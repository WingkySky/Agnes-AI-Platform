# =====================================================
# 资源转存到对象存储服务
# 职责：
#   1. 把上游 Provider（如 Seedance/Seedream）返回的临时 URL 转存到永久可访问的对象存储
#   2. 抽象 StorageBackend 接口，初期实现 S3CompatBackend（对接 R2/S3/MinIO/OSS）
#   3. 未来可扩展其他后端（本地磁盘、Azure Blob 等）而不改动上层调用代码
#
# 关键设计：
#   - 上层代码（轮询器、路由、迁移脚本）通过 migrate_if_needed() / migrate_pending_record()
#     / get_storage_backend() 使用本模块，不直接 import 具体后端类
#   - boto3 是同步 SDK，调用时包装到 asyncio.to_thread 中执行，避免阻塞事件循环
#   - 转存失败不抛异常，返回 pending 状态由上层决定如何处理
# =====================================================

import asyncio
import io
import logging
import mimetypes
import os
from datetime import datetime
from typing import Optional, Tuple, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import new_async_session
from app.models.generation import Generation

logger = logging.getLogger("agnes_platform")

# 大文件阈值（8MB），超过则使用流式上传
LARGE_FILE_THRESHOLD_BYTES = 8 * 1024 * 1024


# =====================================================
# StorageBackend 抽象接口
# =====================================================
class StorageBackend(Protocol):
    """对象存储后端抽象接口"""

    def is_configured(self) -> bool:
        """判断后端是否已配置完整凭据"""
        ...

    async def upload_from_url(self, upstream_url: str, key: str, timeout: int) -> str:
        """从上游 URL 下载并上传到对象存储，返回公共 URL"""
        ...

    async def upload_fileobj(self, fileobj, key: str, content_type: Optional[str] = None) -> str:
        """上传文件对象到对象存储，返回公共 URL"""
        ...

    def build_public_url(self, key: str) -> str:
        """根据对象 key 构造公共访问 URL"""
        ...


# =====================================================
# S3CompatBackend - S3 兼容存储后端实现
# 适配 Cloudflare R2 / AWS S3 / MinIO / 阿里云 OSS S3 兼容模式
# =====================================================
class S3CompatBackend:
    """
    S3 兼容存储后端（适配 Cloudflare R2 / AWS S3 / MinIO / 阿里云 OSS S3 兼容模式）
    基于 boto3 SDK
    """

    def __init__(self):
        self._client = None  # 懒加载

    def _get_client(self):
        """懒加载 boto3 S3 客户端（同步对象，调用时包装到 asyncio.to_thread）"""
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.storage_endpoint or None,
                aws_access_key_id=settings.storage_access_key_id,
                aws_secret_access_key=settings.storage_secret_access_key,
                region_name=settings.storage_region,
            )
        return self._client

    def is_configured(self) -> bool:
        """校验所有必填字段非空"""
        # 注意：endpoint 可以为空（AWS S3 默认 endpoint）
        return bool(
            settings.storage_access_key_id
            and settings.storage_secret_access_key
            and settings.storage_bucket
            and settings.storage_public_url_base
        )

    def build_public_url(self, key: str) -> str:
        """构造公共访问 URL"""
        base = settings.storage_public_url_base.rstrip("/")
        return f"{base}/{key}"

    async def upload_from_url(self, upstream_url: str, key: str, timeout: int) -> str:
        """
        从上游 URL 流式下载并上传到 S3 兼容存储
        - 小文件（<8MB）：先下载到内存再 put_object
        - 大文件（>=8MB）：流式下载到 upload_fileobj
        """
        # 用 httpx 流式下载
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", upstream_url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                # 读取 Content-Length 判断是否大文件
                content_length = int(resp.headers.get("content-length", "0") or "0")

                if content_length and content_length >= LARGE_FILE_THRESHOLD_BYTES:
                    # 大文件：流式上传
                    # 把 httpx 流包装成 file-like 对象给 boto3 upload_fileobj
                    buf = io.BytesIO()
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        buf.write(chunk)
                    buf.seek(0)
                    await asyncio.to_thread(self._upload_fileobj_sync, buf, key, content_type)
                else:
                    # 小文件：读完整 body 再 put_object
                    body = await resp.aread()
                    await asyncio.to_thread(self._put_object_sync, body, key, content_type)

        return self.build_public_url(key)

    def _put_object_sync(self, body: bytes, key: str, content_type: str):
        """同步 put_object（在 to_thread 中执行）"""
        client = self._get_client()
        kwargs = {"Bucket": settings.storage_bucket, "Key": key, "Body": body}
        if content_type:
            kwargs["ContentType"] = content_type
        client.put_object(**kwargs)

    def _upload_fileobj_sync(self, fileobj, key: str, content_type: str):
        """同步 upload_fileobj（在 to_thread 中执行）"""
        client = self._get_client()
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        client.upload_fileobj(
            Fileobj=fileobj,
            Bucket=settings.storage_bucket,
            Key=key,
            ExtraArgs=extra_args if extra_args else None,
        )

    async def upload_fileobj(self, fileobj, key: str, content_type: Optional[str] = None) -> str:
        """直接上传文件对象"""
        await asyncio.to_thread(self._upload_fileobj_sync, fileobj, key, content_type or "")
        return self.build_public_url(key)


# =====================================================
# 工厂函数与单例缓存
# =====================================================
# 后端单例缓存
_backend_instance: Optional[StorageBackend] = None
_backend_initialized: bool = False


def get_storage_backend() -> Optional[StorageBackend]:
    """
    工厂函数：按 settings.storage_backend_type 返回对应后端实例
    - 缓存单例，首次创建后复用
    - 未配置必填字段时返回 None
    - 上层代码应通过此函数获取后端，不直接 import 具体实现类
    """
    global _backend_instance, _backend_initialized
    if _backend_initialized:
        return _backend_instance
    _backend_initialized = True

    backend_type = settings.storage_backend_type
    if backend_type == "s3":
        candidate = S3CompatBackend()
        if candidate.is_configured():
            _backend_instance = candidate
            logger.info("[对象存储] 已启用 S3 兼容后端: endpoint=%s bucket=%s",
                        settings.storage_endpoint or "(aws default)", settings.storage_bucket)
        else:
            logger.warning("[对象存储] S3 兼容后端未配置完整凭据，跳过转存")
    # 未来扩展：
    # elif backend_type == "local":
    #     candidate = LocalDiskBackend()
    #     ...
    else:
        logger.warning("[对象存储] 未知的后端类型: %s", backend_type)

    return _backend_instance


def is_configured() -> bool:
    """判断对象存储是否已配置可用（委托给当前 backend）"""
    backend = get_storage_backend()
    return backend is not None and backend.is_configured()


# =====================================================
# 模块级辅助函数
# =====================================================
def _build_object_key(record_id: int, type: str, created_at: datetime, ext: str) -> str:
    """
    生成对象 key：generated/{type}/{yyyy-mm}/{record_id}.{ext}
    - type: 'image' 或 'video'
    - created_at: 记录创建时间，用于归档分目录
    - ext: 文件扩展名（不含点，如 'png' / 'mp4'）
    """
    if not created_at:
        created_at = datetime.utcnow()
    yyyymm = created_at.strftime("%Y-%m")
    return f"generated/{type}/{yyyymm}/{record_id}.{ext}"


def _infer_ext(upstream_url: str, content_type: str, type: str) -> str:
    """
    从上游 URL 路径或 Content-Type 推断扩展名
    - 优先从 URL 路径后缀推断
    - 其次从 content-type 推断
    - 兜底：图片默认 png，视频默认 mp4
    """
    # 从 URL 路径推断
    if upstream_url:
        path = urlparse(upstream_url).path
        if "." in os.path.basename(path):
            ext = path.rsplit(".", 1)[-1].lower()
            # 过滤掉查询参数
            ext = ext.split("?")[0].split("&")[0]
            if ext and ext.isalpha() and len(ext) <= 5:
                return ext

    # 从 content-type 推断
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext.lstrip(".")

    # 兜底
    return "png" if type == "image" else "mp4"


# =====================================================
# 转存核心逻辑
# =====================================================
async def _do_migrate(
    upstream_url: str,
    record_id: int,
    type: str,
    created_at: datetime,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    实际执行转存（不含策略判断），返回 (result_url, original_url, migrate_status)
    - 转存成功：(r2_url, upstream_url, "done")
    - 转存失败重试 N 次后：(upstream_url, upstream_url, "pending")
    - backend 未配置：(upstream_url, upstream_url, "pending")
    """
    backend = get_storage_backend()
    if backend is None:
        logger.warning("[资源转存] 对象存储未配置，跳过转存: record_id=%s", record_id)
        return (upstream_url, upstream_url, "pending")

    # 先获取 Content-Type 用于推断扩展名（HEAD 请求，失败则用默认扩展名）
    content_type = ""
    timeout = settings.storage_image_upload_timeout_sec if type == "image" else settings.storage_video_upload_timeout_sec
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            head_resp = await client.head(upstream_url)
            content_type = head_resp.headers.get("content-type", "")
    except Exception as e:
        logger.debug("[资源转存] HEAD 请求失败，将用默认扩展名: %s", e)

    ext = _infer_ext(upstream_url, content_type, type)
    key = _build_object_key(record_id, type, created_at, ext)

    # 重试 N 次
    retry_max = settings.storage_migrate_retry_max
    retry_interval = settings.storage_migrate_retry_interval_sec
    last_error = None
    for attempt in range(1, retry_max + 2):  # 1 次正常 + retry_max 次重试
        try:
            logger.info("[资源转存] 开始转存: record_id=%s key=%s attempt=%s", record_id, key, attempt)
            public_url = await backend.upload_from_url(upstream_url, key, timeout)
            logger.info("[资源转存] 转存成功: record_id=%s url=%s", record_id, public_url[:100])
            return (public_url, upstream_url, "done")
        except Exception as e:
            last_error = e
            logger.warning("[资源转存] 转存失败: record_id=%s attempt=%s error=%s", record_id, attempt, e)
            if attempt <= retry_max:
                await asyncio.sleep(retry_interval)

    logger.error("[资源转存] 转存最终失败: record_id=%s error=%s", record_id, last_error)
    return (upstream_url, upstream_url, "pending")


async def migrate_if_needed(
    upstream_url: str,
    record_id: int,
    type: str,
    created_at: datetime,
    model_id: str,
    asset_storage_mode: str,
    provider_type: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    顶层转存入口（供轮询器调用）
    - 根据 asset_storage_mode 决定是否转存
    - auto 模式按 provider_type 判断：agnes → keep，其他 → migrate
    - 返回 (result_url, original_url, migrate_status)
    - 不抛异常，失败返回 pending

    参数：
    - upstream_url: 上游 Provider 返回的原始 URL
    - record_id: 生成记录 ID（generations.id）
    - type: 'image' 或 'video'
    - created_at: 记录创建时间
    - model_id: 模型 ID（用于日志追溯）
    - asset_storage_mode: 模型的存储策略 'auto' / 'keep' / 'migrate'
    - provider_type: 所属 Provider 的类型（'agnes' / 'volcengine_cv' 等）
    """
    if not upstream_url:
        return ("", None, None)

    # 策略判断
    if asset_storage_mode == "keep":
        return (upstream_url, None, None)
    elif asset_storage_mode == "migrate":
        should_migrate = True
    elif asset_storage_mode == "auto":
        # agnes provider 保持原样，其他转存
        should_migrate = provider_type != "agnes"
    else:
        logger.warning("[资源转存] 未知 asset_storage_mode=%s，按 keep 处理", asset_storage_mode)
        return (upstream_url, None, None)

    if not should_migrate:
        return (upstream_url, None, None)

    return await _do_migrate(upstream_url, record_id, type, created_at)


async def migrate_pending_record(record_id: int) -> Tuple[bool, str]:
    """
    重试 pending 状态的记录（供管理员接口和迁移脚本调用）
    - 从数据库读取 original_url 重试转存
    - 成功则更新 result_url / migrate_status=done
    - 失败则保持 migrate_status=pending
    - 返回 (success, message)
    """
    async with new_async_session() as session:
        record = await session.get(Generation, record_id)
        if not record:
            return (False, f"记录不存在: {record_id}")
        if record.migrate_status != "pending":
            return (False, f"记录状态不是 pending: {record.migrate_status}")
        if not record.original_url:
            return (False, "原始 URL 为空，无法重试")

        try:
            result_url, original_url, migrate_status = await _do_migrate(
                upstream_url=record.original_url,
                record_id=record.id,
                type=record.type,
                created_at=record.created_at,
            )
            if migrate_status == "done":
                record.result_url = result_url
                record.migrate_status = "done"
                await session.commit()
                return (True, f"转存成功: {result_url[:80]}")
            else:
                # 保持 pending 状态
                return (False, "转存失败，保持 pending 状态")
        except Exception as e:
            logger.error("[资源转存] 重试失败: record_id=%s error=%s", record_id, e)
            return (False, str(e))

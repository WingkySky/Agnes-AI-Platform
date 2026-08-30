# =====================================================
# AIBridge 统一接入客户端封装
#
# 职责：
#   封装 aibridge-sdk (v2) 的 Client，对外暴露与 AgnesAIClient 兼容的方法签名
#   （list_models / create_image / create_video_task / poll_video_status），
#   让业务层无感切换到任意 aibridge 支持的 Provider（volcengine_cv / kling / runway / pika 等）。
#
# 设计原则（与用户讨论确认的分层）：
#   - aibridge 负责「协议适配」：不同 Provider 的端点 / 请求格式 / 响应结构差异
#   - agnes-platform 中间层（AgnesAIClient）负责「业务字段适配」：8n+1 帧数对齐、
#     宽高 8 倍数、mode 归一化、提示词改写、审核重试、图像归一化等 Agnes-specific 经验
#   - 本类不做任何业务字段适配，仅做协议层调用与结果归一化
#     （其他 Provider 不需要 8n+1 等约束，aibridge 已处理协议差异）
#
# 返回值兼容：
#   所有方法的返回值都是 dict，结构与 AgnesAIClient 对应方法的返回值保持一致，
#   业务调用方无需感知底层是 AgnesAIClient 还是 AGNSDKClient。
#
# v2 变更说明：
#   - PyPI 包名 agn-sdk → aibridge-sdk
#   - 顶层模块 agn → aibridge
#   - 基础错误类 AGNError → AibridgeError
#   - 移除 poll_url 参数（v2 不再支持，轮询由 video_poll 方法内部处理）
# =====================================================

import logging
from typing import Any, Dict, List, Optional

from aibridge import Client as AIBridgeClient
from aibridge import (
    AibridgeError,
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    TimeoutError,
    UnsupportedCapabilityError,
    ValidationError,
)

logger = logging.getLogger("agnes_platform")


# ---------- aibridge SDK 错误到 RuntimeError 的统一翻译 ----------
# 与 AgnesAIClient._human_readable_error 行为一致：把底层异常翻译成中文可读消息
def _build_translated_error(exc: Exception, action: str = "调用") -> RuntimeError:
    """
    根据 aibridge 抛出的标准错误构造中文 RuntimeError 实例。
    调用方应使用 `raise _build_translated_error(e, ...) from e` 抛出，
    保留原始异常链（__cause__）便于排查。
    """
    if isinstance(exc, AuthenticationError):
        msg = f"API Key 无效或已过期（{action}失败）"
    elif isinstance(exc, RateLimitError):
        msg = f"请求被限流，请稍后重试（{action}失败）"
    elif isinstance(exc, TimeoutError):
        msg = f"上游响应超时，可稍后重试（{action}失败）"
    elif isinstance(exc, NetworkError):
        msg = f"网络异常，无法访问上游服务（{action}失败）"
    elif isinstance(exc, ValidationError):
        msg = f"参数校验失败：{exc}（{action}失败）"
    elif isinstance(exc, UnsupportedCapabilityError):
        msg = f"当前 Provider 不支持该能力：{exc}（{action}失败）"
    elif isinstance(exc, APIError):
        # 通用 API 错误，包含 status_code 与原始 message
        msg = f"上游 API 错误（{action}失败）：{exc}"
    elif isinstance(exc, AibridgeError):
        msg = f"aibridge SDK 错误（{action}失败）：{exc}"
    else:
        msg = f"{action}失败：{exc.__class__.__name__}: {exc}"
    return RuntimeError(msg)


class AGNSDKClientWrapper:
    """
    aibridge SDK 统一客户端封装。

    通过 aibridge 的 Client 调用任意已注册的 Adapter（volcengine_cv / kling / runway / pika 等），
    对外暴露与 AgnesAIClient 兼容的方法签名，让业务层无需感知底层 Provider 差异。

    使用方式：
        wrapper = AGNSDKClientWrapper(
            provider_type="volcengine_cv",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="xxx",
        )
        await wrapper.start()
        models = await wrapper.list_models()
        result = await wrapper.create_image(prompt="...", model="seedream-3.0", size="1024x1024")
        await wrapper.shutdown()
    """

    def __init__(
        self,
        provider_type: str,
        base_url: str = "",
        api_key: str = "",
    ) -> None:
        """
        初始化封装客户端。

        Args:
            provider_type: aibridge adapter 标识（如 volcengine_cv / kling / runway / pika）
            base_url: API Base URL（可选，部分 Provider 有默认值）
            api_key: API Key（明文）
        """
        self.provider_type = provider_type
        self.base_url = base_url
        self.api_key = api_key
        # aibridge Client 实例（start 后才可用）
        self._client: Optional[AIBridgeClient] = None

    def configure(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        运行时切换 Provider 配置（与 AgnesAIClient.configure 接口对齐）。
        仅更新传入的非 None 字段，下次 start() 时生效。
        """
        if base_url is not None and base_url != self.base_url:
            self.base_url = base_url
        if api_key is not None and api_key != self.api_key:
            self.api_key = api_key
        logger.info(
            "[AGNSDKClient] 配置已更新: provider_type=%s, base_url=%s, api_key=%s",
            self.provider_type, self.base_url, "***" if self.api_key else "(空)",
        )

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        """启动 aibridge Client（初始化适配器与底层 HTTP 连接池）"""
        if self._client is None:
            self._client = AIBridgeClient(
                provider=self.provider_type,
                api_key=self.api_key or None,
                base_url=self.base_url or None,
            )
            await self._client.start()
            logger.info(
                "[AGNSDKClient] Client 已启动: provider_type=%s, base_url=%s",
                self.provider_type, self.base_url,
            )

    async def shutdown(self) -> None:
        """关闭 aibridge Client（释放底层 HTTP 连接池）"""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning("[AGNSDKClient] 关闭 Client 失败: %s", e)
            self._client = None
            logger.info("[AGNSDKClient] Client 已关闭")

    def _get_client(self) -> AIBridgeClient:
        """获取已启动的 aibridge Client，未启动时抛错"""
        if self._client is None:
            raise RuntimeError("AGNSDKClient 未启动，请先调用 start()")
        return self._client

    # ---------- 兼容 AgnesAIClient 的方法 ----------

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        调用 aibridge Client.list_models() 获取模型列表。

        返回值结构与 AgnesAIClient.list_models 兼容：
        OpenAI 风格的 [{"id": "model-id", "name": "...", "type": "...", ...}, ...]

        失败时抛出中文 RuntimeError（认证失败 / 路径不存在等），
        由模型同步链路透出给前端，避免"同步成功但 0 个"的静默失败。
        """
        client = self._get_client()
        try:
            models = await client.list_models()
        except Exception as e:
            raise _build_translated_error(e, action="获取模型列表") from e

        # 转成 OpenAI 风格的 dict 列表（与 AgnesAIClient.list_models 返回结构对齐）
        result: List[Dict[str, Any]] = []
        for m in models:
            result.append(
                {
                    "id": m.id,
                    "object": "model",
                    "created": m.created or 0,
                    "owned_by": m.provider,
                    # 扩展字段（兼容业务侧的模型类型/能力推断）
                    "name": m.name,
                    "type": m.type,
                    "provider": m.provider,
                    "capabilities": m.capabilities or [],
                    "description": m.description,
                }
            )
        return result

    # ── 方舟 Seedream 尺寸规范（与 aibridge volcengine_cv 适配器 normalize_image_size 同源）──
    # 合法总像素区间 [3.6864MP(2K), 16.77MP(4K)]，宽高比 ∈ [1/16, 16]；
    # 超出区间时按最接近宽高比映射到官方 2K 推荐档（最小合法档）。
    _SEEDREAM_MIN_PIXELS = 3_686_400
    _SEEDREAM_MAX_PIXELS = 16_777_216
    _SEEDREAM_2K_PRESETS = [
        (9 / 16, 1600, 2848),
        (2 / 3, 1664, 2496),
        (3 / 4, 1728, 2304),
        (1.0, 2048, 2048),
        (4 / 3, 2304, 1728),
        (3 / 2, 2496, 1664),
        (16 / 9, 2848, 1600),
        (21 / 9, 3136, 1344),
    ]

    @classmethod
    def _normalize_seedream_size(cls, size: str) -> str:
        """Seedream 系模型尺寸归一化：合法原样透传，不合法按宽高比落到 2K 推荐档。"""
        try:
            w_str, h_str = (size or "").strip().lower().replace("*", "x").split("x", 1)
            w, h = int(w_str), int(h_str)
        except ValueError:
            return "2048x2048"
        if w <= 0 or h <= 0:
            return "2048x2048"
        total, ratio = w * h, w / h
        if cls._SEEDREAM_MIN_PIXELS <= total <= cls._SEEDREAM_MAX_PIXELS and 1 / 16 <= ratio <= 16:
            return f"{w}x{h}"
        best = min(cls._SEEDREAM_2K_PRESETS, key=lambda p: abs(ratio - p[0]))
        return f"{best[1]}x{best[2]}"

    async def create_image(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x1024",
        response_format: str = "url",
        base64_image: Optional[str] = None,
        image_url: Optional[str] = None,
        base64_images: Optional[List[str]] = None,
        image_urls: Optional[List[str]] = None,
        mask: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调用 aibridge Client.image_generate() 生成图片。

        与 AgnesAIClient.create_image 接口对齐，合并参考图后透传给 aibridge。
        返回值结构与 AgnesAIClient 兼容：
        {"id": ..., "created": ..., "model": ..., "data": [{"url": ... / "b64_json": ...}, ...]}
        """
        client = self._get_client()

        # 合并参考图：新字段优先，回退到旧字段（与 AgnesAIClient.create_image 逻辑一致）
        ref_images: List[str] = []
        if base64_images:
            ref_images.extend([img for img in base64_images if img and isinstance(img, str) and img.strip()])
        if image_urls:
            ref_images.extend([u for u in image_urls if u and isinstance(u, str) and u.strip()])
        if not ref_images and base64_image and base64_image.strip():
            ref_images.append(base64_image)
        if not ref_images and image_url and image_url.strip():
            ref_images.append(image_url)

        # ── Seedream 系模型分辨率归一化（与 aibridge volcengine_cv 适配器同规则）──
        # 方舟 Seedream 合法总像素 ∈ [3.6864MP(2K 档), 16.77MP(4K 档)]。volcengine_cv
        # 适配器自带归一化；openai 协议兼容端点（如火山 agent plan）size 原样透传，
        # 前端全局默认 1024x1024 低于 Seedream 最小档，需按宽高比映射到官方 2K 推荐档。
        if "seedream" in (model or "").lower():
            size = self._normalize_seedream_size(size)

        # ── 厂商特有参数经 image_generate **kwargs → adapter extra → 请求体顶层透传 ──
        # Seedream 系生图默认在画面加「AI生成」显式标识水印（标识办法合规要求），
        # 按方舟官方 watermark 参数关闭（volcengine_cv 全量 + openai 兼容端点的 seedream 模型）；
        # 发布内容时按平台规则声明 AI 生成的义务由使用方承担。
        sdk_kwargs = {}
        if self.provider_type == "volcengine_cv" or "seedream" in (model or "").lower():
            sdk_kwargs["watermark"] = False
        try:
            result = await client.image_generate(
                model=model,
                prompt=prompt,
                size=size,
                n=1,
                response_format=response_format,
                reference_images=ref_images if ref_images else None,
                mask=mask,
                **sdk_kwargs,
            )
        except Exception as e:
            raise _build_translated_error(e, action="图片生成") from e

        # 转成 OpenAI 风格 dict（与 AgnesAIClient._post 返回的原始 JSON 结构对齐）
        return {
            "id": result.id,
            "created": result.created,
            "model": result.model,
            "data": [
                {
                    "url": item.url,
                    "b64_json": item.b64_json,
                    "revised_prompt": item.revised_prompt,
                }
                for item in (result.data or [])
            ],
        }

    async def create_video_task(
        self,
        prompt: str,
        model: str = "",
        num_frames: Optional[int] = None,
        frame_rate: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        seconds: Optional[float] = None,
        negative_prompt: Optional[str] = None,
        mode: str = "text2video",
        image: Optional[str] = None,
        images: Optional[list] = None,
        image_mime_type: Optional[str] = None,
        image_mime_types: Optional[list] = None,
        seed: Optional[int] = None,
        # Video 2.5 new params
        reference_videos: Optional[List[str]] = None,
        reference_audios: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        调用 aibridge Client.video_create() 创建视频生成任务。

        与 AgnesAIClient.create_video_task 接口对齐：
        - 合并 image / images 参数为 reference_images 透传给 aibridge
        - Video 2.5: 透传 reference_videos 和 reference_audios
        - 不做 8n+1 / 8 倍数 / mode 归一化等业务适配
          （这些是 Agnes Video API 的硬性要求，其他 Provider 不一定需要；
           如果其他 Provider 也有类似约束，应在对应 aibridge Adapter 内处理）
        - 返回值结构与 AgnesAIClient 兼容：
          {"id": task_id, "video_id": task_id, "status": "pending", "model": ..., ...}
        """
        client = self._get_client()

        # 合并参考图：单图 + 多图统一转成 reference_images
        ref_images: List[str] = []
        if image and isinstance(image, str) and image.strip():
            ref_images.append(image.strip())
        if images and isinstance(images, (list, tuple)):
            ref_images.extend([img for img in images if img and isinstance(img, str) and img.strip()])

        # 计算默认宽高（与 AgnesAIClient 一致的默认值）
        _width = int(width) if width and width > 0 else 1280
        _height = int(height) if height and height > 0 else 720
        _frame_rate = int(frame_rate) if frame_rate and frame_rate > 0 else 24
        _num_frames = num_frames

        # seconds 转 num_frames（如果 num_frames 未传但 seconds 传了）
        if _num_frames is None and seconds and seconds > 0:
            _num_frames = int(round(seconds * _frame_rate))

        try:
            task = await client.video_create(
                model=model,
                prompt=prompt,
                width=_width,
                height=_height,
                num_frames=_num_frames,
                frame_rate=_frame_rate,
                mode=mode,
                reference_images=ref_images if ref_images else None,
                reference_videos=reference_videos if reference_videos else None,
                reference_audios=reference_audios if reference_audios else None,
                negative_prompt=negative_prompt,
                seed=seed,
            )
        except Exception as e:
            raise _build_translated_error(e, action="视频任务创建") from e

        # 转成与 AgnesAIClient._post 返回兼容的 dict
        # AgnesAIClient 返回的是原始 HTTP response JSON，包含 id / video_id / status / created 等字段
        return {
            "id": task.task_id,
            "video_id": task.task_id,
            "task_id": task.task_id,
            "model": task.model,
            "status": task.status,
            "created": task.created_at,
        }

    async def poll_video_status(
        self,
        video_id: Optional[str] = None,
        task_id: Optional[str] = None,
        model_name: str = "",
    ) -> Dict[str, Any]:
        """
        调用 aibridge Client.video_poll() 查询视频任务状态。

        与 AgnesAIClient.poll_video_status 接口对齐：
        - 优先使用 video_id 作为 task_id（与 AgnesAIClient 一致）
        - 回退到 task_id
        - 返回值结构与 AgnesAIClient._normalize_video_status 兼容：
          {"status": "success"|"processing"|"failed", "video_url": ..., "progress": ..., "error": ...}
        """
        client = self._get_client()

        # AgnesAIClient 优先用 video_id 轮询，这里保持一致
        poll_task_id = video_id or task_id
        if not poll_task_id:
            raise RuntimeError("缺少 video_id 和 task_id，无法轮询视频状态")

        try:
            status = await client.video_poll(
                task_id=poll_task_id,
                model=model_name,
            )
        except Exception as e:
            raise _build_translated_error(e, action="视频状态查询") from e

        # 转成与 AgnesAIClient._normalize_video_status 兼容的 dict
        # AgnesAIClient 返回的 status 字段使用 success/processing/failed/pending 标准化值
        # aibridge VideoStatus.status 也是同样取值（pending/processing/success/failed），无需转换
        return {
            "status": status.status,
            "video_url": status.video_url,
            "progress": status.progress,
            "error": status.error,
            "task_id": status.task_id,
            "created_at": status.created_at,
            "updated_at": status.updated_at,
        }

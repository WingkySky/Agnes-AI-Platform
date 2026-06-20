# =====================================================
# Agnes AI API 客户端封装（异步 + 连接池
# 负责：
#   1. 构建带鉴权的 HTTP 请求（通过持久化 httpx.AsyncClient 发送，复用连接）
#   2. 图片生成（异步同步等待，不阻塞其他请求）
#   3. 视频任务创建 + 轮询（异步）
#
# 关键设计：
#   - 使用单一持久化的 httpx.AsyncClient（连接池），避免每次请求新建 TCP 连接
#   - start() 在应用启动时调用，shutdown() 在关闭时释放
#   - 所有 API 方法均为 async，配合 FastAPI 异步路由，图片/视频任务互不阻塞
# =====================================================

import asyncio
import logging
import time
from typing import List, Optional, Dict, Any

import httpx

from app.core.config import settings

logger = logging.getLogger("agnes_platform")

# ---------- 重试与超时配置（集中在一处，便于调参） ----------
# 单次请求超时（包含连接 + 读取，AI 生成本身就慢，默认 300s 更稳）
REQUEST_TIMEOUT_SEC = 300.0
# 仅连接阶段的超时（防止 DNS/握手卡死）
CONNECT_TIMEOUT_SEC = 30.0
# 最大重试次数（第一次成功就不重试）
MAX_RETRIES = 3
# 首次失败后的等待时间（秒，之后指数退避 ×2）
RETRY_INITIAL_BACKOFF = 2.0
# 对哪些异常/状态码重试（只对"很可能是暂时的"情况重试，避免把坏请求重复打到上游）
RETRYABLE_EXCEPTIONS = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.WriteError,
    httpx.PoolTimeout,
    httpx.NetworkError,
    # 下面这些其实是上游返回了错误响应，需要更细判断，由 _post 内部单独判断
)
RETRYABLE_STATUS_CODES = (502, 503, 504, 520, 521, 522, 523, 524)


# =====================================================
# AgnesAIClient - Agnes AI API 客户端
# =====================================================
class AgnesAIClient:
    """
    Agnes AI 官方 API 的统一调用封装。
    使用单一持久化 httpx.AsyncClient（内部维护 HTTP 连接池），
    多个并发请求复用底层 TCP 连接，显著降低延迟。
    """

    def __init__(self):
        self.api_key = settings.agnes_api_key
        self.base_url = settings.agnes_api_base_url
        self.poll_url = settings.agnes_api_poll_url
        self.poll_interval = settings.video_poll_interval_sec
        self.poll_timeout = settings.video_poll_timeout_sec

        # 通用 HTTP Headers（鉴权）
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # ---------- 持久化的 httpx.AsyncClient（连接池）
        # 连接池限制：默认 100 个并发连接
        # 超时：单请求 120s，允许 AI 生成较长时间
        self._client: Optional[httpx.AsyncClient] = None

    # ---------- 生命周期 ----------
    async def start(self):
        """
        应用启动时初始化 HTTP 客户端（连接池）。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                http2=False,
            )
            logger.info(
                "[AgnesAIClient] HTTP 连接池已初始化 (timeout=%ss, connect=%ss, retries=%s)",
                REQUEST_TIMEOUT_SEC, CONNECT_TIMEOUT_SEC, MAX_RETRIES,
            )

    async def shutdown(self):
        """
        应用关闭时释放 HTTP 客户端连接。
        """
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("[AgnesAIClient] HTTP 连接池已释放")

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        调用 GET /models 获取 API 提供商的所有可用模型列表。
        OpenAI 兼容 API 标准：返回 { "data": [{ "id": "model-id", ... }, ...] }
        """
        url = f"{self.base_url}/models"
        # GET 请求不需要 Content-Type，只传鉴权
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = await self.client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            # OpenAI 兼容格式：{ "object": "list", "data": [...] }
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            # 兜底：直接返回列表
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.warning("[AgnesAIClient] 获取模型列表失败: %s", e)
            return []

    # ---------- 获取当前 client（懒初始化保护）----------
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # 兜底：如果 start() 未被调用，则临时创建一个（不推荐）
            logger.warning("[AgnesAIClient] client 未初始化，正在临时创建")
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    # ---------- 统一的错误翻译：把网络异常转成中文可读消息 ----------
    @staticmethod
    def _human_readable_error(exc: BaseException) -> str:
        """把底层 httpx/httpcore 异常翻译成一句话可读错误。"""
        if isinstance(exc, httpx.ReadTimeout):
            return "Agnes AI 响应超时（上游生成较慢或网络抖动），可稍后重试"
        if isinstance(exc, httpx.ConnectTimeout):
            return "无法连接到 Agnes AI（连接超时），请检查网络或稍后重试"
        if isinstance(exc, httpx.ConnectError):
            return "无法连接到 Agnes AI（网络不可达或域名解析失败）"
        if isinstance(exc, httpx.PoolTimeout):
            return "连接池等待超时（并发过高），请稍后重试"
        if isinstance(exc, httpx.WriteError):
            return "请求发送过程中连接断开，请稍后重试"
        if isinstance(exc, httpx.NetworkError):
            return "网络异常，无法访问 Agnes AI，请检查网络"
        return f"调用 Agnes AI 失败: {exc.__class__.__name__}: {exc}"

    # =====================================================
    # 【第一层：基础 HTTP 工具】
    # =====================================================
    async def _post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 POST 请求到 Agnes AI API（使用连接池）。
        为了避免把超长 base64 整段打进日志，这里对 extra_body.image / image 做摘要处理：
        只记录其前 120 字符与总长。
        """
        # ---------- 构造可安全打日志的摘要 body ----------
        safe_body: Dict[str, Any] = {}
        for k, v in body.items():
            if k == "extra_body" and isinstance(v, dict):
                safe_extra: Dict[str, Any] = {}
                for ek, ev in v.items():
                    if ek in ("image", "image_end") and isinstance(ev, str):
                        safe_extra[ek] = f"<str len={len(ev)}> {ev[:120]}..."
                    elif ek == "image" and isinstance(ev, list):
                        safe_extra[ek] = [
                            f"<str len={len(x)}> {x[:120]}..." if isinstance(x, str) else x
                            for x in ev
                        ]
                    else:
                        safe_extra[ek] = ev
                safe_body[k] = safe_extra
            elif k in ("image", "images") and isinstance(v, (list, str)):
                if isinstance(v, str):
                    safe_body[k] = f"<str len={len(v)}> {v[:120]}..."
                else:
                    safe_body[k] = [
                        f"<str len={len(x)}> {x[:120]}..." if isinstance(x, str) else x
                        for x in v
                    ]
            else:
                safe_body[k] = v

        logger.info("[AgnesAIClient] POST %s body=%s", url, safe_body)

        # ---------- 自动重试循环（指数退避）----------
        last_exc: Optional[BaseException] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.post(url, json=body, headers=self._headers)
            except RETRYABLE_EXCEPTIONS as e:
                last_exc = e
                if attempt >= MAX_RETRIES:
                    raise RuntimeError(self._human_readable_error(e)) from e
                wait = RETRY_INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "[AgnesAIClient] POST 第 %s/%s 次网络异常: %s, %ss 后重试",
                    attempt, MAX_RETRIES, self._human_readable_error(e), wait,
                )
                import asyncio
                await asyncio.sleep(wait)
                continue
            except Exception as e:  # 其他异常（如参数错误、鉴权失败）不重试
                raise RuntimeError(self._human_readable_error(e)) from e

            # 对 5xx 网关类错误也做有限次重试（上游抖动常见）
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                wait = RETRY_INITIAL_BACKOFF * (2 ** (attempt - 1))
                preview = (response.text or "")[:120].strip().replace("\n", " ")
                logger.warning(
                    "[AgnesAIClient] POST 第 %s/%s 次返回 HTTP %s，%ss 后重试 (resp=%s)",
                    attempt, MAX_RETRIES, response.status_code, wait, preview,
                )
                import asyncio
                await asyncio.sleep(wait)
                continue

            # 到这里就是最终响应（不管成功还是失败的业务错误码）
            return self._parse_response(response)

        # 理论上到不了这里（最后一次要么抛要么返回）
        if last_exc is not None:
            raise RuntimeError(self._human_readable_error(last_exc)) from last_exc
        raise RuntimeError("调用 Agnes AI 失败：未知错误")

    async def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        发送 GET 请求到 Agnes AI API（使用连接池）。
        与 POST 一样做自动重试 + 中文错误信息。
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.get(url, params=params or {}, headers=self._headers)
            except RETRYABLE_EXCEPTIONS as e:
                last_exc = e
                if attempt >= MAX_RETRIES:
                    raise RuntimeError(self._human_readable_error(e)) from e
                wait = RETRY_INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "[AgnesAIClient] GET 第 %s/%s 次网络异常: %s, %ss 后重试",
                    attempt, MAX_RETRIES, self._human_readable_error(e), wait,
                )
                import asyncio
                await asyncio.sleep(wait)
                continue
            except Exception as e:
                raise RuntimeError(self._human_readable_error(e)) from e

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                wait = RETRY_INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "[AgnesAIClient] GET 第 %s/%s 次返回 HTTP %s，%ss 后重试",
                    attempt, MAX_RETRIES, response.status_code, wait,
                )
                import asyncio
                await asyncio.sleep(wait)
                continue

            return self._parse_response(response)

        if last_exc is not None:
            raise RuntimeError(self._human_readable_error(last_exc)) from last_exc
        raise RuntimeError("调用 Agnes AI 失败：未知错误")

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        统一处理响应：解析 JSON，处理错误（同步解析，不阻塞 I/O）。
        对 5xx / 非 JSON 响应给出更可读的中文错误。
        """
        try:
            data = response.json()
        except Exception:
            text = (response.text or "")[:200].strip().replace("\n", " ")
            # 常见 502/504 是 Cloudflare/上游返回 HTML，给用户一个人话
            if response.status_code in (502, 503, 504):
                raise RuntimeError(
                    f"Agnes AI 上游暂时不可用（HTTP {response.status_code}），请稍后重试"
                )
            if 400 <= response.status_code < 500:
                raise RuntimeError(
                    f"Agnes AI 拒绝了请求（HTTP {response.status_code}）：{text}"
                )
            raise RuntimeError(
                f"Agnes AI 返回非 JSON 响应（HTTP {response.status_code}）：{text}"
            )

        if not response.is_success:
            message = (
                data.get("error", {}).get("message")
                or data.get("message")
                or data.get("detail")
                or str(data)
            )
            raise RuntimeError(f"Agnes AI API 错误 (HTTP {response.status_code}): {message}")

        return data

    # =====================================================
    # 【图像输入归一化】
    # 图生图 / 图生视频 共用同一套处理逻辑：
    #   - 公网 URL（http:// / https://）→ 返回 (url, None)
    #   - Data URI（data:image/xxx;base64,xxxx）→ 清理 base64 段 + 补齐 padding
    #   - 纯 base64 → 清理空白 + 补齐 padding + 按 mime 拼成 Data URI
    # 返回: (normalized_value, size)，size 为 (width, height) 或 None
    # 额外辅助方法 _detect_image_size 负责从 base64/Data URI 里读取 JPEG/PNG 头
    # =====================================================

    @staticmethod
    def _clean_and_pad_base64(b64_str: str) -> str:
        """清理纯 base64 字符串中的空白并补齐 padding（长度为 4 的倍数）。"""
        import re
        b64 = re.sub(r'\s', '', b64_str).rstrip('=')
        pad = len(b64) % 4
        if pad:
            b64 += '=' * (4 - pad)
        return b64

    @classmethod
    def _detect_image_size(cls, data_uri_or_b64: str) -> Optional[tuple]:
        """
        从 Data URI / 纯 base64 中解码头部，识别图片的真实宽高。
        支持 JPEG（SOF0/SOF1/SOF2 marker）和 PNG（IHDR chunk）。
        失败时返回 None（不影响任务提交）。
        """
        try:
            s = data_uri_or_b64.strip()
            if s.lower().startswith("data:"):
                idx = s.rfind(',')
                if idx < 0:
                    return None
                s = s[idx + 1:]
            # 只需要文件头部的一小段就能拿到宽高（PNG 前 24 字节，JPEG 前几百字节）
            head_b64 = s[:2048]
            # 补齐为 4 的倍数，避免 binascii.Error
            pad_needed = (-len(head_b64)) % 4
            if pad_needed:
                head_b64 += '=' * pad_needed
            try:
                import base64
                raw = base64.b64decode(head_b64, validate=False)
            except Exception:
                return None

            if len(raw) < 8:
                return None
            import struct
            # PNG: 89 50 4E 47 0D 0A 1A 0A + length(4) + 'IHDR' + width(4) + height(4)
            if raw[:8] == b'\x89PNG\r\n\x1a\n':
                if len(raw) >= 24 and raw[12:16] == b'IHDR':
                    w, h = struct.unpack('>II', raw[16:24])
                    return (int(w), int(h))
            # JPEG: FF D8 ... SOF marker (FF C0/C1/C2) 后 16 位长度 + 8 位精度 + 16 位 height + 16 位 width
            if raw[:2] == b'\xff\xd8':
                i = 2
                while i < len(raw) - 9:
                    if raw[i] != 0xFF:
                        i += 1
                        continue
                    marker = raw[i + 1]
                    # 独立/差分帧起始（SOF0/SOF1/SOF2），SOI/EOI/DHT 等跳过，DNL 不处理
                    if marker in (0xC0, 0xC1, 0xC2):
                        h, w = struct.unpack('>HH', raw[i + 5:i + 9])
                        return (int(w), int(h))
                    if marker == 0xD9:  # EOI，文件结束
                        break
                    # 该 segment 的长度（包含这 2 字节本身）
                    if i + 3 < len(raw):
                        seg_len = struct.unpack('>H', raw[i + 2:i + 4])[0]
                        i += 2 + seg_len
                    else:
                        break
            return None
        except Exception:
            return None

    @classmethod
    def _normalize_image_input(
        cls, raw: str, default_mime: str = "image/png"
    ) -> tuple:
        """
        统一归一化图像输入：URL / Data URI / 纯 base64 都走这个入口。
        返回 (normalized_value, size)，size 为 (width, height) 或 None（URL 无法本地解码）。
        """
        if not raw or not isinstance(raw, str):
            return ("", None)
        s = raw.strip()
        lowered = s.lower()
        if lowered.startswith(("http://", "https://")):
            # URL 分支：不做尺寸检测（避免额外网络请求），size=None
            return (s, None)
        if lowered.startswith("data:"):
            comma_idx = s.rfind(',')
            if comma_idx < 0:
                # 异常 Data URI：退化为纯 base64 分支
                b64 = cls._clean_and_pad_base64(s)
                out = f"data:{default_mime};base64,{b64}"
                return (out, cls._detect_image_size(b64))
            prefix = s[:comma_idx + 1]
            b64 = cls._clean_and_pad_base64(s[comma_idx + 1:])
            out = f"{prefix}{b64}"
            return (out, cls._detect_image_size(b64))
        # 纯 base64
        b64 = cls._clean_and_pad_base64(s)
        out = f"data:{default_mime};base64,{b64}"
        return (out, cls._detect_image_size(b64))

    # =====================================================
    # 【第二层：API 方法】
    # =====================================================

    # ---------- 图片生成 ----------
    async def create_image(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x1024",
        response_format: str = "url",
        base64_image: Optional[str] = None,           # 保留：向后兼容（单图）
        image_url: Optional[str] = None,               # 保留：向后兼容（单图）
        base64_images: Optional[List[str]] = None,     # 【新增】多图 base64 数组
        image_urls: Optional[List[str]] = None,        # 【新增】多图 URL 数组
        mask: Optional[str] = None,                    # 【新增】蒙版图 base64，用于局部编辑
    ) -> Dict[str, Any]:
        """
        调用 Agnes AI 生成图片（异步等待，不阻塞其他请求的事件循环）。

        API 调用规范（严格按 Agnes Image 2.1 Flash 文档）：
          - model、prompt、size → 顶层必填参数
          - 图生图：image 放在 extra_body 中（2.1-flash 规范，不在顶层）
          - return_base64: true → 文生图 Base64 输出（顶层参数）
          - extra_body.response_format: "url" | "b64_json" → 输出格式（放顶层会 400）
          - 文生图：不传入 image 字段
          - 图生图：image 放在 extra_body.image 中
          - 局部编辑：mask 放在 extra_body.mask 中（黑白图，白色为编辑区域）

        【多图参考改造】：
          - 参数优先级：base64_images / image_urls（新字段，数组）→ base64_image / image_url（旧字段，单值）
          - 所有有效参考图最终会归一化为 data URI 或公网 URL，统一放入 extra_body.image 数组
        """
        url = f"{self.base_url}/images/generations"

        # ── 收集参考图（新字段优先，回退到旧字段） ──
        ref_images: List[str] = []
        if base64_images:
            for img in base64_images:
                if img and isinstance(img, str) and img.strip():
                    ref_images.append(img)
        if image_urls:
            for u in image_urls:
                if u and isinstance(u, str) and u.strip():
                    ref_images.append(u)
        # 如果新字段为空，回退到旧字段（与之前的单图行为一致）
        if not ref_images and base64_image and base64_image.strip():
            ref_images.append(base64_image)
        if not ref_images and image_url and image_url.strip():
            ref_images.append(image_url)

        # 【核心修复】严格按 Agnes Image 2.1 Flash 文档构建请求体
        #   - model、prompt、size → 顶层必填参数
        #   - 图生图：image 放在 extra_body 中（2.1-flash 规范）
        #   - 文生图 Base64 输出：顶层参数 return_base64: true
        #   - response_format → 必须放在 extra_body 中（放顶层会 400）
        #   - seed → 随机种子，避免相同 prompt 生成相同图片
        import random
        body = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "seed": random.randint(1, 2147483647),  # 随机 seed，确保每次请求不同
        }

        if ref_images:
            # 【图生图模式】按官方规范将参考图数组放在 extra_body.image 中
            # 每张图统一走 _normalize_image_input: URL/Data URI/纯 base64 都可
            normalized = []
            for img in ref_images:
                uri, _size = self._normalize_image_input(img)
                if uri:
                    normalized.append(uri)

            extra_body = {
                "image": normalized,
                "response_format": response_format,
            }

            # 【局部编辑模式】mask 归一化后放入 extra_body.mask
            if mask and mask.strip():
                mask_uri, _ = self._normalize_image_input(mask)
                if mask_uri:
                    extra_body["mask"] = mask_uri
                    logger.info("[图片生成] 局部编辑模式: 已附加 mask")

            body["extra_body"] = extra_body
            logger.info(
                "[图片生成] 图生图模式: model=%s, size=%s, ref_images=%d 张, format=%s, mask=%s, prompt=%s",
                model, size, len(normalized), response_format, "yes" if mask and mask.strip() else "no", prompt[:80],
            )
        elif response_format == "b64_json":
            # 【文生图 + Base64 输出】使用顶层参数 return_base64（文档规范）
            body["return_base64"] = True
            logger.info("[图片生成] 文生图模式(Base64): model=%s, size=%s, prompt=%s",
                        model, size, prompt[:80])
        else:
            # 【文生图 + URL 输出】response_format 放在 extra_body（放顶层会 400）
            body["extra_body"] = {
                "response_format": "url",
            }
            logger.info("[图片生成] 文生图模式(URL): model=%s, size=%s, prompt=%s",
                        model, size, prompt[:80])

        return await self._post(url, body)

    # ---------- 视频任务创建 ----------
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
    ) -> Dict[str, Any]:
        """
        创建视频生成异步任务。

        Agnes Video V2.0 当前文档使用 /videos/generations，并接收
        aspect_ratio、duration、fps。前端优先传入 aspect_ratio / seconds，
        不再依赖 width/height / num_frames。
        """
        url = f"{self.base_url}/video/generations"

        # 1) aspect_ratio：优先使用显式传入值；否则由 width/height 计算；最后回退到 16:9
        if aspect_ratio and isinstance(aspect_ratio, str) and aspect_ratio.strip():
            _aspect_ratio = aspect_ratio.strip()
        elif width and height:
            _aspect_ratio = self._aspect_ratio(width, height)
        else:
            _aspect_ratio = "16:9"

        # 2) duration（秒）：优先使用显式传入的 seconds；否则用 num_frames / frame_rate 计算；最后回退 5s
        if seconds and seconds > 0:
            _duration = int(round(seconds))
        elif num_frames and frame_rate:
            _duration = max(1, round(num_frames / frame_rate))
        elif num_frames:
            _duration = max(1, round(num_frames / 24))
        else:
            _duration = 5

        # 3) fps：优先使用显式传入的 frame_rate；否则默认 24
        _fps = int(frame_rate) if frame_rate and frame_rate > 0 else 24

        # ── 图生视频模式 / 关键帧动画处理（核心修正）
        # 经实测 Agnes `video/generations` 对非平台托管 URL 均失败：
        #   - 外部公开图 URL（维基/示例） -> FAILURE ("Invalid image")
        #   - base64 Data URI -> 永远 NOT_START 不会启动
        # 仅接受 Agnes 自己平台返回的 URL（形如 https://platform-outputs.agnes-ai.space/...jpg）
        # 因此：
        #   1) 先归一化 base64 / Data URI（_normalize_image_input）
        #   2) 把非 Agnes-URL 的图调用一次 images/generations 做 pass-through，拿到平台托管 URL
        #   3) 用该 URL 调 video/generations
        # 同时用第一张参考图的真实宽高修正 aspect_ratio，避免与请求值不一致导致 Internal generation failed

        refs_with_mime: list = []
        if image and isinstance(image, str) and image.strip():
            refs_with_mime.append((image.strip(), image_mime_type or "image/png"))
        if images and isinstance(images, (list, tuple)):
            for idx, img in enumerate(images):
                if img and isinstance(img, str) and img.strip():
                    mime = (
                        image_mime_types[idx]
                        if image_mime_types and idx < len(image_mime_types)
                        else "image/png"
                    )
                    refs_with_mime.append((img.strip(), mime or "image/png"))

        pairs: list = []  # [(要写入 body 的 uri, 真实宽高 or None)]
        if refs_with_mime:
            for raw, _mime in refs_with_mime:
                _uri, _size = self._normalize_image_input(raw, default_mime=_mime)
                if not _uri:
                    continue
                try:
                    final_uri = await self._to_agnes_url(_uri)
                except Exception as e:
                    # 即使转换失败，也继续用归一化的 uri（不阻断任务）
                    logger.warning("[视频生成] 参考图转 Agnes URL 失败: %s", e)
                    final_uri = _uri
                pairs.append((final_uri, _size))

            if pairs and pairs[0][1]:
                w, h = pairs[0][1]
                from math import gcd
                _g = gcd(w, h)
                detected = f"{w // _g}:{h // _g}"
                if detected != _aspect_ratio:
                    logger.info(
                        "[视频生成] 图片真实宽高比 %s（%dx%d）与请求 aspect_ratio=%s 不一致，已自动覆盖",
                        detected, w, h, _aspect_ratio,
                    )
                    _aspect_ratio = detected

        body = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": _aspect_ratio,
            "duration": _duration,
            "fps": _fps,
        }

        if seed is not None:
            body["seed"] = seed

        if pairs:
            extra_body: Dict[str, Any] = {"image": pairs[0][0]}
            if len(pairs) >= 2:
                extra_body["image_end"] = pairs[-1][0]
            body["extra_body"] = extra_body
            logger.info(
                "[视频生成] 图生视频模式: model=%s, image_count=%d, "
                "duration=%ss, aspect_ratio=%s, fps=%d, prompt=%s",
                model, len(pairs), _duration, _aspect_ratio, _fps, prompt[:80],
            )

        # 额外打印一次真正发出去的 body（避免 safe_body 只看前 120 字符造成误判）
        if "extra_body" in body and isinstance(body["extra_body"].get("image"), str):
            img = body["extra_body"]["image"]
            logger.info(
                "[视频生成] 上游请求体摘要: aspect_ratio=%s, image_type=%s, image_len=%d, image_head=%s",
                _aspect_ratio,
                "agnes_url" if "platform-outputs.agnes-ai.space" in img else ("url" if img.lower().startswith("http") else "data_uri"),
                len(img),
                img[:160],
            )

        logger.info(
            "[视频生成] 创建任务: prompt=%s, mode=%s, duration=%ss, "
            "aspect_ratio=%s, fps=%d, seed=%s",
            prompt[:60], mode, _duration, _aspect_ratio, _fps, seed,
        )
        return await self._post(url, body)

    async def _to_agnes_url(self, uri: str) -> str:
        """
        把任意参考图转换成 Agnes 平台托管的 URL。
        - 若是 Agnes 平台 URL (https://platform-outputs.agnes-ai.space/...)，直接返回
        - 否则调用一次 Agnes Image 2.1 Flash 图生图做 pass-through，拿到平台托管 URL
        """
        if not isinstance(uri, str) or not uri.strip():
            return uri
        lowered = uri.strip().lower()
        if lowered.startswith("https://platform-outputs.agnes-ai.space"):
            return uri
        # 如果是其他 Agnes 子域也放过（避免循环）
        if lowered.startswith("https://") and "agnes-ai.space" in lowered:
            return uri

        # 检测原图宽高，决定生成 size（与原图比例一致）
        try:
            _, size = self._normalize_image_input(uri)
            if size:
                w, h = size
                size_str = f"{w}x{h}"
            else:
                size_str = "1024x1024"
        except Exception:
            size_str = "1024x1024"

        logger.info(
            "[视频生成] 参考图先转 Agnes 图片任务：type=%s size=%s",
            "url" if lowered.startswith("http") else "data_uri",
            size_str,
        )
        try:
            # 区分 base64 / URL 传参
            # 使用第一个可用的图片模型做 pass-through
            from app.services.model_registry import get_models_by_type
            image_models = await get_models_by_type("image")
            _pass_model = image_models[0].id if image_models else ""
            if lowered.startswith("http"):
                resp = await self.create_image(
                    prompt="reproduce reference image as is to get its hosted url",
                    model=_pass_model,
                    size=size_str,
                    response_format="url",
                    image_urls=[uri],
                )
            else:
                resp = await self.create_image(
                    prompt="reproduce reference image as is to get its hosted url",
                    model=_pass_model,
                    size=size_str,
                    response_format="url",
                    base64_images=[uri],
                )
            out = None
            try:
                data = resp.get("data", [])
                if isinstance(data, list) and data:
                    out = data[0].get("url")
                if not out and isinstance(resp.get("url"), str):
                    out = resp["url"]
                if not out and resp.get("image"):
                    out = resp["image"]
            except Exception as e:
                logger.warning("[视频生成] 解析图片任务返回失败: %s, 原始返回: %s", e, str(resp)[:200])
            if not out:
                raise RuntimeError(
                    f"参考图转 Agnes 平台 URL 失败，原始返回: {str(resp)[:200]}"
                )
            logger.info("[视频生成] 参考图已转 Agnes URL: %s", out[:160])
            return out
        except Exception as e:
            logger.exception("[视频生成] 参考图转 Agnes 平台 URL 失败: %s", e)
            # 失败时回退：把原始 uri 返回（避免阻断前端提交）
            return uri

    # ---------- 视频任务轮询 ----------
    async def poll_video_status(
        self, video_id: Optional[str] = None, task_id: Optional[str] = None, model_name: str = ""
    ) -> Dict[str, Any]:
        """
        查询视频任务状态。
        优先使用 video_id 走 agnesapi 路径（直接返回视频结果对象，含公开可访问的 remixed_from_video_id），
        否则回退到 /video/generations/{task_id} 路径。
        """
        if video_id:
            try:
                data = await self._get(
                    self.poll_url,
                    params={"video_id": video_id, "model_name": model_name},
                )
                return self._normalize_video_status(data)
            except Exception as e:
                logger.warning(f"[视频轮询] agnesapi 路径失败，尝试回退: {e}")

        if task_id:
            try:
                data = await self._get(f"{self.base_url}/video/generations/{task_id}")
                return self._normalize_video_status(data)
            except Exception as e:
                raise RuntimeError(f"视频状态查询失败: {e}") from e

        raise RuntimeError("缺少 video_id 和 task_id，无法轮询视频状态")

    @staticmethod
    def _aspect_ratio(width: int, height: int) -> str:
        """
        将前端宽高转换为 Agnes Video 文档要求的 aspect_ratio 字符串。
        常见比例保持为标准写法，其他比例用最大公约数约分。
        """
        import math

        if width <= 0 or height <= 0:
            return "16:9"

        ratio = width / height
        common = {
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "1:1": 1,
            "4:3": 4 / 3,
            "3:4": 3 / 4,
            "3:2": 3 / 2,
            "2:3": 2 / 3,
        }
        closest, value = min(common.items(), key=lambda item: abs(item[1] - ratio))
        if abs(value - ratio) < 0.03:
            return closest

        divisor = math.gcd(width, height)
        return f"{width // divisor}:{height // divisor}"

    # ---------- 标准化视频状态 ----------
    def _normalize_video_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Agnes AI 的视频状态响应标准化，便于上层业务逻辑处理。

        Agnes API 响应结构（两轮询路径）：
          - /v1/video/generations/{id} 路径返回：
            {
              "code": "success",
              "data": {
                "status": "SUCCESS" | "NOT_START" | "RUNNING",
                "result_url": "https://...",          ← 需认证，可能 401
                "progress": "100%",
                "data": {                              ← 内层视频生成详情
                  "status": "completed" | "queued",
                  "remixed_from_video_id": "https://...",  ← 公开可访问
                  "progress": 100,
                }
              }
            }
          - /agnesapi?video_id=... 路径直接返回视频结果对象：
            {
              "status": "completed",
              "progress": 100,
              "remixed_from_video_id": "https://...",  ← 公开可访问
              "error": null,
            }

        提取策略：
          - 状态：按优先级检查根级别 → 外层 data → 内层 data.data
          - 视频 URL：优先 remixed_from_video_id（公开可访问），其次 url/result_url
          - 进度：优先数字 progress，其次字符串 progress（如 "100%"）
        """
        outer = data.get("data")
        inner = outer if isinstance(outer, dict) else None
        if isinstance(outer, dict) and "data" in outer:
            inner = outer["data"]

        # 状态提取：根级别 → 外层 → 内层
        raw_status = (
            data.get("status")
            or (isinstance(outer, dict) and outer.get("status"))
            or data.get("state")
            or (isinstance(outer, dict) and outer.get("state"))
            or (isinstance(inner, dict) and inner.get("status"))
            or (isinstance(inner, dict) and inner.get("state"))
            or "unknown"
        )

        status = str(raw_status).lower()
        if status in ("succeeded", "success", "completed", "done", "finished"):
            status = "success"
        elif status in ("pending", "queued", "running", "not_start", "notstart", "in_progress", "inprogress"):
            status = "processing"

        # 视频 URL 提取：按优先级检查多种可能字段
        # 优先使用 remixed_from_video_id（公开可访问），其次是 url/result_url
        # 检查范围：根级别 → 外层 data → 内层 data.data
        video_url = (
            data.get("remixed_from_video_id")           # 根级别（agnesapi 路径）
            or data.get("url")                          # 根级别 url
            or data.get("result_url")                   # 根级别 result_url
            or data.get("video_url")                    # 根级别 video_url
            or (isinstance(outer, dict) and outer.get("remixed_from_video_id"))  # 外层
            or (isinstance(outer, dict) and outer.get("url"))          # 外层 url
            or (isinstance(outer, dict) and outer.get("result_url"))   # 外层 result_url
            or (isinstance(outer, dict) and outer.get("video_url"))    # 外层 video_url
            or (isinstance(inner, dict) and inner.get("remixed_from_video_id"))  # 内层
            or (isinstance(inner, dict) and inner.get("url"))         # 内层 url
            or (isinstance(inner, dict) and inner.get("video_url"))   # 内层 video_url
            or None
        )

        # 确保提取到的值是有效的 URL（以 http 开头），否则丢弃
        if video_url and isinstance(video_url, str) and not video_url.startswith("http"):
            video_url = None

        # 进度提取：优先数字，其次字符串百分比
        progress = None
        for src in (data, outer, inner):
            if src is None:
                continue
            if isinstance(src.get("progress"), (int, float)):
                progress = src["progress"]
                break
            elif isinstance(src.get("progress"), str):
                try:
                    progress = int(src["progress"].replace("%", ""))
                except (ValueError, AttributeError):
                    pass

        # 错误消息提取
        error_msg = None
        if status in ("failed", "error"):
            error_msg = (
                (isinstance(data.get("error"), dict) and data["error"].get("message"))
                or (isinstance(outer, dict) and isinstance(outer.get("error"), dict) and outer["error"].get("message"))
                or (isinstance(inner, dict) and isinstance(inner.get("error"), dict) and inner["error"].get("message"))
                or (isinstance(data.get("error"), str) and data["error"])
                or (isinstance(outer, dict) and isinstance(outer.get("error"), str) and outer["error"])
                or (isinstance(inner, dict) and isinstance(inner.get("error"), str) and inner["error"])
                or (isinstance(outer, dict) and outer.get("fail_reason"))
                or (isinstance(outer, dict) and outer.get("error"))
                or (isinstance(inner, dict) and inner.get("error"))
                or (isinstance(data.get("error"), dict) and data["error"].get("message"))
                or data.get("error_message")
                or data.get("message")
                or "未知错误"
            )

        return {
            "status": status,
            "video_url": video_url,
            "progress": progress,
            "error": error_msg,
            "raw": data,
        }


# 全局单例客户端实例
agnes_client = AgnesAIClient()

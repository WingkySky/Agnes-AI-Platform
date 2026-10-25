# =====================================================
# DeclarativeHttpClient — 声明式 HTTP 渠道客户端
# provider_type=http_custom 时由 provider_registry 构建：
# 管理员在 UI 配置 HTTP 模板（创建端点+请求体模板+点路径响应映射+轮询状态映射），
# 不写 Python 代码即可接入长尾渠道。契约与 AgnesAIClient/AGNSDKClientWrapper 对齐：
#   list_models / create_image / create_video_task / poll_video_status
# 返回形状严格合成消费方硬契约（image_poller/videos 路由/video_poller 的解析逻辑）：
#   图片 {"data":[{"url"|"b64_json"}]}；视频 {id, video_id, task_id}；
#   轮询 {status, video_url, progress, error}（status ∈ success/processing/failed/cancelled，
#   未命中 status_map 保守按 processing 续轮）。
# 复用 UpstreamError（status_code/error_kind——failover 判定的结构化事实载体）与
# 出口记账；网络异常/5xx 指数退避重试同 agnes_client 语义。
# 参考图 v1 仅支持 URL（base64 参考图不支持——长尾渠道主流形态）。
# =====================================================

import asyncio
import logging
import time
from typing import Any

import httpx

from app.services.agnes_client import UpstreamError
from app.services.api_call_log_service import record_api_call
from app.services.declarative_http import (
    extract_path,
    render_and_parse_body,
    render_template,
)
from app.services.error_taxonomy import classify

logger = logging.getLogger("agnes_platform")

LOG_PREFIX = "[声明式渠道]"

REQUEST_TIMEOUT_SEC = 300
CONNECT_TIMEOUT_SEC = 30
MAX_RETRIES = 3
RETRY_INITIAL_BACKOFF = 2.0
_RETRYABLE_STATUS = (502, 503, 504, 520, 521, 522, 523, 524)
_VALID_POLL_STATUS = ("success", "processing", "failed", "cancelled")


class DeclarativeHttpClient:
    """声明式 HTTP 渠道（provider_type=http_custom，模板来自 api_providers.http_config）"""

    def __init__(self, base_url: str, api_key: str, http_config: dict):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.http_config = http_config or {}
        # 记账归因（provider_registry 构建后动态赋值）
        self.provider_id: int | None = None
        self.provider_name: str | None = None
        self._client: httpx.AsyncClient | None = None

    # ---------- 生命周期 ----------

    async def start(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
                http2=False,
            )

    async def shutdown(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def configure(self, base_url: str | None = None, api_key: str | None = None, http_config: dict | None = None):
        """运行时更新配置（registry 检测到 http_config 变更时走整体重建，此方法保留对齐）"""
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        if api_key is not None:
            self.api_key = api_key
        if http_config is not None:
            self.http_config = http_config

    def _action(self, key: str) -> dict:
        cfg = self.http_config.get(key)
        if not isinstance(cfg, dict) or not cfg.get("path"):
            raise UpstreamError(f"该渠道未配置 {key} 模板（请在渠道管理中补全）")
        return cfg

    # ---------- HTTP 基础 ----------

    def _build_url(self, cfg: dict, values: dict[str, Any]) -> str:
        path = render_template(str(cfg.get("path") or ""), values).strip()
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _build_headers(self, cfg: dict) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for key, value in (cfg.get("headers") or {}).items():
            headers[key] = render_template(str(value), {"api_key": self.api_key, "task_id": ""})
        return headers

    async def _record_call(self, call_type: str, model: str, endpoint: str, started: float,
                           status: str, error: BaseException | None = None) -> None:
        """出口记账 best-effort（与 agn_sdk_client._record_call 同范式）"""
        try:
            await record_api_call(
                provider_id=getattr(self, "provider_id", None),
                provider_name=getattr(self, "provider_name", None) or "声明式渠道",
                model=model or None,
                call_type=call_type,
                endpoint=endpoint[:255],
                status=status,
                error_category=classify(error, submitted=False, receipt=False)[0] if error else None,
                error_message=str(error)[:500] if error else None,
                latency_ms=int((time.time() - started) * 1000),
            )
        except Exception:
            pass

    async def _send(self, call_type: str, method: str, url: str, headers: dict[str, str],
                    body: dict | list | None, model: str, timeout_sec: int) -> dict | list:
        """带重试的请求 + 非 2xx 错误翻译 + 出口记账。网络异常/5xx 网关码指数退避重试。"""
        started = time.time()
        last_error: BaseException | None = None
        for attempt in range(MAX_RETRIES):
            try:
                assert self._client is not None
                resp = await self._client.request(
                    method=method, url=url, headers=headers,
                    json=body if method in ("POST", "PUT", "PATCH") else None,
                    timeout=float(timeout_sec),
                )
                if resp.status_code < 400:
                    try:
                        payload = resp.json()
                    except Exception:
                        error = UpstreamError(f"上游响应不是合法 JSON（HTTP {resp.status_code}）")
                        await self._record_call(call_type, model, url, started, "failed", error)
                        raise error
                    await self._record_call(call_type, model, url, started, "success")
                    return payload
                detail = ""
                try:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        err = payload.get("error")
                        detail = str(err.get("message") if isinstance(err, dict) else err) if err else str(
                            payload.get("message") or payload.get("detail") or ""
                        )
                except Exception:
                    detail = resp.text[:200]
                error = UpstreamError(
                    f"上游 API 错误（HTTP {resp.status_code}）：{detail or '无错误详情'}",
                    status_code=resp.status_code,
                    upstream_body=resp.text[:300],
                    error_kind="http",
                )
                if resp.status_code not in _RETRYABLE_STATUS or attempt == MAX_RETRIES - 1:
                    await self._record_call(call_type, model, url, started, "failed", error)
                    raise error
                last_error = error
            except UpstreamError:
                raise
            except httpx.HTTPError as e:  # 网络层异常（连接/读超时等）
                error = UpstreamError(f"网络请求失败：{e}", error_kind="network")
                if attempt == MAX_RETRIES - 1:
                    await self._record_call(call_type, model, url, started, "failed", error)
                    raise error
                last_error = error
            await asyncio.sleep(RETRY_INITIAL_BACKOFF * (2 ** attempt))
        raise last_error or UpstreamError("请求失败")

    # ---------- 模型目录 ----------

    async def list_models(self) -> list[dict[str, Any]]:
        mode = (self.http_config.get("models_mode") or "openai").strip()
        if mode == "static":
            models = self.http_config.get("static_models") or []
            return [
                {"id": m.get("id"), "type": m.get("type") or ""}
                for m in models if isinstance(m, dict) and m.get("id")
            ]
        if mode == "custom":
            cfg = self._action("models_endpoint")
            values = {"task_id": ""}
            payload = await self._send(
                "other", (cfg.get("method") or "GET").upper(),
                self._build_url(cfg, values), self._build_headers(cfg),
                None, "", int(cfg.get("timeout_sec") or 15),
            )
            return self._parse_model_list(payload)
        # openai 兼容：GET {base}/models
        url = f"{self.base_url}/models"
        payload = await self._send("other", "GET", url, self._build_headers({}), None, "", 30)
        return self._parse_model_list(payload)

    @staticmethod
    def _parse_model_list(payload: Any) -> list[dict[str, Any]]:
        """自动适配 {data:[...]} 包裹或裸数组；条目 dict 取 id 字段、str 取本身"""
        items = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return []
        models = []
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                models.append({"id": str(item["id"]), "type": item.get("type") or ""})
            elif isinstance(item, str) and item.strip():
                models.append({"id": item.strip(), "type": ""})
        return models

    # ---------- 图片（同步单 POST） ----------

    async def create_image(self, *, prompt: str, model: str = "", size: str = "1024x1024",
                           response_format: str = "url", base64_image=None, image_url=None,
                           base64_images=None, image_urls=None, mask=None) -> dict[str, Any]:
        cfg = self._action("image_create")
        urls = [u for u in ([image_url] if image_url else []) + list(image_urls or []) if u]
        values: dict[str, Any] = {
            "prompt": prompt or "", "model": model or "", "size": size,
            "image": urls[0] if urls else "", "images": urls,
        }
        body = render_and_parse_body(str(cfg.get("body") or "{}"), values)
        payload = await self._send(
            "image_create", (cfg.get("method") or "POST").upper(),
            self._build_url(cfg, values), self._build_headers(cfg),
            body, model, int(cfg.get("timeout_sec") or 300),
        )
        url = extract_path(payload, str(cfg.get("url_path") or ""))
        b64 = extract_path(payload, str(cfg.get("b64_path") or ""))
        if not url and not b64:
            raise UpstreamError("响应中未找到图片数据（检查 image_create.url_path / b64_path 映射）",
                                upstream_body=str(payload)[:300])
        item: dict[str, Any] = {}
        if url:
            item["url"] = str(url)
        if b64:
            item["b64_json"] = str(b64)
        return {"data": [item]}

    # ---------- 视频（提交 + 轮询两段式） ----------

    async def create_video_task(self, *, prompt: str, model: str = "", num_frames: int | None = None,
                                frame_rate: int | None = None, width: int | None = None,
                                height: int | None = None, aspect_ratio: str | None = None,
                                seconds: float | None = None, negative_prompt: str | None = None,
                                mode: str | None = None, image=None, images=None,
                                image_mime_type=None, image_mime_types=None, seed=None,
                                reference_videos=None, reference_audios=None) -> dict[str, Any]:
        cfg = self._action("video_create")
        url_list = list(images or [])
        if image and image not in url_list:
            url_list.insert(0, image)
        values: dict[str, Any] = {
            "prompt": prompt or "", "model": model or "",
            "width": width or 0, "height": height or 0,
            "seconds": int(seconds) if seconds else 0,
            "aspect_ratio": aspect_ratio or "",
            "negative_prompt": negative_prompt or "",
            "image": url_list[0] if url_list else "", "images": url_list,
        }
        body = render_and_parse_body(str(cfg.get("body") or "{}"), values)
        payload = await self._send(
            "video_create", (cfg.get("method") or "POST").upper(),
            self._build_url(cfg, values), self._build_headers(cfg),
            body, model, int(cfg.get("timeout_sec") or 60),
        )
        task_id = extract_path(payload, str(cfg.get("task_id_path") or ""))
        video_id = extract_path(payload, str(cfg.get("video_id_path") or ""))
        if not task_id and not video_id:
            raise UpstreamError("响应中未找到任务 ID（检查 video_create.task_id_path / video_id_path 映射）",
                                upstream_body=str(payload)[:300])
        task_id = str(task_id) if task_id else str(video_id)
        video_id = str(video_id) if video_id else None
        return {"id": task_id, "task_id": task_id, "video_id": video_id}

    async def poll_video_status(self, *, video_id: str | None = None, task_id: str | None = None,
                                model_name: str = "") -> dict[str, Any]:
        cfg = self._action("video_poll")
        poll_task_id = video_id or task_id or ""
        values = {"task_id": poll_task_id}
        payload = await self._send(
            "video_poll", (cfg.get("method") or "GET").upper(),
            self._build_url(cfg, values), self._build_headers(cfg),
            None, model_name, int(cfg.get("timeout_sec") or 15),
        )
        status_map: dict[str, str] = cfg.get("status_map") or {}
        status_raw = extract_path(payload, str(cfg.get("status_path") or ""))
        status = status_map.get(str(status_raw), "processing")
        if status not in _VALID_POLL_STATUS:
            status = "processing"

        error = extract_path(payload, str(cfg.get("error_path") or ""))
        progress = extract_path(payload, str(cfg.get("progress_path") or ""))
        if isinstance(progress, str):
            digits = "".join(ch for ch in progress if ch.isdigit())
            progress = int(digits) if digits else None
        elif isinstance(progress, (int, float)):
            progress = int(progress)
        else:
            progress = None

        video_url = None
        if status == "success":
            video_url = extract_path(payload, str(cfg.get("video_url_path") or ""))
            if not video_url or not str(video_url).startswith(("http://", "https://")):
                return {"status": "failed", "video_url": None, "progress": None,
                        "error": f"任务标记成功但响应中未找到有效视频地址（检查 video_poll.video_url_path 映射）：{str(video_url)[:120]}"}
            video_url = str(video_url)
        return {
            "status": status,
            "video_url": video_url,
            "progress": min(progress, 99) if isinstance(progress, int) and status != "success" else (100 if status == "success" else progress),
            "error": str(error) if error else None,
            "task_id": poll_task_id,
        }

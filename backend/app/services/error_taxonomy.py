# =====================================================
# 生成错误类目合同（error_taxonomy）
#
# 13 类类目 + 「能否手动重试」语义。前端文案走 i18n（errors.category_<code>），
# 语义标志随 GET /api/config 的 error_categories 下发；本模块是唯一出处。
#
# 重试闸门的核心语义（防重复扣费）：
#   - 「上游已明确判死」的失败 → 按原因归类，重试安全性由类目决定；
#   - 「结果未知」的失败（提交回执丢失 / 查询阶段网络与 5xx / 轮询超时）→
#     一律 submission_uncertain，禁止原地重试（原任务可能仍在途）。
# phase 语义：
#   submitted=False 提交阶段（请求未发出或被明确拒绝）；submitted=True 已提交
#   （查询/轮询阶段，或提交成功后的后续失败）。receipt=True 表示该调用有可
#   凭回执找回的任务（视频异步任务）；False 表示同步调用无回执（图片同步）。
# =====================================================

import re
from typing import Optional, Tuple

# 类目 → canRetry（dict 顺序即 config 下发顺序）
CATEGORIES: dict[str, bool] = {
    "network_transient": True,
    "upstream_server": True,
    "timeout": True,
    "rate_limited": True,
    "result_fetch_failed": True,
    "unknown": True,
    "auth_failed": False,
    "model_missing": False,
    "invalid_params": False,
    "moderation_rejected": False,
    "upstream_quota": False,
    "local_storage_failed": False,
    "submission_uncertain": False,
}

_STATUS_RULES: dict[int, str] = {
    401: "auth_failed",
    403: "auth_failed",
    404: "model_missing",
    429: "rate_limited",
}

# 关键词 → 类目（首个命中生效；作用于错误文案与上游响应体摘要）
_KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (("审核", "moderation", "敏感", "sensitive", "内容安全"), "moderation_rejected"),
    (("余额", "额度", "欠费", "quota", "balance"), "upstream_quota"),
    (("限流", "rate limit", "too many requests", "请求过于频繁"), "rate_limited"),
    (("不存在", "not found", "无权限", "permission denied", "forbidden model"), "model_missing"),
    (("too many images", "invalid", "不合法", "非法", "无效", "参数错误"), "invalid_params"),
    (("超时", "timeout", "timed out"), "timeout"),
    (("网络", "network", "connect"), "network_transient"),
]

_TIMEOUT_PATTERN = re.compile(r"超时|timeout|timed out", re.IGNORECASE)


def can_retry(category: Optional[str]) -> bool:
    """类目 → 能否手动重试；无类目（旧数据）默认可重试（行为不变）"""
    if not category:
        return True
    return CATEGORIES.get(category, True)


def _match_keywords(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    for keywords, category in _KEYWORD_RULES:
        if any(kw in lowered for kw in keywords):
            return category
    return None


def classify_message(message: str, *, submitted: bool) -> str:
    """
    按错误文案归类（上游明确判死的失败文案 / 无结构化异常时）。
    submitted=True 且无关键词命中 → unknown：上游已判死但原因未知，重试安全。
    """
    category = _match_keywords(message or "")
    if category:
        return category
    if submitted:
        return "unknown"
    if _TIMEOUT_PATTERN.search(message or ""):
        return "timeout"
    if re.search(r"网络|connect|network", message or "", re.IGNORECASE):
        return "network_transient"
    return "unknown"


def classify(exc: BaseException, *, submitted: bool = False, receipt: bool = False) -> Tuple[str, str]:
    """
    异常 → (类目, 原始文案)。

    - receipt=False（同步调用，如图片同步生成）：网络/超时按文案归类，可安全重试；
    - receipt=True（视频等异步任务）：一切「结果未知」的失败（提交回执丢失、
      查询阶段网络/5xx/超时）→ submission_uncertain；
    - 上游明确拒绝（4xx/5xx 携带状态码）：按状态码与关键词归类。
    """
    message = str(exc) or exc.__class__.__name__
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "upstream_body", "") or ""
    kind = getattr(exc, "error_kind", "http")

    if kind == "network":
        # 提交回执可能已到达（receipt=True）→ 结果未知；同步调用 → 按文案细分
        if receipt:
            return "submission_uncertain", message
        if _TIMEOUT_PATTERN.search(message):
            return "timeout", message
        return "network_transient", message

    if status is not None:
        if status in _STATUS_RULES:
            return _STATUS_RULES[status], message
        if status >= 500:
            return ("submission_uncertain" if receipt else "upstream_server"), message

    category = _match_keywords(f"{message} {body}")
    if category:
        return category, message

    if status is not None and 400 <= status < 500 and not submitted:
        return "invalid_params", message

    if receipt and submitted:
        return "submission_uncertain", message
    return "unknown", message

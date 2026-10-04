# =====================================================
# 错误类目合同测试（error_taxonomy）
# 表驱动锁死：状态码/关键词/网络类 → 类目；重试闸门语义（防重复扣费）
# =====================================================

import pytest

from app.services.agnes_client import UpstreamError
from app.services.error_taxonomy import CATEGORIES, can_retry, classify, classify_message


def _upstream(message, status=None, kind="http", body=""):
    return UpstreamError(message, status_code=status, upstream_body=body, error_kind=kind)


@pytest.mark.parametrize("exc,expected", [
    # 状态码规则
    (_upstream("认证失败", status=401), "auth_failed"),
    (_upstream("无权限", status=403), "auth_failed"),
    (_upstream("模型不存在", status=404), "model_missing"),
    (_upstream("太快了", status=429), "rate_limited"),
    # 5xx：同步调用（无回执）可重试；异步任务（有回执）结果未知（见 test_classify_receipt_semantics）
    (_upstream("上游网关错误", status=502), "upstream_server"),
    # 网络类
    (_upstream("响应超时", kind="network"), "timeout"),
    (_upstream("连接失败", kind="network"), "network_transient"),
    # 关键词（message + body）
    (_upstream("请求被拒绝", status=400, body='{"error": "content moderation violation"}'), "moderation_rejected"),
    (_upstream("任务创建失败", status=400, body="账户余额不足"), "upstream_quota"),
    (_upstream("参数错误：too many images", status=400), "invalid_params"),
])
def test_classify_submit_phase(exc, expected):
    category, _ = classify(exc, submitted=False, receipt=False)
    assert category == expected


def test_classify_receipt_semantics():
    # 有回执的任务：提交回执丢失/查询 5xx → 一律 submission_uncertain（防重复扣费）
    assert classify(UpstreamError("网络断开", error_kind="network"), submitted=False, receipt=True)[0] == "submission_uncertain"
    assert classify(_upstream("网关错误", status=502), submitted=False, receipt=True)[0] == "submission_uncertain"
    assert classify(RuntimeError("未知错误"), submitted=True, receipt=True)[0] == "submission_uncertain"


def test_classify_message_upstream_verdict():
    # 上游明确判死的失败文案 → 按关键词归类
    assert classify_message("内容包含敏感词，无法生成", submitted=True) == "moderation_rejected"
    assert classify_message("渠道额度用尽", submitted=True) == "upstream_quota"
    # 判死但原因未知 → unknown（重试安全）
    assert classify_message("生成失败", submitted=True) == "unknown"
    # 提交阶段文案兜底
    assert classify_message("请求超时", submitted=False) == "timeout"


def test_can_retry_gate():
    assert can_retry(None) is True  # 旧数据无类目：行为不变
    assert can_retry("unknown") is True
    assert can_retry("rate_limited") is True
    assert can_retry("moderation_rejected") is False
    assert can_retry("submission_uncertain") is False
    assert can_retry("not-a-category") is True  # 未知编码兜底可重试


def test_category_contract_shape():
    # 13 类且 submission_uncertain 永远不可原地重试
    assert len(CATEGORIES) == 13
    assert CATEGORIES["submission_uncertain"] is False
    assert all(isinstance(v, bool) for v in CATEGORIES.values())

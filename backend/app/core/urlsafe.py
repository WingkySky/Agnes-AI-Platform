# =====================================================
# URL 安全工具（防 SSRF）
# is_safe_url：仅允许 http/https，禁止内网/环回/链路本地地址。
# 图片代理与画布合成等服务端抓取远程资源的入口统一使用。
# 注意：基于主机名字面量，不做 DNS 解析（DNS rebinding 残余风险由
# 出口网络策略兜底）；重定向目标必须逐跳重新校验。
# =====================================================

from urllib.parse import urlparse


def is_safe_url(url: str) -> bool:
    """校验 URL 是否安全：必须是 http/https，且不是内网地址"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    # 禁止 localhost / 127.x / 10.x / 192.168.x / 169.254.x / ::1
    host = parsed.hostname.lower()
    if host in ("localhost", "::1"):
        return False
    if host.startswith(("127.", "10.", "192.168.", "169.254.")):
        return False
    return True

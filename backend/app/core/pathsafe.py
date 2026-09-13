# =====================================================
# 路径安全工具
# ensure_within：realpath 规范化 + 包含校验，杜绝相对成分
# （../、含 / 的扩展名、绝对路径等）逃出基准目录。
# 所有服务端落盘点统一使用该模式。
# =====================================================

import os


def ensure_within(base: str, *parts: str) -> str:
    """把 parts 拼到 base 下并规范化；结果逃出 base 时抛 ValueError"""
    base_real = os.path.realpath(base)
    path_real = os.path.realpath(os.path.join(base_real, *parts))
    if path_real != base_real and not path_real.startswith(base_real + os.sep):
        raise ValueError(f"路径越界：{parts!r}")
    return path_real

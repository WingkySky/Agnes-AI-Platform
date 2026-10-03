# =====================================================
# 首启初始化 Schema
# =====================================================

from pydantic import BaseModel, Field, field_validator


class SetupBootstrapRequest(BaseModel):
    """首启创建首个管理员请求体（仅实例无管理员时可用，免登录）"""
    username: str = Field(..., min_length=3, max_length=32, description="管理员用户名（3~32 字符）")
    password: str = Field(..., min_length=6, max_length=64, description="管理员密码（6~64 字符）")

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        # 与注册规则一致：字母数字 + 下划线 + 中文
        if not all(ch.isalnum() or ch == "_" or ord(ch) > 127 for ch in v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v

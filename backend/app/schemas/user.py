# =====================================================
# 用户 / 认证相关 Schema
# - 注册请求、登录请求、token 响应、当前用户信息响应
# - 用户管理（列表、修改角色/积分、启停用）
# - 积分规则（查询、更新）
# =====================================================

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# =====================================================
# 一、请求体
# =====================================================

class RegisterRequest(BaseModel):
    """注册请求体"""
    username: str = Field(..., min_length=3, max_length=32, description="用户名（3~32 字符）")
    email: Optional[str] = Field(default=None, max_length=128, description="邮箱（可选）")
    password: str = Field(..., min_length=6, max_length=64, description="密码（6~64 字符）")

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        # 允许字母数字 + 下划线 + 中文
        if not all(ch.isalnum() or ch == "_" or ord(ch) > 127 for ch in v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v


class LoginRequest(BaseModel):
    """登录请求体"""
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=64, description="密码")


# =====================================================
# 二、响应体
# =====================================================

class TokenResponse(BaseModel):
    """登录/注册成功后返回的 token 响应"""
    access_token: str = Field(..., description="JWT access token（前端需存入 localStorage，并以 Authorization: Bearer <token> 发送）")
    token_type: str = Field(default="bearer", description="token 类型，固定为 bearer")
    expires_in: int = Field(..., description="token 有效期（秒）")


class UserInfoResponse(BaseModel):
    """当前用户信息（不含 password_hash）"""
    id: int
    username: str
    email: Optional[str] = None
    credits: int
    role: str           # admin / user
    is_active: bool
    is_admin: bool      # 向后兼容：等价于 role == 'admin'
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserCreditsResponse(BaseModel):
    """用户积分查询响应"""
    credits: int


# =====================================================
# 三、管理员：用户管理接口 Schema
# =====================================================

class UserAdminRow(BaseModel):
    """管理员在用户列表页看到的一行"""
    id: int
    username: str
    email: Optional[str] = None
    credits: int
    role: str
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应"""
    items: List[UserAdminRow]
    total: int


class UpdateRoleRequest(BaseModel):
    """修改用户角色"""
    role: str = Field(..., description="新角色：admin / user")

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("admin", "user"):
            raise ValueError("role 仅可取值 admin / user")
        return v


class UpdateCreditsRequest(BaseModel):
    """调整用户积分"""
    credits: int = Field(..., ge=0, description="新的积分余额（>=0）")


class UpdateActiveRequest(BaseModel):
    """启用 / 禁用用户"""
    is_active: bool


# =====================================================
# 四、积分规则 Schema
# =====================================================

class CreditRuleResponse(BaseModel):
    """一条积分规则"""
    id: int
    rule_key: str
    name: str
    value: int
    description: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreditRuleUpdateRequest(BaseModel):
    """修改一条积分规则"""
    name: Optional[str] = Field(default=None, description="中文名称（可选）")
    value: int = Field(..., ge=0, description="积分值（>=0）")
    description: Optional[str] = Field(default=None, description="说明（可选）")

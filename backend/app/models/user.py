# =====================================================
# User 模型 — 用户账户与积分
# 包含：用户基本信息、密码哈希、积分余额、角色
# 设计要点：
#   - password_hash 存储 bcrypt 哈希值，从不存明文
#   - credits 存储当前可用积分（生成任务从中扣除）
#   - role 取值 ROLE_ADMIN / ROLE_USER，保留 is_admin 做向后兼容
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from app.core.database import Base

# 角色常量（前端/后端统一使用）
ROLE_ADMIN = "admin"   # 超级管理员：可访问配置页面、修改用户、修改积分规则
ROLE_USER = "user"     # 普通用户：可登录、生成、查看自己的记录

# 角色展示名
ROLE_LABELS = {
    ROLE_ADMIN: "超级管理员",
    ROLE_USER: "普通用户",
}


class User(Base):
    """
    用户表

    字段说明：
    - id: 主键
    - username: 用户名（唯一）
    - email: 邮箱（可选，唯一）
    - password_hash: bcrypt 哈希后的密码（从不存明文）
    - credits: 积分余额
    - role: 用户角色（admin / user）
    - is_active: 是否启用（禁用后无法登录）
    - is_admin: 向后兼容字段，等价于 role == 'admin'
    - created_at: 注册时间
    - last_login_at: 最近一次登录时间
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    # 积分余额（用于生成任务消耗）
    credits = Column(Integer, default=0, nullable=False)

    # 角色：admin / user
    role = Column(String(16), default=ROLE_USER, nullable=False, index=True)

    # 权限标记
    is_active = Column(Boolean, default=True, nullable=False)
    # 向后兼容：若 role == ROLE_ADMIN，则 is_admin 自动为 True（也允许通过修改 is_admin 间接改 role）
    is_admin = Column(Boolean, default=False, nullable=False)

    # 时间字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # ---------- 辅助方法 ----------

    @property
    def effective_is_admin(self) -> bool:
        """统一判断是否为管理员：role == 'admin' 或 is_admin == True"""
        return (self.role == ROLE_ADMIN) or bool(self.is_admin)

    def sync_role_and_is_admin(self) -> None:
        """
        将 role 与 is_admin 做一次同步：
        - 若 is_admin 为 True，则 role 强制为 admin
        - 若 role 为 admin，则 is_admin 强制为 True
        用于首次创建或修改后保持一致性。
        """
        if self.is_admin:
            self.role = ROLE_ADMIN
        if self.role == ROLE_ADMIN:
            self.is_admin = True

    def to_dict(self) -> dict:
        """对外暴露的 JSON 结构（不含 password_hash）"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "credits": self.credits,
            "role": self.role,
            "is_active": self.is_active,
            "is_admin": self.effective_is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }

# =====================================================
# 角色与权限模型
# - RBAC：角色 (Role) 包含一组权限点 (permissions JSON)
# - 用户通过 role_id 关联一个角色
# - 权限点用冒号分隔的字符串，如 "plaza:moderate" "user:manage"
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.core.database import Base


# ---------- 权限点常量定义 ----------
# 命名规范：模块:操作，如 plaza:moderate 表示广场内容审核权限
PERM_USER_MANAGE = "user:manage"               # 用户管理（增删改、积分、角色分配）
PERM_ROLE_MANAGE = "role:manage"               # 角色管理（创建/修改/删除角色、配置权限）
PERM_CREDIT_MANAGE = "credit:manage"           # 积分规则管理
PERM_PLAZA_MODERATE = "plaza:moderate"         # 广场内容审核（屏蔽/恢复作品）
PERM_MODERATION_CONFIG = "moderation:config"   # 审核配置管理（敏感词、审核规则等）
PERM_WATERMARK_MANAGE = "watermark:manage"     # 水印配置管理
PERM_CONTENT_GENERATE = "content:generate"     # 内容生成（图片/视频，普通用户默认拥有）
PERM_PLAZA_SHARE = "plaza:share"               # 分享作品到广场

# 内置角色权限配置
DEFAULT_ROLES = [
    {
        "name": "admin",
        "display_name": "超级管理员",
        "description": "拥有全部权限",
        "is_system": True,
        "permissions": [
            PERM_USER_MANAGE,
            PERM_ROLE_MANAGE,
            PERM_CREDIT_MANAGE,
            PERM_PLAZA_MODERATE,
            PERM_MODERATION_CONFIG,
            PERM_WATERMARK_MANAGE,
            PERM_CONTENT_GENERATE,
            PERM_PLAZA_SHARE,
        ],
    },
    {
        "name": "moderator",
        "display_name": "审核员",
        "description": "负责内容审核，可管理广场作品和审核配置",
        "is_system": True,
        "permissions": [
            PERM_PLAZA_MODERATE,
            PERM_MODERATION_CONFIG,
            PERM_CONTENT_GENERATE,
            PERM_PLAZA_SHARE,
        ],
    },
    {
        "name": "user",
        "display_name": "普通用户",
        "description": "普通注册用户，可生成内容和分享到广场",
        "is_system": True,
        "permissions": [
            PERM_CONTENT_GENERATE,
            PERM_PLAZA_SHARE,
        ],
    },
]


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(32), unique=True, index=True, nullable=False)    # 角色英文标识，如 admin / user
    display_name = Column(String(64), nullable=False)                     # 显示名称
    description = Column(Text, nullable=True)
    permissions = Column(JSON, nullable=False, default=list)             # 权限点数组，如 ["plaza:moderate", "user:manage"]
    is_system = Column(Integer, default=0, nullable=False, index=True)  # 是否系统内置角色（1=是，不可删除）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "permissions": self.permissions or [],
            "is_system": bool(self.is_system),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def has_permission(self, perm: str) -> bool:
        """检查角色是否拥有指定权限"""
        if not self.permissions:
            return False
        # 支持通配符：admin 角色的 * 权限或模块级通配（如 "plaza:*"）
        if "*" in self.permissions:
            return True
        if perm in self.permissions:
            return True
        # 模块级通配检查：请求 plaza:moderate，拥有 plaza:* 即通过
        parts = perm.split(":")
        if len(parts) >= 2 and f"{parts[0]}:*" in self.permissions:
            return True
        return False

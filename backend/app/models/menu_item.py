# =====================================================
# 菜单项模型
# - 存储顶部导航和侧边栏菜单配置
# - 支持父子层级关系（parent_id 实现树结构）
# - 支持排序、显示/隐藏、图标配置
# - 菜单位置：top(顶部导航) / sidebar(侧边栏)
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


# 默认菜单配置（首次启动时初始化）
DEFAULT_MENU_ITEMS = [
    # ---------- 顶部导航 ----------
    {"key": "chat", "label_key": "nav.chat", "icon": "ChatDotRound", "path": "/chat", "position": "top", "sort_order": 1, "is_visible": True},
    {"key": "images", "label_key": "nav.images", "icon": "Picture", "path": "/images", "position": "top", "sort_order": 2, "is_visible": True},
    {"key": "videos", "label_key": "nav.videos", "icon": "VideoPlay", "path": "/videos", "position": "top", "sort_order": 3, "is_visible": True},
    {"key": "canvas", "label_key": "nav.canvas", "icon": "Grid", "path": "/canvas", "position": "top", "sort_order": 4, "is_visible": True},
    {"key": "plaza", "label_key": "nav.plaza", "icon": "Histogram", "path": "/plaza", "position": "top", "sort_order": 5, "is_visible": True},
    # ---------- 侧边栏 - 创作工具分组 ----------
    {"key": "sidebar-create", "label_key": "sidebar.groups.create", "path": "", "position": "sidebar", "group_key": "create", "sort_order": 1, "is_group": True, "is_visible": True},
    {"key": "create-chat", "label_key": "nav.chat", "icon": "ChatDotRound", "path": "/chat", "position": "sidebar", "group_key": "create", "sort_order": 1, "is_visible": True},
    {"key": "create-images", "label_key": "nav.images", "icon": "Picture", "path": "/images", "position": "sidebar", "group_key": "create", "sort_order": 2, "is_visible": True},
    {"key": "create-videos", "label_key": "nav.videos", "icon": "VideoPlay", "path": "/videos", "position": "sidebar", "group_key": "create", "sort_order": 3, "is_visible": True},
    {"key": "create-canvas", "label_key": "nav.canvas", "icon": "Grid", "path": "/canvas", "position": "sidebar", "group_key": "create", "sort_order": 4, "is_visible": True},
    # ---------- 侧边栏 - 个人中心分组 ----------
    {"key": "sidebar-personal", "label_key": "sidebar.groups.personal", "path": "", "position": "sidebar", "group_key": "personal", "sort_order": 2, "is_group": True, "is_visible": True},
    {"key": "personal-history", "label_key": "nav.history", "icon": "Clock", "path": "/history", "position": "sidebar", "group_key": "personal", "sort_order": 1, "is_visible": True},
    {"key": "personal-credits", "label_key": "nav.credits", "icon": "Coin", "path": "/credits", "position": "sidebar", "group_key": "personal", "sort_order": 2, "is_visible": True},
    {"key": "personal-profile", "label_key": "userMenu.profile", "icon": "UserFilled", "path": "/profile", "position": "sidebar", "group_key": "personal", "sort_order": 3, "is_visible": True},
    {"key": "personal-preferences", "label_key": "userMenu.preferences", "icon": "StarFilled", "path": "/preferences", "position": "sidebar", "group_key": "personal", "sort_order": 4, "is_visible": True},
    # ---------- 侧边栏 - 社区分组 ----------
    {"key": "sidebar-community", "label_key": "sidebar.groups.community", "path": "", "position": "sidebar", "group_key": "community", "sort_order": 3, "is_group": True, "is_visible": True},
    {"key": "community-plaza", "label_key": "nav.plaza", "icon": "Histogram", "path": "/plaza", "position": "sidebar", "group_key": "community", "sort_order": 1, "is_visible": True},
    # ---------- 侧边栏 - 管理分组（仅管理员可见，前端根据权限控制显示） ----------
    {"key": "sidebar-admin", "label_key": "sidebar.groups.admin", "path": "", "position": "sidebar", "group_key": "admin", "sort_order": 4, "is_group": True, "is_visible": True, "require_admin": True},
    {"key": "admin-models", "label_key": "nav.settings", "icon": "Setting", "path": "/admin/models", "position": "sidebar", "group_key": "admin", "sort_order": 1, "is_visible": True, "require_admin": True},
    {"key": "admin-users", "label_key": "nav.usersAdmin", "icon": "User", "path": "/admin/users", "position": "sidebar", "group_key": "admin", "sort_order": 2, "is_visible": True, "require_admin": True},
    {"key": "admin-roles", "label_key": "nav.roleManage", "icon": "UserFilled", "path": "/admin/roles", "position": "sidebar", "group_key": "admin", "sort_order": 3, "is_visible": True, "require_admin": True},
    {"key": "admin-credit-rules", "label_key": "nav.creditRules", "icon": "Coin", "path": "/admin/credit-rules", "position": "sidebar", "group_key": "admin", "sort_order": 4, "is_visible": True, "require_admin": True},
    {"key": "admin-moderation", "label_key": "nav.moderation", "icon": "Histogram", "path": "/admin/moderation", "position": "sidebar", "group_key": "admin", "sort_order": 5, "is_visible": True, "require_admin": True},
    {"key": "admin-sensitive-words", "label_key": "nav.sensitiveWords", "icon": "ChatDotRound", "path": "/admin/sensitive-words", "position": "sidebar", "group_key": "admin", "sort_order": 6, "is_visible": True, "require_admin": True},
    {"key": "admin-watermark", "label_key": "nav.watermarkConfig", "icon": "Picture", "path": "/admin/watermark", "position": "sidebar", "group_key": "admin", "sort_order": 7, "is_visible": True, "require_admin": True},
    {"key": "admin-email", "label_key": "nav.emailConfig", "icon": "Message", "path": "/admin/email", "position": "sidebar", "group_key": "admin", "sort_order": 8, "is_visible": True, "require_admin": True},
    {"key": "admin-menus", "label_key": "nav.menuAdmin", "icon": "Grid", "path": "/admin/menus", "position": "sidebar", "group_key": "admin", "sort_order": 9, "is_visible": True, "require_admin": True},
]


class MenuItem(Base):
    """菜单项配置表"""
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True, nullable=False)               # 菜单唯一标识
    label_key = Column(String(128), nullable=False)                                  # i18n 文案 key（如 nav.chat）
    icon = Column(String(64), nullable=True)                                         # Element Plus 图标组件名
    path = Column(String(255), nullable=True, default="")                            # 路由路径
    position = Column(String(32), nullable=False, default="top", index=True)         # 位置：top(顶部) / sidebar(侧边栏)
    group_key = Column(String(64), nullable=True, index=True)                        # 所属分组 key（侧边栏用）
    parent_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)          # 父菜单 ID（顶部下拉子菜单用）
    sort_order = Column(Integer, nullable=False, default=0)                          # 排序序号（越小越靠前）
    is_visible = Column(Boolean, nullable=False, default=True)                       # 是否显示
    is_group = Column(Boolean, nullable=False, default=False)                        # 是否为分组标题
    require_admin = Column(Boolean, nullable=False, default=False)                   # 是否仅管理员可见
    children = relationship("MenuItem", backref="parent", remote_side=[id], lazy="joined")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_menu_position", "position"),
        Index("idx_menu_group", "group_key"),
        Index("idx_menu_sort", "position", "group_key", "sort_order"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "label_key": self.label_key,
            "icon": self.icon,
            "path": self.path,
            "position": self.position,
            "group_key": self.group_key,
            "parent_id": self.parent_id,
            "sort_order": self.sort_order,
            "is_visible": self.is_visible,
            "is_group": self.is_group,
            "require_admin": self.require_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

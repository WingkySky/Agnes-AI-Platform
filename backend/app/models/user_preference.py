# =====================================================
# UserPreference 模型 — 用户偏好设置
#
# 每个用户一条记录，所有偏好项以 JSON 存储在同一行。
# 好处：新增偏好项不需要改表结构，直接读写 JSON key 即可。
#
# 偏好项分类：
#   - generation : 生成相关（默认模型 / 默认比例 / 自动复制提示词）
#   - download   : 下载相关（自动下载 / 下载目录 / 命名规则 / 分类方式）
#   - ui         : 界面相关（主题 / 画布网格）
#   - notification: 通知相关（完成提示音）
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, JSON, DateTime, ForeignKey

from app.core.database import Base


# =====================================================
# 偏好项默认值（用户首次注册时写入）
# =====================================================
DEFAULT_PREFERENCES = {
    # 生成偏好
    "generation": {
        "default_model_id": "",
        "default_aspect_ratio": "1:1",
        "auto_copy_prompt": True,
        "default_image_count": 1,
    },
    # 下载偏好
    "download": {
        "auto_download": False,
        "download_directory": "",          # 空=默认下载目录；File System Access API 支持用户指定目录
        "file_naming_pattern": "{type}_{timestamp}",  # 支持 {type}/{timestamp}/{model}/{uuid}
        "classify_by": "type",             # type=按图片/视频分类，date=按日期分类，none=不分类
        "default_format": "original",       # original / png / jpg / webp
    },
    # 界面偏好
    "ui": {
        "theme": "dark",                   # dark / light / system
        "canvas_grid_visible": True,
        "canvas_grid_size": 20,
        "canvas_snap_to_grid": False,
    },
    # 通知偏好
    "notification": {
        "sound_on_complete": True,
        "browser_notification": False,
    },
}


class UserPreference(Base):
    """
    用户偏好设置表（每用户一行）

    字段说明：
    - user_id    : 关联用户 ID（唯一索引，一对一）
    - preferences: JSON 存储所有偏好项（结构见 DEFAULT_PREFERENCES）
    - created_at : 首次创建时间
    - updated_at : 最后修改时间
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    preferences = Column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_PREFERENCES.copy(),
        comment="所有偏好项的 JSON 结构",
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def get(self, category: str, key: str, default=None):
        """读取指定分类下的偏好值（不存在时返回 default）"""
        cat = self.preferences.get(category, {}) if self.preferences else {}
        return cat.get(key, default)

    def set(self, category: str, key: str, value) -> None:
        """写入指定分类下的偏好值"""
        if not self.preferences:
            self.preferences = DEFAULT_PREFERENCES.copy()
        if category not in self.preferences:
            self.preferences[category] = {}
        self.preferences[category][key] = value
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """对外暴露的 JSON 结构"""
        return {
            "user_id": self.user_id,
            "preferences": self.preferences,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

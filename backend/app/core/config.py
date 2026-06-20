# =====================================================
# 后端核心配置
# 使用 pydantic-settings 从 .env 文件和环境变量中加载配置
# 优先级：环境变量 > .env 文件 > 默认值
# =====================================================

from typing import List, Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import json


class Settings(BaseSettings):
    """
    全局配置类
    所有字段均可通过环境变量覆盖
    """

    # model_config: pydantic-settings 2.x 的标准写法
    # extra="ignore" 表示忽略 .env 中未在此类中定义的变量
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Agnes AI API 配置 ----------
    agnes_api_key: str = Field(
        default="",
        description="Agnes AI API Key（从 platform.agnes-ai.com 获取）",
    )
    agnes_api_base_url: str = Field(
        default="https://apihub.agnes-ai.com/v1",
        description="Agnes AI API 基础地址",
    )
    agnes_api_poll_url: str = Field(
        default="https://apihub.agnes-ai.com/agnesapi",
        description="Agnes AI 异步任务轮询专用接口",
    )

    # ---------- 模型配置 ----------
    available_models: str = Field(
        default="",
        description="可用模型 ID 列表（逗号分隔，可选），仅作 API 不可用时的回退",
    )
    model_overrides: str = Field(
        default="{}",
        description="模型属性覆盖（JSON 字符串），当自动推断不准确时手动指定",
    )

    # ---------- 数据库配置 ----------
    # SQLite：sqlite:///./agnes_platform.db
    # PostgreSQL：postgresql://user:pass@host:5432/dbname
    database_url: str = Field(
        default="sqlite:///./agnes_platform.db",
        description="数据库连接字符串（SQLite / PostgreSQL / MySQL）",
    )

    # ---------- 服务配置 ----------
    frontend_origins: List[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="允许跨域访问的前端来源列表",
    )
    backend_port: int = Field(default=8000, description="后端服务端口")

    # ---------- 业务参数 ----------
    max_upload_size_mb: int = Field(default=10, description="单张图片上传大小限制（MB）")
    video_poll_interval_sec: int = Field(default=5, description="视频任务轮询间隔（秒）")
    video_poll_timeout_sec: int = Field(default=600, description="视频任务轮询超时（秒）")

    # ---------- 日志配置 ----------
    log_level: str = Field(
        default="INFO",
        description="全局日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）",
    )
    log_file_enabled: bool = Field(
        default=True,
        description="是否启用文件日志（生产环境建议开启）",
    )
    log_dir: str = Field(
        default="./logs",
        description="日志文件存储目录",
    )
    log_max_bytes: int = Field(
        default=10_485_760,
        description="单个日志文件最大字节数（默认 10MB）",
    )
    log_backup_count: int = Field(
        default=5,
        description="日志文件轮转备份数量",
    )
    log_json_enabled: bool = Field(
        default=True,
        description="是否启用 JSON 格式错误日志（WARNING 及以上输出 JSON，便于 Agent 解析）",
    )

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_origins(cls, v):
        """
        支持以逗号分隔的字符串形式配置多个来源
        例如："http://localhost:5173,http://127.0.0.1:5173"
        """
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("model_overrides", mode="before")
    @classmethod
    def parse_model_overrides(cls, v):
        """确保 model_overrides 是合法 JSON 字符串"""
        if isinstance(v, str):
            json.loads(v)  # 校验格式
        return v

    @property
    def max_upload_bytes(self) -> int:
        """将 MB 转换为字节数，用于请求体大小校验"""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def model_id_list(self) -> List[str]:
        """解析 available_models 为模型 ID 列表"""
        return [m.strip() for m in self.available_models.split(",") if m.strip()]

    @property
    def model_overrides_dict(self) -> Dict[str, Any]:
        """解析 model_overrides JSON 为字典"""
        try:
            return json.loads(self.model_overrides) if self.model_overrides else {}
        except (json.JSONDecodeError, TypeError):
            return {}


# 全局单例配置实例
settings = Settings()

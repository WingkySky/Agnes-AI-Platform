# =====================================================
# 后端核心配置
# 使用 pydantic-settings 从 .env 文件和环境变量中加载配置
# 优先级：环境变量 > .env 文件 > 默认值
#
# 注意：API Key / Base URL / 模型列表等运行时配置
# 已迁移到数据库（api_providers / model_definitions 表），
# 由前端配置页面管理。此处仅保留首次启动初始化用的引导配置。
# =====================================================

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


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

    # ---------- Agnes AI API 引导配置（仅首次启动初始化默认 Provider 用） ----------
    # 启动后这些值会被写入数据库 api_providers 表，后续在前端配置页修改
    agnes_api_key: str = Field(
        default="",
        description="Agnes AI API Key（仅首次启动初始化用，后续在前端配置页管理）",
    )
    agnes_api_base_url: str = Field(
        default="https://apihub.agnes-ai.com/v1",
        description="Agnes AI API 基础地址（仅首次启动初始化用）",
    )
    agnes_api_poll_url: str = Field(
        default="https://apihub.agnes-ai.com/agnesapi",
        description="Agnes AI 异步任务轮询专用接口（仅首次启动初始化用）",
    )

    # ---------- API Key 加密密钥 ----------
    # 用于加密数据库中存储的 Provider API Key（Fernet 对称加密）
    # 生产环境务必配置为随机字符串
    encryption_key: str = Field(
        default="",
        description="API Key 加密密钥（任意长度字符串，用于 Fernet 加密 Provider 的 api_key）",
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

    # ---------- JWT 与用户认证 ----------
    jwt_secret: str = Field(
        default="change-me-please-this-is-not-secure",
        description="JWT 签名密钥（生产环境请务必修改为随机字符串）",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=60 * 24 * 7,
        description="JWT access token 默认有效期（分钟），默认 7 天",
    )
    new_user_default_credits: int = Field(
        default=500,
        description="新注册用户默认赠送的积分",
    )

    # ---------- 邮件服务配置（用于发送验证码等） ----------
    smtp_host: str = Field(
        default="",
        description="SMTP 服务器地址（留空则不启用邮件功能）",
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP 服务器端口（默认 587）",
    )
    smtp_user: str = Field(
        default="",
        description="SMTP 用户名",
    )
    smtp_password: str = Field(
        default="",
        description="SMTP 密码",
    )
    smtp_from_email: str = Field(
        default="",
        description="发件人邮箱地址",
    )
    smtp_from_name: str = Field(
        default="Agnes AI Platform",
        description="发件人显示名称",
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="是否使用 TLS 加密",
    )

    # ---------- 验证码配置 ----------
    captcha_expire_seconds: int = Field(
        default=300,
        description="图片验证码有效期（秒），默认 5 分钟",
    )
    email_code_expire_seconds: int = Field(
        default=600,
        description="邮箱验证码有效期（秒），默认 10 分钟",
    )
    email_code_resend_interval: int = Field(
        default=60,
        description="邮箱验证码重发间隔（秒），默认 60 秒",
    )

    # ---------- 对象存储配置（用于资源转存，S3 兼容协议） ----------
    # 支持任何 S3 兼容服务商：Cloudflare R2 / AWS S3 / MinIO / 阿里云 OSS（S3 兼容模式）
    # 未配置时跳过转存，所有 URL 走原始上游
    storage_backend_type: str = Field(
        default="s3",
        description="对象存储后端类型：s3（兼容 R2/MinIO/OSS）/ 未来扩展 local 等",
    )
    storage_endpoint: str = Field(
        default="",
        description="S3 兼容 endpoint，如 https://<account_id>.r2.cloudflarestorage.com",
    )
    storage_access_key_id: str = Field(
        default="",
        description="对象存储 Access Key ID",
    )
    storage_secret_access_key: str = Field(
        default="",
        description="对象存储 Secret Access Key",
    )
    storage_bucket: str = Field(
        default="",
        description="对象存储桶名",
    )
    storage_region: str = Field(
        default="auto",
        description="region，R2 用 auto，AWS S3 用具体 region 如 us-east-1",
    )
    storage_public_url_base: str = Field(
        default="",
        description="公共访问基址，如 https://pub-xxx.r2.dev 或绑定的自定义域名",
    )
    storage_video_upload_timeout_sec: int = Field(
        default=120,
        description="视频上传超时（秒）",
    )
    storage_image_upload_timeout_sec: int = Field(
        default=30,
        description="图片上传超时（秒）",
    )
    storage_migrate_retry_max: int = Field(
        default=2,
        description="转存失败重试次数",
    )
    storage_migrate_retry_interval_sec: int = Field(
        default=5,
        description="转存重试间隔（秒）",
    )

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

    @property
    def max_upload_bytes(self) -> int:
        """将 MB 转换为字节数，用于请求体大小校验"""
        return self.max_upload_size_mb * 1024 * 1024


# 全局单例配置实例
settings = Settings()

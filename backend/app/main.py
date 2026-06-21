# =====================================================
# Agnes AI Platform - 后端入口（全异步架构）
#
# 架构概览：
#   ┌──────────────────────────────────────────┐
#   │  FastAPI 应用层                           │
#   │  - lifespan：启动/关闭时初始化/释放资源   │
#   │  - 路由：images / videos / history / config│
#   │  - CORS 中间件：允许前端跨域              │
#   └────────────────────┬─────────────────────┘
#                        │ HTTP (async)
#   ┌────────────────────▼─────────────────────┐
#   │  Service 层（业务逻辑）                    │
#   │  - agnes_client：httpx.AsyncClient（连接池）│
#   │  - video_poller：独立 asyncio.Task 轮询   │
#   └────────────────────┬─────────────────────┘
#                        │ async/await
#   ┌────────────────────▼─────────────────────┐
#   │  Database 层                              │
#   │  - 异步 SQLAlchemy 2.0 engine + AsyncSession │
#   │  - SQLite / PostgreSQL（可切换）           │
#   └──────────────────────────────────────────┘
#
# 异步特性：
#   - 图片生成：await 等待 Agnes AI，不阻塞事件循环
#   - 视频生成：创建任务后立即返回，后台独立 Task 轮询
#   - 数据库：所有数据库操作均为 AsyncSession + await
#   - HTTP：httpx.AsyncClient 持久化连接池
#   - 图片与视频任务互不干扰，独立调度
# =====================================================

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine, async_engine
from app.core.logging import setup_logging
from app.middleware.request_id import RequestIdMiddleware
from app.routes import images, videos, history as history_route, config as config_route, chat as chat_route, auth as auth_route
from app.routes import logs as logs_route
from app.routes import providers as providers_route
from app.routes import admin as admin_route
from app.routes import credits as credits_route
from app.routes import proxy as proxy_route
from app.services.video_poller import poller_manager
from app.services.image_poller import image_poller_manager
from app.services.agnes_client import agnes_client
from app.services.provider_registry import provider_registry

# ---------- 日志配置（替换原 logging.basicConfig）----------
# 使用自定义日志系统：控制台 + 文件轮转 + JSON 错误日志 + Request ID 追踪
logger = setup_logging(
    log_level=settings.log_level,
    log_file_enabled=settings.log_file_enabled,
    log_dir=settings.log_dir,
    log_max_bytes=settings.log_max_bytes,
    log_backup_count=settings.log_backup_count,
    log_json_enabled=settings.log_json_enabled,
)


# =====================================================
# 数据库初始化（同步 + 异步表创建 + 自动迁移缺失列）
# =====================================================
# 使用同步 metadata 先创建表（SQLite 不支持 DDL 并发）
Base.metadata.create_all(bind=engine)
logger.info("✓ 数据库表已初始化")

# 自动迁移：检查模型定义的列是否都存在于数据库表中，缺失则自动添加
# 解决 SQLite 的 create_all 只创建不存在的表、不添加新列的问题
def _auto_migrate_missing_columns():
    """
    自动检测并添加模型中定义但数据库表中缺失的列。
    仅支持 ALTER TABLE ADD COLUMN（新增列），不支持修改列类型或删除列。
    """
    from sqlalchemy import inspect as sa_inspect, text
    insp = sa_inspect(engine)
    for table_name, table_obj in Base.metadata.tables.items():
        if not insp.has_table(table_name):
            continue  # 新表已由 create_all 创建
        # 获取数据库中已有的列名
        db_columns = {col['name'] for col in insp.get_columns(table_name)}
        # 获取模型中定义的列名
        model_columns = {col.name for col in table_obj.columns}
        # 找出缺失的列
        missing = model_columns - db_columns
        for col_name in missing:
            col_obj = table_obj.columns[col_name]
            col_type = col_obj.type.compile(dialect=engine.dialect)
            default_val = ""
            if col_obj.default is not None:
                default_val = f" DEFAULT {col_obj.default.arg}"
            elif col_obj.server_default is not None:
                default_val = f" DEFAULT {col_obj.server_default.arg}"
            sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{default_val}"
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))  # SQLAlchemy 2.x 必须用 text() 包装字符串 SQL
                    conn.commit()
                logger.info("✓ 自动迁移: 已添加列 %s.%s", table_name, col_name)
            except Exception as e:
                logger.warning("⚠️ 自动迁移失败: %s.%s - %s", table_name, col_name, e)

_auto_migrate_missing_columns()


# =====================================================
# Lifespan 上下文管理器（替代 deprecated startup/shutdown）
# =====================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：
    - 启动：初始化异步资源（HTTP 连接池、后台任务轮询器）
    - 关闭：优雅释放所有异步资源
    """
    # ---------- 【启动阶段】----------
    if not settings.agnes_api_key or settings.agnes_api_key.startswith("sk-your"):
        logger.warning("⚠️ AGNES_API_KEY 未配置！请在前端配置页添加 Provider，或编辑 backend/.env 填入引导配置后重启服务。")
    else:
        logger.info("✓ Agnes AI API Key 引导配置已加载（将用于首次启动创建默认 Provider）")

    # 初始化 Provider 注册表（核心预处理层）
    # - 从数据库加载所有 Provider 配置
    # - 首次启动时用 settings 引导配置创建默认 Provider
    # - 为每个 Provider 创建独立的 AgnesAIClient 实例
    # - 用默认 Provider 配置全局 agnes_client 单例
    await provider_registry.initialize()
    logger.info("✓ Provider 注册表已初始化")

    # 初始化 httpx.AsyncClient（持久化连接池）
    # agnes_client 单例已由 provider_registry.configure() 配置好
    await agnes_client.start()
    logger.info("✓ HTTP 连接池已就绪")

    # 启动视频轮询器后台清理协程
    await poller_manager.start()
    logger.info("✓ 视频任务轮询器已就绪")

    # 启动图片任务器后台清理协程
    await image_poller_manager.start()
    logger.info("✓ 图片任务器已就绪")

    logger.info("🚀 Agnes AI Platform（全异步架构）后端服务已启动")

    yield  # 应用在此期间运行

    # ---------- 【关闭阶段】----------
    logger.info("👋 正在优雅关闭服务...")

    # 1. 取消所有视频轮询任务
    await poller_manager.shutdown()
    logger.info("✓ 视频轮询器已关闭")

    # 2. 取消所有图片生成任务
    await image_poller_manager.shutdown()
    logger.info("✓ 图片任务器已关闭")

    # 3. 关闭 Provider 注册表（释放所有 Provider 的 client 连接池）
    await provider_registry.shutdown()
    logger.info("✓ Provider 注册表已关闭")

    # 4. 关闭全局 agnes_client 单例的连接池
    await agnes_client.shutdown()
    logger.info("✓ HTTP 连接池已关闭")

    # 5. 关闭异步数据库引擎
    await async_engine.dispose()
    logger.info("✓ 数据库连接已释放")

    logger.info("👋 服务已完全关闭")


# =====================================================
# FastAPI 应用实例
# =====================================================
app = FastAPI(
    title="Agnes AI Platform",
    description="图片与视频生成平台 BFF 服务 — 全异步架构，图片/视频任务互不阻塞",
    version="2.0.0",
    lifespan=lifespan,
)

# ---------- CORS 中间件 ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request ID 中间件（必须在 CORS 之后注册）----------
# 为每个请求分配唯一 ID，注入日志上下文，实现请求链路追踪
app.add_middleware(RequestIdMiddleware)

# ---------- 全局异常处理 ----------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    捕获所有未处理异常，返回统一格式的 JSON 响应，避免将原始堆栈暴露给前端。
    """
    logger.error("未处理的异常: %s", str(exc), exc_info=True)

    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc)) if hasattr(exc, "detail") else "服务器内部错误，请稍后重试"

    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": detail},
    )


# ---------- 注册路由 ----------
app.include_router(config_route.router, prefix="/api", tags=["配置"])
app.include_router(providers_route.router, prefix="/api", tags=["Provider 与模型管理"])
app.include_router(images.router, prefix="/api", tags=["图片生成"])
app.include_router(videos.router, prefix="/api", tags=["视频生成"])
app.include_router(history_route.router, prefix="/api", tags=["生成历史"])
app.include_router(chat_route.router, prefix="/api", tags=["AI 聊天"])
app.include_router(logs_route.router, prefix="/api", tags=["日志查询"])
app.include_router(auth_route.router, prefix="/api", tags=["用户认证"])
app.include_router(admin_route.router, prefix="/api", tags=["管理员-积分规则"])
app.include_router(credits_route.router, prefix="/api", tags=["积分明细"])
app.include_router(proxy_route.router, prefix="/api", tags=["图片代理"])


# ---------- 健康检查 ----------
@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "ok", "service": "agnes-ai-platform"}


# ---------- 静态文件：用户上传的头像 ----------
# 通过 /uploads/avatars/<filename> 访问 backend/uploads/avatars/ 下的头像文件
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(os.path.join(UPLOADS_DIR, "avatars"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.get("/", summary="根路径 — 返回服务信息")
async def root():
    return {
        "name": "Agnes AI Platform BFF",
        "version": "2.0.0",
        "architecture": "async (FastAPI + httpx.AsyncClient + SQLAlchemy async)",
        "docs": "/docs",
        "health": "/health",
    }

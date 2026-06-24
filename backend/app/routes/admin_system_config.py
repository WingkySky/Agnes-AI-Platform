# =====================================================
# 系统配置管理路由（仅超级管理员）
#
# GET    /api/admin/system-config/smtp           获取 SMTP 配置
# PUT    /api/admin/system-config/smtp           更新 SMTP 配置
# POST   /api/admin/system-config/smtp/test      测试 SMTP 邮件发送
# =====================================================

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_async_db
from app.core.security import get_current_admin_user
from app.models.user import User
from app.services.system_config_service import get_smtp_config, update_smtp_config, SmtpConfig
from app.services.email_service import send_test_email

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/system-config", tags=["管理员-系统配置"])


# ---------- 请求模型 ----------

class SmtpConfigUpdate(BaseModel):
    """SMTP 配置更新请求"""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Agnes AI Platform"
    smtp_use_tls: bool = True


class SmtpTestRequest(BaseModel):
    """SMTP 测试请求"""
    test_email: str


# ---------- SMTP 配置 ----------

@router.get("/smtp", summary="[管理员] 获取 SMTP 配置")
async def get_smtp(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    """获取 SMTP 邮件服务器配置（密码字段返回空字符串，不回显）"""
    config = await get_smtp_config(db)
    return {
        "smtp_host": config.host,
        "smtp_port": config.port,
        "smtp_user": config.user,
        "smtp_password": "",  # 密码不回显
        "smtp_from_email": config.from_email,
        "smtp_from_name": config.from_name,
        "smtp_use_tls": config.use_tls,
        "is_enabled": config.is_enabled,
    }


@router.put("/smtp", summary="[管理员] 更新 SMTP 配置")
async def update_smtp(
    config_data: SmtpConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    """更新 SMTP 邮件服务器配置"""
    # 密码留空表示不修改：先读取当前配置，把密码带过去
    if not config_data.smtp_password:
        current_config = await get_smtp_config(db)
        password = current_config.password
    else:
        password = config_data.smtp_password

    await update_smtp_config(db, {
        "smtp_host": config_data.smtp_host,
        "smtp_port": config_data.smtp_port,
        "smtp_user": config_data.smtp_user,
        "smtp_password": password,
        "smtp_from_email": config_data.smtp_from_email,
        "smtp_from_name": config_data.smtp_from_name,
        "smtp_use_tls": config_data.smtp_use_tls,
    })

    logger.info("[系统配置] %s 更新了 SMTP 配置", admin.username)
    return {"message": "配置已保存"}


@router.post("/smtp/test", summary="[管理员] 测试 SMTP 邮件发送")
async def test_smtp(
    req: SmtpTestRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    """测试 SMTP 配置，发送一封测试邮件到指定邮箱"""
    config = await get_smtp_config(db)

    if not config.is_enabled:
        raise HTTPException(status_code=400, detail="SMTP 配置不完整，请先填写完整的服务器地址、账号、密码和发件人邮箱")

    success = await send_test_email(config, req.test_email)
    if not success:
        raise HTTPException(status_code=500, detail="测试邮件发送失败，请检查 SMTP 配置是否正确")

    logger.info("[系统配置] %s 测试 SMTP 邮件发送到 %s 成功", admin.username, req.test_email)
    return {"message": "测试邮件发送成功"}

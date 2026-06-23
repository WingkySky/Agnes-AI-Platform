# =====================================================
# 邮件发送服务
# - 通过 SMTP 发送邮件（验证码、通知等）
# - 使用 Python 内置 smtplib，异步封装
# =====================================================

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("agnes_platform")


def is_email_enabled() -> bool:
    """检查邮件服务是否已配置启用"""
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from_email)


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> bool:
    """
    异步发送邮件（实际通过线程池执行，避免阻塞事件循环）。

    参数：
    - to_email: 收件人邮箱
    - subject: 邮件主题
    - html_content: HTML 格式邮件正文
    - text_content: 纯文本格式邮件正文（可选，不提供则使用 html_content 的纯文本版本）

    返回：是否发送成功
    """
    if not is_email_enabled():
        logger.warning("[邮件] SMTP 未配置，跳过邮件发送 to=%s", to_email)
        return False

    import asyncio

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _send_email_sync,
            to_email,
            subject,
            html_content,
            text_content,
        )
        return result
    except Exception as e:
        logger.error("[邮件] 发送失败 to=%s error=%s", to_email, e)
        return False


def _send_email_sync(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> bool:
    """同步发送邮件（在线程池中执行）"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
        msg["To"] = to_email

        # 纯文本部分
        if text_content:
            part1 = MIMEText(text_content, "plain", "utf-8")
            msg.attach(part1)

        # HTML 部分
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part2)

        # 连接 SMTP 服务器
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)

        try:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
        finally:
            server.quit()

        logger.info("[邮件] 发送成功 to=%s subject=%s", to_email, subject)
        return True

    except Exception as e:
        logger.error("[邮件] 发送失败 to=%s error=%s", to_email, e)
        return False


# =====================================================
# 模板：重置密码验证码邮件
# =====================================================

def build_reset_password_email(code: str, expire_minutes: int = 10) -> tuple[str, str]:
    """
    构建重置密码验证码邮件的 HTML 和纯文本内容。

    返回：(html_content, text_content)
    """
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px 12px 0 0; text-align: center;">
            <h2 style="color: white; margin: 0; font-size: 24px;">Agnes AI Platform</h2>
            <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0;">重置密码验证码</p>
        </div>
        <div style="background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px; padding: 30px;">
            <p style="margin: 0 0 16px; color: #374151; font-size: 16px;">您好，</p>
            <p style="margin: 0 0 16px; color: #374151; font-size: 16px;">您正在请求重置 Agnes AI Platform 账号的密码。请使用以下验证码完成操作：</p>
            <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                <span style="font-size: 32px; font-weight: bold; color: #6366f1; letter-spacing: 8px;">{code}</span>
            </div>
            <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">
                验证码有效期：<strong style="color: #374151;">{expire_minutes} 分钟</strong>
            </p>
            <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">
                如非您本人操作，请忽略此邮件。
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
            <p style="margin: 0; color: #9ca3af; font-size: 12px; text-align: center;">
                此邮件由系统自动发送，请勿直接回复。
            </p>
        </div>
    </div>
    """

    text = f"""
Agnes AI Platform - 重置密码验证码

您好，

您正在请求重置 Agnes AI Platform 账号的密码。请使用以下验证码完成操作：

验证码：{code}

验证码有效期：{expire_minutes} 分钟

如非您本人操作，请忽略此邮件。

此邮件由系统自动发送，请勿直接回复。
    """.strip()

    return html, text

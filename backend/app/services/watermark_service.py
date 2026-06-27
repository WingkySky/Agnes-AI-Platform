# =====================================================
# 水印处理服务
# - 图片水印：使用 Pillow 在图片上叠加文字或图片水印
# - 视频水印：使用 ffmpeg drawtext/overlay 滤镜实时处理（apply_video_watermark）
# =====================================================

import asyncio
import hashlib
import logging
import os
import io
import tempfile
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.watermark import WatermarkConfig
from app.models.user import User

logger = logging.getLogger("agnes_platform")


# ---------- 获取/初始化水印配置 ----------
async def get_watermark_config(db: AsyncSession) -> WatermarkConfig:
    """获取全局水印配置，不存在则创建默认配置"""
    result = await db.execute(select(WatermarkConfig).filter(WatermarkConfig.id == 1))
    config = result.scalar_one_or_none()
    if not config:
        config = WatermarkConfig(id=1)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


# ---------- 判断是否需要加水印 ----------
def should_apply_watermark(config: WatermarkConfig, user: Optional[User]) -> bool:
    """
    判断某用户的生成结果是否需要加水印"""
    if not config:
        return False
    # 全局强制：所有用户都加
    if config.force_all:
        return True
    # 用户级开关
    if user and user.watermark_enabled:
        return True
    return False


# ---------- 给图片加文字水印 ----------
def apply_image_watermark(
    image_bytes: bytes,
    config: WatermarkConfig,
    output_path: Optional[str] = None,
) -> bytes:
    """
    给图片加文字水印，返回加水印后的图片字节。
    
    参数：
    - image_bytes: 原始图片字节数据
    - config: 水印配置
    - output_path: 可选，保存到文件路径
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("[水印] Pillow 未安装，跳过图片水印")
        return image_bytes

    try:
        # 打开图片
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size

        # 创建透明图层用于绘制水印
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        opacity = max(0, min(100, int(config.opacity or 50)))
        alpha = int(255 * opacity / 100)

        wm_type = str(getattr(config, 'type', 'text') or 'text').lower()
        if wm_type == "image" and getattr(config, 'image_url', None):
            # 图片水印
            from urllib.parse import urlparse
            logo = None
            try:
                image_url = str(config.image_url or "")
                parsed = urlparse(image_url)
                # 如果是本地路径（/uploads/...）直接读本地文件
                local_path = parsed.path
                if local_path and os.path.exists(local_path):
                    logo = Image.open(local_path).convert("RGBA")
                else:
                    # 远程 URL 的水印图片暂不支持（避免网络请求）
                    logger.warning("[水印] 水印图片路径不存在或为远程URL: %s", image_url)
            except Exception as e:
                logger.warning("[水印] 加载水印图片失败: %s", e)
                logo = None
            
            if logo is not None:
                try:
                    # 按宽度等比缩放
                    wm_width = int(getattr(config, 'image_width', 120) or 120)
                    if wm_width <= 0:
                        wm_width = 120
                    ratio = wm_width / max(1, logo.width)
                    new_height = int(logo.height * ratio)
                    if new_height <= 0:
                        new_height = 1
                    logo = logo.resize((wm_width, new_height), Image.LANCZOS)
                    
                    # 计算位置
                    margin = int(getattr(config, 'margin', 20) or 20)
                    pos = _calc_position(config.position, width, height, wm_width, new_height, margin)
                    
                    # 调整透明度
                    if logo.mode != "RGBA":
                        logo = logo.convert("RGBA")
                    # 创建新的alpha通道，设置统一透明度
                    r, g, b, a = logo.split()
                    a = a.point(lambda i: int(i * alpha / 255))
                    logo = Image.merge("RGBA", (r, g, b, a))
                    
                    overlay.paste(logo, pos, logo)
                except Exception as e:
                    logger.warning("[水印] 图片水印绘制失败: %s", e)
        else:
            # 文字水印
            font_size = int(getattr(config, 'font_size', 24) or 24)
            if font_size <= 0:
                font_size = 24
            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except Exception:
                try:
                    # macOS 系统字体兜底
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                except Exception:
                    font = ImageFont.load_default()
            
            text = str(getattr(config, 'text', None) or "Agnes AI")
            
            # 计算文字尺寸
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except Exception:
                text_width = len(text) * font_size
                text_height = font_size
            
            # 颜色
            color_hex = str(getattr(config, 'color', None) or "#FFFFFF")
            color_rgb = _hex_to_rgb(color_hex)
            fill_color = (color_rgb[0], color_rgb[1], color_rgb[2], alpha)
            
            # 计算位置
            margin = int(getattr(config, 'margin', 20) or 20)
            pos = _calc_position(config.position, width, height, text_width, text_height, margin)
            
            # 先画文字阴影（增强可读性）
            shadow_offset = max(1, font_size // 24)
            shadow_alpha = min(alpha // 2, 128)
            draw.text(
                (pos[0] + shadow_offset, pos[1] + shadow_offset),
                text,
                font=font,
                fill=(0, 0, 0, shadow_alpha)
            )
            draw.text(pos, text, font=font, fill=fill_color)

        # 合并图层
        watermarked = Image.alpha_composite(img, overlay)
        watermarked = watermarked.convert("RGB")
        
        # 保存到字节
        output = io.BytesIO()
        watermarked.save(output, format="PNG")
        result_bytes = output.getvalue()
        
        # 如果指定了输出路径
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(result_bytes)
        
        return result_bytes
        
    except Exception as e:
        logger.error("[水印] 图片水印处理失败: %s", e)
        return image_bytes


# ---------- 辅助函数 ----------
def _calc_position(position, img_width: int, img_height: int,
                  wm_width: int, wm_height: int, margin: int) -> tuple:
    """根据位置字符串计算水印坐标（左上角 x, y）"""
    # 安全转换，防止非数值类型
    try:
        margin = int(margin or 20)
        img_width = int(img_width or 0)
        img_height = int(img_height or 0)
        wm_width = int(wm_width or 0)
        wm_height = int(wm_height or 0)
    except (ValueError, TypeError):
        margin = 20
        img_width = int(img_width or 0)
        img_height = int(img_height or 0)
        wm_width = int(wm_width or 0)
        wm_height = int(wm_height or 0)

    position_str = str(position or "bottom-right").lower()
    if position_str == "top-left":
        return (margin, margin)
    elif position_str == "top-right":
        return (max(0, img_width - wm_width - margin), margin)
    elif position_str == "bottom-left":
        return (margin, max(0, img_height - wm_height - margin))
    elif position_str == "center":
        return (max(0, (img_width - wm_width) // 2), max(0, (img_height - wm_height) // 2))
    else:  # bottom-right (default)
        return (max(0, img_width - wm_width - margin), max(0, img_height - wm_height - margin))


def _hex_to_rgb(hex_color) -> tuple:
    """十六进制颜色转 RGB，失败时返回白色 (255,255,255)"""
    # 确保输入是字符串
    if not hex_color:
        return (255, 255, 255)
    try:
        hex_str = str(hex_color).lstrip("#")
        if len(hex_str) == 3:
            hex_str = "".join(c * 2 for c in hex_str)
        if len(hex_str) != 6:
            return (255, 255, 255)
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b)
    except Exception:
        return (255, 255, 255)


# =====================================================
# 视频水印（ffmpeg drawtext / overlay）
# =====================================================

def _calc_ffmpeg_position(
    position: str,
    video_width: int,
    video_height: int,
    wm_width: int,
    wm_height: int,
    margin: int,
) -> str:
    """
    根据位置字符串计算 ffmpeg overlay 滤镜的坐标表达式

    ffmpeg overlay 坐标系：左上角为原点，支持表达式（W/H 为主视频宽高，w/h 为水印宽高）

    Returns:
        ffmpeg 坐标表达式字符串，如 "x=W-w-20:y=H-h-20"
    """
    position_str = str(position or "bottom-right").lower()
    # 安全转换
    try:
        margin = max(0, int(margin or 20))
    except (ValueError, TypeError):
        margin = 20

    if position_str == "top-left":
        return f"x={margin}:y={margin}"
    elif position_str == "top-right":
        return f"x=W-w-{margin}:y={margin}"
    elif position_str == "bottom-left":
        return f"x={margin}:y=H-h-{margin}"
    elif position_str == "center":
        return f"x=(W-w)/2:y=(H-h)/2"
    else:  # bottom-right（默认）
        return f"x=W-w-{margin}:y=H-h-{margin}"


def _find_video_font() -> str:
    """查找系统中可用的中文字体文件（与 ffmpeg_composite._find_font 逻辑一致）"""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


def _escape_drawtext_text(text: str) -> str:
    """转义 drawtext 文本中的特殊字符（与 ffmpeg_composite 一致）"""
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    text = text.replace("\n", " ").replace("\r", " ")
    return text


_video_watermark_logger = logging.getLogger("agnes_platform.watermark")


async def apply_video_watermark(
    video_path: str,
    config: "WatermarkConfig",
    output_path: str,
) -> str:
    """
    给视频加水印（文字或图片），返回输出文件路径

    实现策略：
    - 文字水印：ffmpeg drawtext 滤镜
    - 图片水印：ffmpeg overlay 滤镜
    - 必须重编码视频流（drawtext/overlay 需要 -filter_complex，不能用 -c:v copy）
    - 用 libx264 -preset fast 平衡速度与质量

    Args:
        video_path: 输入视频文件路径
        config: 水印配置（WatermarkConfig ORM 对象）
        output_path: 输出文件路径

    Returns:
        输出文件路径（处理失败时返回原 video_path，不阻断下载）
    """
    if not os.path.exists(video_path):
        _video_watermark_logger.warning(f"[视频水印] 输入视频不存在: {video_path}")
        return video_path

    opacity = max(0, min(100, int(config.opacity or 50)))
    alpha = opacity / 100.0  # 0.0~1.0
    margin = int(getattr(config, "margin", 20) or 20)
    position = str(getattr(config, "position", "bottom-right") or "bottom-right")

    wm_type = str(getattr(config, "type", "text") or "text").lower()
    fontfile = _find_video_font()
    font_opt = f":fontfile='{fontfile}'" if fontfile else ""

    # 构建 filter_complex
    if wm_type == "image" and getattr(config, "image_url", None):
        # 图片水印：用 overlay 滤镜
        from urllib.parse import urlparse
        image_url = str(config.image_url or "")
        parsed = urlparse(image_url)
        local_path = parsed.path
        if not local_path or not os.path.exists(local_path):
            _video_watermark_logger.warning(
                f"[视频水印] 水印图片不存在或为远程URL: {image_url}，跳过"
            )
            return video_path

        # 计算水印图片缩放后的尺寸（用于位置计算）
        wm_width = int(getattr(config, "image_width", 120) or 120)
        if wm_width <= 0:
            wm_width = 120
        # overlay 表达式不直接知道缩放后的高，用 -filter_complex 链
        pos_expr = _calc_ffmpeg_position(
            position, 0, 0, 0, 0, margin  # video_width/height 用 W/H 表达式
        )
        # 注意：图片水印的高需要从输入读取，这里用 w/h 表达式
        # 替换占位为 ffmpeg 表达式
        if "W-w-" in pos_expr:
            pos_expr = pos_expr.replace("W-w-", "W-w-")
        elif "W-w" in pos_expr:
            pass  # 已是表达式
        # 简化：overlay 直接用 W/H/w/h 表达式
        if position == "top-left":
            overlay_pos = f"x={margin}:y={margin}"
        elif position == "top-right":
            overlay_pos = f"x=W-w-{margin}:y={margin}"
        elif position == "bottom-left":
            overlay_pos = f"x={margin}:y=H-h-{margin}"
        elif position == "center":
            overlay_pos = f"x=(W-w)/2:y=(H-h)/2"
        else:  # bottom-right
            overlay_pos = f"x=W-w-{margin}:y=H-h-{margin}"

        filter_complex = (
            f"[1:v]scale={wm_width}:-1[wm];"
            f"[0:v][wm]overlay={overlay_pos}:format=auto[outv]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", local_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a?",  # 保留原音轨（如有）
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        # 文字水印：用 drawtext 滤镜
        text = str(getattr(config, "text", None) or "Agnes AI")
        escaped = _escape_drawtext_text(text)
        font_size = int(getattr(config, "font_size", 24) or 24)
        if font_size <= 0:
            font_size = 24
        color_hex = str(getattr(config, "color", None) or "#FFFFFF").lstrip("#")
        color_rgb = _hex_to_rgb(color_hex)
        # drawtext fontcolor 用 0xRRGGBB@alpha 格式
        fontcolor = f"0x{color_rgb[0]:02X}{color_rgb[1]:02X}{color_rgb[2]:02X}@{alpha:.2f}"

        # 位置表达式
        if position == "top-left":
            pos = f"x={margin}:y={margin}"
        elif position == "top-right":
            pos = f"x=w-text_w-{margin}:y={margin}"
        elif position == "bottom-left":
            pos = f"x={margin}:y=h-text_h-{margin}"
        elif position == "center":
            pos = f"x=(w-text_w)/2:y=(h-text_h)/2"
        else:  # bottom-right
            pos = f"x=w-text_w-{margin}:y=h-text_h-{margin}"

        drawtext = (
            f"drawtext=text='{escaped}'{font_opt}"
            f":fontcolor={fontcolor}:fontsize={font_size}"
            f":{pos}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", drawtext,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[-300:]
            _video_watermark_logger.warning(f"[视频水印] ffmpeg 失败: {err_text}")
            return video_path
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        _video_watermark_logger.warning("[视频水印] 输出文件为空")
        return video_path
    except asyncio.TimeoutError:
        _video_watermark_logger.warning("[视频水印] ffmpeg 超时（5min）")
        return video_path
    except Exception as e:
        _video_watermark_logger.warning(f"[视频水印] 异常: {e}")
        return video_path

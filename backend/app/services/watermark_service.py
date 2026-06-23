# =====================================================
# 水印处理服务
# - 图片水印：使用 Pillow 在图片上叠加文字或图片水印
# - 视频水印：暂不处理（视频水印复杂度高，先做图片）
# =====================================================

import logging
import os
import io
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
        logger.warning("[水印] Pillow 未安装，跳过敏词检测")
        return image_bytes

    try:
        # 打开图片
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size

        # 创建透明图层用于绘制水印
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        opacity = max(0, min(100, config.opacity or 50))
        alpha = int(255 * opacity / 100)

        if config.type == "image" and config.image_url:
            # 图片水印
            from urllib.parse import urlparse
            parsed = urlparse(config.image_url)
            # 如果是本地路径（/uploads/...）直接读本地文件
            local_path = parsed.path
            if os.path.exists(local_path):
                try:
                    logo = Image.open(local_path).convert("RGBA")
                except Exception:
                    logo = None
            else:
                # 远程 URL 的水印图片暂不支持（避免网络请求）
                logo = None
            
            if logo:
                # 按宽度等比缩放
                ratio = config.image_width / logo.width
                new_height = int(logo.height * ratio)
                logo = logo.resize((config.image_width, new_height), Image.LANCZOS)
                
                # 计算位置
                pos = _calc_position(config.position, width, height, config.image_width, new_height, config.margin)
                
                # 调整透明度
                if logo.mode != "RGBA":
                    logo = logo.convert("RGBA")
                alpha_layer = logo.split()[3]
                alpha_layer = Image.new("L", logo.size, int(alpha * 255 / 255))
                logo.putalpha(alpha_layer)
                
                overlay.paste(logo, pos, logo)
        else:
            # 文字水印
            try:
                font = ImageFont.truetype("Arial.ttf", config.font_size or 24)
            except Exception:
                font = ImageFont.load_default()
            
            text = config.text or "Agnes AI"
            
            # 计算文字尺寸
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except Exception:
                text_width = len(text) * (config.font_size or 24)
                text_height = config.font_size or 24
            
            # 颜色
            color_hex = config.color or "#FFFFFF"
            color_rgb = _hex_to_rgb(color_hex)
            fill_color = (*color_rgb, alpha)
            
            # 计算位置
            pos = _calc_position(config.position, width, height, text_width, text_height, config.margin)
            
            # 先画文字阴影（增强可读性）
            shadow_offset = max(1, config.font_size // 24)
            draw.text((pos[0] + shadow_offset, pos[1] + shadow_offset), text, font=font, fill=(0, 0, 0, min(alpha // 2)))
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
def _calc_position(position: str, img_width: int, img_height: int,
                  wm_width: int, wm_height: int, margin: int) -> tuple:
    """根据位置字符串计算水印坐标（左上角 x, y）"""
    margin = margin or 20
    if position == "top-left":
        return (margin, margin)
    elif position == "top-right":
        return (img_width - wm_width - margin, margin)
    elif position == "bottom-left":
        return (margin, img_height - wm_height - margin)
    elif position == "center":
        return ((img_width - wm_width) // 2, (img_height - wm_height) // 2)
    else:  # bottom-right (default)
        return (img_width - wm_width - margin, img_height - wm_height - margin)


def _hex_to_rgb(hex_color: str) -> tuple:
    """十六进制颜色转 RGB"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (255, 255, 255)

# =====================================================
# 文件上传服务 — 通用文件保存到本地 uploads 目录
#
# 复用项目现有的 /uploads 静态目录挂载（见 main.py）
# 所有上传文件统一保存到 uploads/<folder>/<filename>，
# 返回 /uploads/<folder>/<filename> 形式的 URL 供前端访问。
# =====================================================

import logging
import os
import time
from typing import Optional

from fastapi import UploadFile, HTTPException

logger = logging.getLogger("agnes_platform.upload")

# uploads 根目录（与 main.py 的 UPLOADS_DIR 一致）
UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "uploads",
)
UPLOADS_DIR = os.path.abspath(UPLOADS_DIR)

# 允许的文件类型
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/quicktime", "video/webm",
}
ALLOWED_ALL = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES

# 单文件最大 100MB
MAX_FILE_BYTES = 100 * 1024 * 1024


# =====================================================
# 核心函数
# =====================================================

async def save_upload_file(
    file: UploadFile,
    folder: str = "projects",
    *,
    allowed_types: Optional[set] = None,
    max_size: int = MAX_FILE_BYTES,
) -> str:
    """
    保存上传文件到本地 uploads 目录

    Args:
        file: FastAPI UploadFile
        folder: 子目录（如 projects/123/characters）
        allowed_types: 允许的 MIME 类型集合，None 则用 ALLOWED_ALL
        max_size: 最大字节数
    Returns:
        可访问的 URL（如 /uploads/projects/123/...）
    """
    allowed = allowed_types or ALLOWED_ALL
    if file.content_type and file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：{file.content_type}",
        )

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大 {max_size // 1024 // 1024}MB",
        )

    # 确保目录存在
    target_dir = os.path.join(UPLOADS_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)

    # 扩展名
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
    }
    ext = ext_map.get(file.content_type, "")
    if not ext and file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()

    # 文件名：时间戳 + 随机数避免冲突
    import secrets
    filename = f"{int(time.time())}_{secrets.token_hex(4)}{ext}"
    filepath = os.path.join(target_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    url = f"/uploads/{folder}/{filename}"
    logger.info(f"[文件上传] 保存到 {filepath}, url={url}")
    return url


async def save_audio_bytes(
    content: bytes,
    folder: str = "projects",
    ext: str = ".mp3",
) -> str:
    """
    保存服务端生成的音频字节（如 TTS 产物）到 uploads 目录

    Returns:
        可访问的 URL（/uploads/<folder>/<filename>）
    """
    if not content:
        raise HTTPException(status_code=400, detail="音频内容为空")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f"音频文件过大，最大 {MAX_FILE_BYTES // 1024 // 1024}MB")

    target_dir = os.path.join(UPLOADS_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)

    import secrets
    filename = f"{int(time.time())}_{secrets.token_hex(4)}{ext}"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    url = f"/uploads/{folder}/{filename}"
    logger.info(f"[音频落盘] 保存到 {filepath}, url={url}")
    return url


async def save_image_upload(file: UploadFile, folder: str = "projects") -> str:
    """仅允许图片的上传快捷函数"""
    return await save_upload_file(
        file, folder, allowed_types=ALLOWED_IMAGE_TYPES, max_size=20 * 1024 * 1024
    )


async def save_video_upload(file: UploadFile, folder: str = "projects") -> str:
    """仅允许视频的上传快捷函数"""
    return await save_upload_file(
        file, folder, allowed_types=ALLOWED_VIDEO_TYPES, max_size=MAX_FILE_BYTES
    )

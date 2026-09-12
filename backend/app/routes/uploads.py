# =====================================================
# 通用图片上传路由
# 预设封面等场景的小体积图片上传，存 uploads/preset-covers/
# =====================================================

import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from app.core.response import ok

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/uploads", tags=["上传"])

# 保存目录（相对于后端工作目录）
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "preset-covers")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/image", summary="上传图片（预设封面等）")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    上传图片，返回可直接访问的 URL（/uploads/preset-covers/<filename>）。

    - 支持 jpeg/png/webp，最大 5MB
    - 文件名带用户 ID + 时间戳防冲突
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式：{file.content_type}，仅支持 jpeg/png/webp")

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="图片文件过大，最大 5MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    filename = f"{current_user.id}_{int(time.time())}{ext_map.get(file.content_type, '.jpg')}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    return ok(data={"url": f"/uploads/preset-covers/{filename}"})

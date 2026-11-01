# =====================================================
# 剪辑成片导出（成片后处理：GIF / 仅音频；剪映草稿另见 jianying_export）
#
# 同步端点：GIF 有时长守门（超上限 400 拒绝，防长阻塞），产物落 uploads/editor/
# + 存储配额记账（best-effort），返回 /uploads/ 下载 URL（不入资产库）。
# =====================================================

import os
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.editing_project import RENDER_SUCCEEDED, EditingProject
from app.services.media_compose import probe_durations, run_ffmpeg
from app.services.upload_service import UPLOADS_DIR

GIF_MAX_SECONDS = 120
GIF_DEFAULT_WIDTH = 480
GIF_DEFAULT_FPS = 12


def build_gif_cmds(src: str, out: str, width: int, fps: int) -> list[list[str]]:
    """GIF 调色板两遍命令（纯函数，黄金测试直测）"""
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    palette = out + ".palette.png"
    return [
        ["ffmpeg", "-y", "-i", src, "-vf", f"{vf},palettegen", palette],
        ["ffmpeg", "-y", "-i", src, "-i", palette, "-lavfi", f"[0:v]{vf}[x];[x][1:v]paletteuse", "-loop", "0", out],
    ]


def build_audio_cmd(src: str, out: str) -> list[str]:
    """成片提取混音（纯函数）"""
    return ["ffmpeg", "-y", "-i", src, "-vn", "-c:a", "aac", "-b:a", "192k", out]


async def export_final(project: EditingProject, fmt: str, width: int | None = None, fps: int | None = None,
                       db: AsyncSession | None = None) -> dict:
    """成片后处理导出：校验 → ffmpeg → uploads 落盘 + 记账 → 下载 URL。"""
    if project.render_status != RENDER_SUCCEEDED or not project.final_url:
        raise HTTPException(status_code=400, detail="还没有渲染成功的成片，请先渲染")
    src = os.path.join(UPLOADS_DIR, project.final_url.removeprefix("/uploads/"))
    if not os.path.exists(src):
        raise HTTPException(status_code=400, detail="成片文件缺失，请重新渲染")

    if fmt == "gif":
        (duration,) = await probe_durations([src])
        if duration > GIF_MAX_SECONDS:
            raise HTTPException(status_code=400, detail=f"成片时长 {duration:.0f}s 超过 GIF 导出上限 {GIF_MAX_SECONDS}s，可下载成片后自行转换")
        w = min(max(int(width or GIF_DEFAULT_WIDTH), 64), 1920)
        f = min(max(int(fps or GIF_DEFAULT_FPS), 5), 30)
        ext, kind = "gif", "image"
    elif fmt == "audio":
        ext, kind = "m4a", "audio"
    else:
        raise HTTPException(status_code=400, detail="format 仅支持 gif / audio")

    out_dir = os.path.join(UPLOADS_DIR, "editor")
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, f".export_{uuid.uuid4().hex[:12]}.{ext}")
    if fmt == "gif":
        cmds = build_gif_cmds(src, tmp, w, f)
        palette = cmds[0][-1]
        try:
            for c in cmds:
                await run_ffmpeg(c, timeout=600, error_label="GIF 导出")
        finally:
            if os.path.exists(palette):
                os.remove(palette)
    else:
        await run_ffmpeg(build_audio_cmd(src, tmp), timeout=600, error_label="音频导出")

    storage_key = f"editor/{uuid.uuid4().hex}.{ext}"
    final_path = os.path.join(UPLOADS_DIR, storage_key)
    os.replace(tmp, final_path)
    size = os.path.getsize(final_path)

    from app.services.storage_quota import SOURCE_RENDER, record_file
    await record_file(user_id=project.user_id, storage_key=storage_key, source=SOURCE_RENDER, kind=kind)
    if db is not None:
        await db.commit()

    return {"format": fmt, "url": f"/uploads/{storage_key}", "size": size}

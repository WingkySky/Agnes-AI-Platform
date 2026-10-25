# =====================================================
# 诊断包路由（可靠性三件套 ③）
# GET /api/admin/diagnostics/export - 导出脱敏诊断 ZIP（管理员级，显式挂鉴权）
# =====================================================

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.database import get_async_db
from app.core.security import get_current_admin_user
from app.models.user import User
from app.services.diagnostics_service import build_diagnostics_zip, diagnostics_filename

router = APIRouter(tags=["诊断"])


@router.get("/admin/diagnostics/export", summary="导出脱敏诊断包（ZIP）")
async def export_diagnostics(
    db=Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    """管理员一键导出：meta/脱敏配置/日志尾部/最近生成与上游调用/存储摘要/表统计"""
    data = await build_diagnostics_zip(db)
    filename = diagnostics_filename()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

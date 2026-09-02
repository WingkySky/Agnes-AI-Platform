# =====================================================
# 统一响应结构（AGENTS.md：status/message/data 或 HTTPException）
# 成功：{"status": "success", "message": "", "data": ...}
# 失败：一律 raise HTTPException（FastAPI 标准 {"detail": ...}）
# 前端 client.ts 拦截器对 envelope 透明解包，组件直接拿 data。
# 注意：StreamingResponse / FileResponse / SSE 等非 JSON 响应不包 envelope。
# =====================================================

from typing import Any


def ok(data: Any = None, message: str = "") -> dict:
    """业务成功响应的统一包装。"""
    return {"status": "success", "message": message, "data": data}

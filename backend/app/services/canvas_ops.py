# =====================================================
# 画布远程操作领域服务（外部宿主增量写入：对话 Agent / Phase B MCP / CLI 共用）
#
# - 纯函数操作工作区 data（panels/connections），不触 DB：路由层取行 → apply → 写回
# - 语义对齐前端 stores/canvas.ts 的 addPanel/addConnection/validateConnectionTypes
#   与 lib/agent/tools.ts 的 applyOps（TS/Python 各一份，pytest 锁死一致）
# - v1 仅只读 + 增量：add_panel / add_connection，不做 update/delete
# =====================================================

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 节点缺省尺寸（对齐 lib/agent/tools.ts applyOps）
PANEL_DEFAULT_WIDTH = 240
PANEL_DEFAULT_HEIGHT = 180

# 连线校验的目标类型白名单（对齐前端 validateConnectionTypes 的 ALLOWED_INPUTS）
_ALLOWED_INPUTS: Dict[str, List[str]] = {
    "tts": ["text"],
    "subtitle": ["text"],
    "compose": ["video", "tts", "subtitle"],
}
_TARGET_LABELS = {"tts": "配音", "subtitle": "字幕", "compose": "成片合成"}
_SOURCE_LABELS = {
    "text": "文本", "image": "图片", "video": "视频", "audio": "音频", "config": "配置",
    "tts": "配音", "subtitle": "字幕", "compose": "合成", "script": "脚本",
}


def _uid() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _as_number(v: Any, fallback: float) -> float:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else fallback


def panel_type(panel: Dict[str, Any]) -> str:
    return panel.get("type") or "text"


def validate_connection_types(source_type: str, target_type: str) -> Optional[str]:
    """连线类型级校验（复刻前端 validateConnectionTypes；返回 None 表示通过）"""
    if source_type == "script" and target_type != "config":
        return "脚本节点只能连接到生成配置节点"
    allowed = _ALLOWED_INPUTS.get(target_type)
    if not allowed:
        return None
    if source_type not in allowed:
        target_label = _TARGET_LABELS.get(target_type, target_type)
        source_label = _SOURCE_LABELS.get(source_type, source_type)
        return f"{target_label}节点不接受 {source_label} 类型输入"
    return None


def apply_canvas_ops(
    data: Dict[str, Any], ops: List[Dict[str, Any]], workspace_id: Optional[str] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """对工作区 data 应用批量增量操作，返回 (new_data, outcome)。

    - new_data 为深拷贝后的新对象（调用方整体赋值回 ORM JSON 列，保证变更被跟踪）
    - outcome = { results, new_panel_ids, failed }；单条失败不拖垮整批，
      全部失败时调用方不写回（路由层返回 400）
    """
    new_data = json.loads(json.dumps(data or {}))
    panels: List[Dict[str, Any]] = new_data.setdefault("panels", [])
    connections: List[Dict[str, Any]] = new_data.setdefault("connections", [])

    results: List[Dict[str, Any]] = []
    new_panel_ids: List[str] = []
    # 批内新建 name → id：后续 op 可按名引用本批新建节点（一拍完成建点 + 连线）
    batch_by_name: Dict[str, str] = {}

    def resolve_ref(ref: Any) -> Optional[str]:
        if not isinstance(ref, str) or not ref:
            return None
        batch_id = batch_by_name.get(ref)
        if batch_id:
            return batch_id
        for p in panels:
            if p.get("id") == ref:
                return ref
        for p in panels:
            if (p.get("name") or "") == ref and p.get("id"):
                return p["id"]
        return None

    for i, raw in enumerate(ops):
        op = raw if isinstance(raw, dict) else {}
        kind = str(op.get("op") or "")
        try:
            if kind == "add_panel":
                n = len(panels)
                name = str(op.get("name") or "").strip()
                panel: Dict[str, Any] = {
                    "id": _uid(),
                    "type": str(op.get("type") or "text"),
                    "x": _as_number(op.get("x"), 120 + (n % 8) * 40),
                    "y": _as_number(op.get("y"), 120 + (n % 8) * 40),
                    "width": _as_number(op.get("width"), PANEL_DEFAULT_WIDTH),
                    "height": _as_number(op.get("height"), PANEL_DEFAULT_HEIGHT),
                    "zIndex": n + 1,
                    "content": op.get("content") if isinstance(op.get("content"), dict) else {},
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
                if workspace_id:
                    panel["workspace_id"] = workspace_id
                if name:
                    panel["name"] = name
                    batch_by_name[name] = panel["id"]
                panels.append(panel)
                new_panel_ids.append(panel["id"])
                results.append({"index": i, "op": kind, "ok": True, "panel_id": panel["id"]})
            elif kind == "add_connection":
                source_id = resolve_ref(op.get("source_panel_id"))
                target_id = resolve_ref(op.get("target_panel_id"))
                if not source_id or not target_id:
                    missing = "、".join(
                        str(op.get(k))
                        for k in ("source_panel_id", "target_panel_id")
                        if not resolve_ref(op.get(k))
                    )
                    results.append({
                        "index": i, "op": kind, "ok": False,
                        "error": f"节点不存在: {missing}（可用节点名称或 canvas_get_overview 返回的 id）",
                    })
                    continue
                source = next(p for p in panels if p.get("id") == source_id)
                target = next(p for p in panels if p.get("id") == target_id)
                err = validate_connection_types(panel_type(source), panel_type(target))
                if err:
                    results.append({"index": i, "op": kind, "ok": False, "error": err})
                    continue
                conn: Dict[str, Any] = {
                    "id": _uid(),
                    "source_panel_id": source_id,
                    "target_panel_id": target_id,
                    "type": "manual",
                    "created_at": _now_iso(),
                }
                if workspace_id:
                    conn["workspace_id"] = workspace_id
                connections.append(conn)
                results.append({"index": i, "op": kind, "ok": True, "connection_id": conn["id"]})
            else:
                results.append({"index": i, "op": kind or "(空)", "ok": False, "error": f"未知操作类型: {kind}"})
        except Exception as e:  # 单条异常不拖垮整批
            results.append({"index": i, "op": kind, "ok": False, "error": str(e)})

    failed = sum(1 for r in results if not r.get("ok"))
    return new_data, {"results": results, "new_panel_ids": new_panel_ids, "failed": failed}

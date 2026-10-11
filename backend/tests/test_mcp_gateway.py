# =====================================================
# MCP 网关单测 —— overview 分页纯函数（TS 对齐）/ 内容摘要 / 工具 impl（db+user_id 直测）
# =====================================================

import pytest
from fastapi import HTTPException

from app.models.canvas_workspace import CanvasWorkspace
from app.services.mcp_gateway import (
    canvas_apply_ops_impl,
    canvas_create_impl,
    canvas_list_impl,
    canvas_overview_impl,
    overview_page,
    panel_content_summary,
    parse_overview_cursor,
)


# ---------- 游标解析 ----------
def test_parse_overview_cursor():
    assert parse_overview_cursor(None) == 0
    assert parse_overview_cursor("") == 0
    assert parse_overview_cursor("abc") == 0
    assert parse_overview_cursor("-3") == 0
    assert parse_overview_cursor("0") == 0
    assert parse_overview_cursor("12") == 12


# ---------- 分页：钳位 / next_cursor / 游标越界回第一页 ----------
def test_overview_page_clamp_and_cursor():
    panels = [{"id": i} for i in range(25)]
    page = overview_page(panels, None, 10)
    assert len(page["items"]) == 10 and page["next_cursor"] == "10" and page["total"] == 25

    page = overview_page(panels, "20", 10)
    assert len(page["items"]) == 5 and "next_cursor" not in page  # 末页

    # size 钳 10~100，非法回退 60
    assert overview_page(panels, None, 1)["items"].__len__() == 10
    assert overview_page(panels, None, 999)["items"].__len__() == 25
    assert overview_page(panels, None, None)["items"].__len__() == 25

    # 游标越过末尾 = 画布收缩 → 回第一页重读
    page = overview_page(panels, "999", 10)
    assert page["page_range"] == [0, 10]


# ---------- 内容摘要：文本/媒体两分支（与前端 panelContentSummary 对齐） ----------
def test_panel_content_summary():
    assert panel_content_summary({"type": "text", "content": {"content": "一段剧情文字"}}) == "一段剧情文字"
    assert panel_content_summary({"type": "text", "content": {}}) == ""
    long = "x" * 150
    assert panel_content_summary({"type": "text", "content": {"content": long}}).endswith("…")
    media = panel_content_summary({"type": "image", "content": {"status": "done", "prompt": "p" * 80, "content": "url"}})
    assert media == f"status=done prompt={'p' * 60}… 有媒体内容"
    assert panel_content_summary({"type": "image", "content": {}}) == ""


# ---------- 工具 impl：list / create（默认名）/ overview（连线过滤）/ apply_ops ----------
@pytest.mark.asyncio
async def test_canvas_impl_flow(memory_db, seed_user):
    created = await canvas_create_impl(memory_db, seed_user.id, None)
    assert created["ok"] is True
    assert created["workspace"]["name"].startswith("外部画布")  # 默认命名
    ws_id = created["workspace"]["id"]

    listing = await canvas_list_impl(memory_db, seed_user.id)
    assert [w["id"] for w in listing["items"]] == [ws_id]

    ops = [
        {"op": "add_panel", "type": "text", "name": "开场", "content": {"content": "第一幕"}},
        {"op": "add_panel", "type": "image", "name": "海报"},
        {"op": "add_connection", "source_panel_id": "开场", "target_panel_id": "海报"},  # 按名引用
    ]
    outcome = await canvas_apply_ops_impl(memory_db, seed_user.id, ws_id, ops)
    assert outcome["ok"] is True and outcome["failed"] == 0
    assert len(outcome["new_panel_ids"]) == 2 and outcome["revision"] == 2

    overview = await canvas_overview_impl(memory_db, seed_user.id, ws_id, None, 1)  # size 钳 10
    assert overview["panel_count"] == 2
    assert overview["panels"][0]["summary"] == "第一幕"
    assert overview["connections"] == [{"id": overview["connections"][0]["id"], "source": "开场", "target": "海报"}]


# ---------- 归属：他人画布 403 / 不存在 404；全部失败 400 ----------
@pytest.mark.asyncio
async def test_canvas_impl_ownership_and_all_failed(memory_db, seed_user):
    other_ws = CanvasWorkspace(id="ws_other", user_id=seed_user.id + 1, name="别人的")
    memory_db.add(other_ws)
    memory_db.add(CanvasWorkspace(id="ws_mine", user_id=seed_user.id, name="我的"))
    await memory_db.commit()

    with pytest.raises(HTTPException) as e:
        await canvas_overview_impl(memory_db, seed_user.id, "ws_other", None, None)
    assert e.value.status_code == 403

    with pytest.raises(HTTPException) as e:
        await canvas_apply_ops_impl(memory_db, seed_user.id, "ws_missing", [{"op": "add_panel"}])
    assert e.value.status_code == 404

    with pytest.raises(HTTPException) as e:
        await canvas_apply_ops_impl(memory_db, seed_user.id, "ws_mine", [{"op": "unknown_kind"}])
    assert e.value.status_code == 400  # 全部失败不写回

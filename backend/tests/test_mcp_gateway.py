# =====================================================
# MCP 网关单测 —— overview 分页纯函数（TS 对齐）/ 内容摘要 / 工具 impl（db+user_id 直测）
# =====================================================


import pytest
from fastapi import HTTPException

from app.models.asset import Asset
from app.models.canvas_workspace import CanvasWorkspace
from app.services import mcp_gateway
from app.services.mcp_gateway import (
    asset_list_impl,
    canvas_apply_ops_impl,
    canvas_create_impl,
    canvas_list_impl,
    canvas_overview_impl,
    editor_create_project_impl,
    editor_get_document_impl,
    editor_list_projects_impl,
    editor_put_document_impl,
    generation_get_impl,
    image_generate_impl,
    model_list_impl,
    overview_page,
    panel_content_summary,
    parse_overview_cursor,
    video_generate_impl,
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


# ---------- 编辑器 impl：list / create / get / put 文档 ----------
@pytest.mark.asyncio
async def test_editor_impl_document_flow(memory_db, seed_user):
    created = await editor_create_project_impl(memory_db, seed_user.id, "CLI 工程", None)
    assert created["ok"] is True and created["title"] == "CLI 工程"
    uid = created["uid"]

    listing = await editor_list_projects_impl(memory_db, seed_user.id, None)
    assert [p["uid"] for p in listing["items"]] == [uid]

    detail = await editor_get_document_impl(memory_db, seed_user.id, uid)
    revision = detail["revision"]
    assert detail["document"] is not None or detail["document"] == {}

    saved = await editor_put_document_impl(
        memory_db, seed_user.id, uid,
        {"timebase": 30, "width": 1280, "height": 720, "tracks": [], "clips": []}, revision, "CLI 写入",
    )
    assert saved["ok"] is True and saved["revision"] == revision + 1

    # 乐观锁：旧 revision 冲突 409
    with pytest.raises(HTTPException) as e:
        await editor_put_document_impl(
            memory_db, seed_user.id, uid,
            {"timebase": 30, "width": 1280, "height": 720, "tracks": [], "clips": []}, revision, None,
        )
    assert e.value.status_code == 409


# ---------- 素材清单 impl ----------
@pytest.mark.asyncio
async def test_asset_list_impl(memory_db, seed_user):
    memory_db.add(Asset(type="material", user_id=seed_user.id, name="主图", kind="image", asset_url="http://x/a.png",
                        visual_description="一张主图", source="upload"))
    memory_db.add(Asset(type="material", user_id=seed_user.id, name="片段", kind="video", asset_url="http://x/b.mp4",
                        visual_description="一段视频", source="upload"))
    await memory_db.commit()

    result = await asset_list_impl(memory_db, seed_user.id, "video", None, None, 1, 50)
    assert result["ok"] is True and result["total"] == 1
    assert result["items"][0]["name"] == "片段"

    everything = await asset_list_impl(memory_db, seed_user.id, None, None, None, 1, 50)
    assert everything["total"] == 2


# ---------- 模型清单 impl（打桩 registry） ----------
@pytest.mark.asyncio
async def test_model_list_impl(monkeypatch):
    class M:
        def __init__(self, id, type):
            self.id, self.name, self.type, self.provider, self.capabilities = id, id, type, "Agnes", []

    async def fake_by_type(t):
        return [M(f"agnes-{t}-1", t)]

    async def fake_all():
        return [M("agnes-image-1", "image"), M("agnes-video-1", "video"), M("chat-1", "chat")]

    monkeypatch.setattr(mcp_gateway, "get_models_by_type", fake_by_type)
    monkeypatch.setattr(mcp_gateway, "get_all_models", fake_all)

    assert [m["id"] for m in (await model_list_impl("video"))["items"]] == ["agnes-video-1"]
    assert len((await model_list_impl(None))["items"]) == 3


# ---------- 生成 impl：请求映射与 generation_get 三分支（路由函数打桩） ----------
@pytest.mark.asyncio
async def test_generate_impl_mapping(memory_db, seed_user, monkeypatch):
    captured = {}

    async def fake_image(req, db, user):
        captured["image"] = req
        return {"status": "success", "data": {"task_id": "img_1", "status": "pending"}}

    async def fake_video(req, db, user):
        captured["video"] = req
        return {"status": "success", "data": {"task_id": "vid_1", "video_id": "v9", "status": "pending"}}

    monkeypatch.setattr(mcp_gateway, "create_image_task_async", fake_image)
    monkeypatch.setattr(mcp_gateway, "create_video_task", fake_video)

    img = await image_generate_impl(memory_db, seed_user, "一只猫", None, None, ["http://r/1.png"])
    assert img["ok"] is True and img["task_id"] == "img_1"
    assert captured["image"].image_urls == ["http://r/1.png"]  # 图生图

    vid = await video_generate_impl(memory_db, seed_user, "跑动", "agnes-video-2", "9:16", 5.0, None)
    assert vid["ok"] is True and vid["task_id"] == "vid_1"
    assert captured["video"].mode == "text2video" and captured["video"].aspect_ratio == "9:16"

    with_refs = await video_generate_impl(memory_db, seed_user, "跑动", None, None, None, ["http://r/1.png"])
    assert with_refs["ok"] is True
    assert captured["video"].mode == "image2video"


@pytest.mark.asyncio
async def test_generation_get_impl_three_branches(memory_db, seed_user, monkeypatch):
    async def image_status(task_id, db, current_user):
        if task_id == "img_ok":
            return {"status": "success", "data": {"task_id": task_id, "status": "success", "result_url": "http://x/1.png"}}
        raise HTTPException(status_code=404, detail="未找到任务")

    async def video_status(task_id, db, current_user):
        if task_id == "vid_ok":
            from pydantic import BaseModel

            class R(BaseModel):
                task_id: str
                status: str
                progress: int

            return {"status": "success", "data": R(task_id=task_id, status="processing", progress=40)}
        raise HTTPException(status_code=404, detail="未找到任务")

    monkeypatch.setattr(mcp_gateway, "get_image_task_status", image_status)
    monkeypatch.setattr(mcp_gateway, "get_video_status", video_status)

    result = await generation_get_impl(memory_db, seed_user, ["img_ok", "vid_ok", "ghost"])
    items = {i.get("task_id") or i.get("id"): i for i in result["items"]}
    assert items["img_ok"]["kind"] == "image" and items["img_ok"]["result_url"] == "http://x/1.png"
    assert items["vid_ok"]["kind"] == "video" and items["vid_ok"]["status"] == "processing"
    assert items["ghost"]["status"] == "not_found"

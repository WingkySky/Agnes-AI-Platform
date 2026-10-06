# =====================================================
# 剪辑渲染测试
# - Plan 派生纯函数黄金测试（轨道分组/render_start 转场压缩/黑场 gap/字幕事件）
# - lowering 命令结构断言（不执行 ffmpeg）
# - 提交幂等 / 空时间线 400 / 启动复位 stale rendering
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.future import select as _select

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.editing_project import RENDER_FAILED, RENDER_RENDERING, EditingProject
from app.models.user import User
from app.services.editor.plan_builder import build_plan, timeline_total
from app.services.editor.render_service import (
    _audio_filter_for,
    _segment_normalize_cmd,
    _xfade_name,
    build_render_command,
    reset_stale_rendering,
)

pytestmark = pytest.mark.asyncio


def _doc():
    return {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "v2", "kind": "video", "order": 1, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {}},
            {"id": "s1", "kind": "subtitle", "order": 0, "flags": {}},
        ],
        "clips": [
            {"id": "c1", "trackId": "v1", "assetId": 1, "start": 0, "duration": 4, "trimStart": 1,
             "props": {"transition": {"type": "crossfade", "duration": 0.5}}},
            {"id": "c2", "trackId": "v1", "assetId": 2, "start": 4, "duration": 3, "trimStart": 0, "props": {}},
            {"id": "p1", "trackId": "v2", "assetId": 3, "start": 1, "duration": 2, "trimStart": 0,
             "props": {"rect": {"x": 0.6, "y": 0.6, "w": 0.3, "h": 0.3}}},
            {"id": "a9", "trackId": "a1", "assetId": 4, "start": 0, "duration": 2, "trimStart": 0.5,
             "props": {"volume": 0.8, "fadeIn": 0.3}},
            {"id": "s9", "trackId": "s1", "assetId": None, "start": 0.5, "duration": 1.5,
             "trimStart": 0, "props": {}, "text": "你好字幕"},
        ],
        "subtitleStyle": {"font": "Noto Sans CJK SC", "size": 48, "color": "#FFFFFF",
                          "outline": True, "position": "bottom"},
    }


PATHS = {1: "/tmp/a.mp4", 2: "/tmp/b.mp4", 3: "/tmp/p.png", 4: "/tmp/v.mp3"}


# ---------- Plan 黄金测试 ----------

def test_plan_video_tracks_and_transition_compression():
    plan = build_plan(_doc(), lambda aid: PATHS.get(aid))
    assert plan is not None
    assert plan["width"] == 1280 and plan["height"] == 720
    # 主轨两段：c1 render_start=0，转场压缩 0.5 → c2 render_start=3.5，轨 total=6.5
    v1 = next(t for t in plan["video_tracks"] if t["track_id"] == "v1")
    assert [s["clip_id"] for s in v1["segments"]] == ["c1", "c2"]
    assert v1["segments"][0]["render_start"] == 0
    assert v1["segments"][1]["render_start"] == 3.5
    assert v1["total"] == 6.5
    assert v1["segments"][0]["transition_applied"] == {"type": "crossfade", "duration": 0.5}
    # PIP 轨：无转场，render_start 为文档绝对位置（overlay enable 窗口用）
    v2 = next(t for t in plan["video_tracks"] if t["track_id"] == "v2")
    assert v2["segments"][0]["render_start"] == 1
    assert v2["segments"][0]["rect"] == {"x": 0.6, "y": 0.6, "w": 0.3, "h": 0.3}
    # 音频保留时间线 start（adelay 定位）
    audio = plan["audio_clips"][0]
    assert audio["start"] == 0 and audio["render_start"] == 0 and audio["volume"] == 0.8
    # 字幕事件
    assert plan["subtitle_events"] == [{"start": 0.5, "end": 2.0, "text": "你好字幕"}]
    # 总时长 = max(轨 total 6.5, 音频 2) = 6.5
    assert timeline_total(plan) == 6.5


def test_plan_gap_preserved_and_unavailable_assets_dropped():
    doc = _doc()
    # c2 缺素材被剔除 → 主轨只剩 c1
    plan = build_plan(doc, lambda aid: PATHS.get(aid) if aid != 2 else None)
    v1 = next(t for t in plan["video_tracks"] if t["track_id"] == "v1")
    assert [s["clip_id"] for s in v1["segments"]] == ["c1"]
    assert v1["segments"][0]["transition_applied"] is None
    # 全部素材不可用 → None
    assert build_plan(doc, lambda aid: None) is None


def test_plan_duration_zero_dropped():
    doc = _doc()
    doc["clips"][3]["duration"] = 0  # 草稿占位片段
    plan = build_plan(doc, lambda aid: PATHS.get(aid))
    assert plan["audio_clips"] == []


# ---------- 轨道开关：hidden 剔整轨 / muted 剔声留画 / solo 监听态不入成片 ----------

def test_plan_hidden_track_excluded_entirely():
    doc = _doc()
    doc["tracks"][0]["flags"] = {"hidden": True}  # v1 整轨剔除
    plan = build_plan(doc, lambda aid: PATHS.get(aid), _kinds)
    assert {t["track_id"] for t in plan["video_tracks"]} == {"v2"}
    # 隐藏视频轨的自带音频也一并剔除
    assert {s["clip_id"] for s in plan["audio_clips"]} == {"a9"}
    doc["tracks"][2]["flags"] = {"hidden": True}  # 静音音频轨（hidden 同样剔除）
    plan2 = build_plan(doc, lambda aid: PATHS.get(aid), _kinds)
    assert plan2["audio_clips"] == []


def test_plan_muted_track_drops_audio_keeps_video():
    doc = _doc()
    doc["tracks"][0]["flags"] = {"muted": True}  # v1 静音：画面在、自带音频剔
    plan = build_plan(doc, lambda aid: PATHS.get(aid), _kinds)
    assert {t["track_id"] for t in plan["video_tracks"]} == {"v1", "v2"}
    assert {s["clip_id"] for s in plan["audio_clips"]} == {"a9"}
    doc["tracks"][2]["flags"] = {"muted": True}  # a1 静音：音频图清空
    plan2 = build_plan(doc, lambda aid: PATHS.get(aid), _kinds)
    assert plan2["audio_clips"] == []


def test_plan_hidden_subtitle_track_no_events_and_solo_ignored():
    doc = _doc()
    doc["tracks"][3]["flags"] = {"hidden": True}
    plan = build_plan(doc, lambda aid: PATHS.get(aid))
    assert plan["subtitle_events"] == []
    # solo 是预览监听态：不影响成片
    doc["tracks"][3]["flags"] = {"solo": True}
    doc["tracks"][0]["flags"] = {"solo": True}
    plan2 = build_plan(doc, lambda aid: PATHS.get(aid))
    assert plan2["subtitle_events"] == [{"start": 0.5, "end": 2.0, "text": "你好字幕"}]
    assert {t["track_id"] for t in plan2["video_tracks"]} == {"v1", "v2"}


# ---------- 音画分离：视频自带音频进 Plan/命令 ----------

def _kinds(aid):
    return {1: "video", 2: "video", 3: "image", 4: "audio"}.get(aid)


def test_plan_video_audio_candidates_and_muted():
    plan = build_plan(_doc(), lambda aid: PATHS.get(aid), _kinds)
    audio_ids = {s["clip_id"] for s in plan["audio_clips"]}
    # 未静音视频片段自带音频进音频图；图片素材/静音标记剔除
    assert audio_ids == {"c1", "c2", "a9"}
    muted = _doc()
    muted["clips"][0]["props"]["muted"] = True  # 音画分离后源片段
    plan2 = build_plan(muted, lambda aid: PATHS.get(aid), _kinds)
    assert {s["clip_id"] for s in plan2["audio_clips"]} == {"c2", "a9"}
    # 不传 kind 解析器 = 旧行为（视频自带音频不进 Plan）
    plan3 = build_plan(_doc(), lambda aid: PATHS.get(aid))
    assert {s["clip_id"] for s in plan3["audio_clips"]} == {"a9"}


def test_render_command_with_video_audio_candidates():
    plan = build_plan(_doc(), lambda aid: PATHS.get(aid), _kinds)
    normalized = {"c1": "/tmp/n1.mp4", "c2": "/tmp/n2.mp4", "p1": "/tmp/n3.mp4"}
    cmd = build_render_command(plan, normalized, None, "/tmp/final.mp4")
    text = " ".join(cmd)
    graph = cmd[cmd.index("-filter_complex") + 1]
    # 输入：基座 1 + 视频段 3 + 音频 3（c1/c2 视频自带 + a9 音频轨）= 7 个 -i
    assert text.count(" -i ") == 7
    # 视频自带音频走同一 atempo/volume/afade/adelay 链（c2 start=4 → adelay 4000）
    assert "adelay=4000:all=1" in graph
    assert "amix=inputs=3" in graph


def test_render_command_two_fullframe_tracks_offset_windows():
    """回归：两个全帧片段分属两条视频轨——各轨按时间线位置开窗，上层轨不得从头遮盖下层轨"""
    doc = _doc()
    doc["clips"] = [
        {"id": "cA", "trackId": "v1", "assetId": 1, "start": 0, "duration": 5.042, "trimStart": 0, "props": {}},
        {"id": "cB", "trackId": "v2", "assetId": 2, "start": 5.042, "duration": 3.375, "trimStart": 0, "props": {}},
    ]
    plan = build_plan(doc, lambda aid: PATHS.get(aid), lambda aid: "video")
    v2 = next(t for t in plan["video_tracks"] if t["track_id"] == "v2")
    assert v2["chain_start"] == 5.042 and v2["total"] == 3.375
    cmd = build_render_command(plan, {"cA": "/tmp/nA.mp4", "cB": "/tmp/nB.mp4"}, None, "/tmp/f.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=0:0:enable='between(t,0.000,5.042)'" in graph
    # 上层轨 pts 平移到锚点（否则 overlay 按主时间轴取帧会跳到 eof 冻结末帧）
    assert "[2:v]setpts=PTS+5.042/TB" in graph
    assert "overlay=0:0:enable='between(t,5.042,8.417)'" in graph
    # 音频轴与视频窗同源：后段自带音频 adelay 在其文档位置
    assert "adelay=5042:all=1" in graph


# ---------- lowering 命令结构 ----------

def test_normalize_cmd_structure():
    seg = {"clip_id": "c1", "asset_path": "/tmp/a.mp4", "duration": 4, "trim_start": 1,
           "speed": 2, "rect": None}
    cmd = _segment_normalize_cmd(seg, 1280, 720, 30, "/tmp/out.mp4")
    assert cmd[cmd.index("-ss") + 1] == "1"
    assert cmd[cmd.index("-t") + 1] == "8.000000"  # 源跨度 = duration * speed
    assert "setpts=PTS/2" in cmd[cmd.index("-vf") + 1]
    assert "scale=1280:720" in cmd[cmd.index("-vf") + 1]
    assert "-an" in cmd


def test_render_command_fullframe_xfade_and_pip():
    plan = build_plan(_doc(), lambda aid: PATHS.get(aid))
    normalized = {"c1": "/tmp/n1.mp4", "c2": "/tmp/n2.mp4", "p1": "/tmp/n3.mp4"}
    cmd = build_render_command(plan, normalized, None, "/tmp/final.mp4")
    text = " ".join(cmd)
    graph = cmd[cmd.index("-filter_complex") + 1]
    # 输入：黑底基座 + 主轨两段 + PIP 一段 + 音频一段 = 5 个 -i
    assert text.count(" -i ") == 5
    # xfade 链（主轨内转场压缩 offset=3.5）+ PIP overlay（绝对窗口 + pts 平移）
    assert "xfade=transition=fade:duration=0.500:offset=3.500" in graph
    assert "setpts=PTS+1.000/TB" in graph
    assert "overlay=768:432:enable='between(t,1.000,3.000)'" in graph
    # 音频链：volume/afade + 统一重采样（start=0 无 adelay）
    assert "[4:a]volume=0.8,afade=t=in:st=0:d=0.3,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[ad0]" in graph
    assert "-pix_fmt" in cmd and cmd[-1] == "/tmp/final.mp4"


def test_render_command_subtitle_filter_escaped():
    plan = build_plan(_doc(), lambda aid: PATHS.get(aid))
    normalized = {"c1": "/tmp/n1.mp4", "c2": "/tmp/n2.mp4", "p1": "/tmp/n3.mp4"}
    cmd = build_render_command(plan, normalized, "/tmp/subs_x.ass", "/tmp/final.mp4")
    assert any("subtitles=filename='/tmp/subs_x.ass'" in f for f in cmd)


def test_xfade_name_and_audio_filter():
    assert _xfade_name("crossfade") == "fade"
    assert _xfade_name("fade") == "fadeblack"
    assert _xfade_name("wipe") == "wipeleft"
    seg = {"speed": 1.0, "volume": 0.8, "fade_in": 0.3, "fade_out": 0, "duration": 2}
    assert _audio_filter_for(seg) == "volume=0.8,afade=t=in:st=0:d=0.3"
    # 4x 变速 → atempo 链 2.0,2.0
    assert _audio_filter_for({**seg, "speed": 4.0, "volume": 1.0, "fade_in": 0}).startswith("atempo=2.0,atempo=2.0")


# ---------- 端点行为 ----------

async def _noop_task(uid):
    return None


async def _client_with(memory_db, user):
    async def _override_db():
        yield memory_db
    app.dependency_overrides[get_async_db] = _override_db
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


async def test_submit_render_empty_timeline_400(memory_db, monkeypatch):
    from app.services.editor import render_service

    user = User(username="u1", email="u1@example.com", password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    monkeypatch.setattr(render_service, "_render_task", _noop_task)
    client = await _client_with(memory_db, user)
    try:
        uid = (await client.post("/api/editor/projects", json={"title": "x"})).json()["data"]["uid"]
        resp = await client.post(f"/api/editor/projects/{uid}/render", json={})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


async def test_submit_render_idempotent_and_stale_reset(memory_db, monkeypatch):
    from app.models.asset import Asset
    from app.services.editor import render_service

    user = User(username="u1", email="u1@example.com", password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    for aid, kind in [(1, "video"), (2, "video"), (3, "image"), (4, "audio")]:
        memory_db.add(Asset(id=aid, type="material", name=f"a{aid}", description=None, visual_description="",
                            user_id=user.id, is_public=False, tags=[], version=1,
                            source="upload", kind=kind, asset_url=f"/uploads/{aid}.mp4"))
    await memory_db.commit()
    monkeypatch.setattr(render_service, "_render_task", _noop_task)
    client = await _client_with(memory_db, user)
    try:
        uid = (await client.post("/api/editor/projects", json={"title": "x", "document": _doc()})).json()["data"]["uid"]

        # 提交成功（后台任务被桩掉，状态停在 rendering）
        resp = await client.post(f"/api/editor/projects/{uid}/render", json={"client_operation_id": "op1"})
        assert resp.status_code == 200
        assert resp.json()["data"]["render_status"] == RENDER_RENDERING

        # rendering 中重复提交幂等
        resp2 = await client.post(f"/api/editor/projects/{uid}/render", json={"client_operation_id": "op2"})
        assert resp2.json()["data"]["render_status"] == RENDER_RENDERING

        # 轮询端点
        resp3 = await client.get(f"/api/editor/projects/{uid}/render")
        assert resp3.json()["data"]["render_status"] == RENDER_RENDERING

        # 手动制造 stale → 启动复位
        project = (await memory_db.scalars(
            _select(EditingProject).where(EditingProject.uid == uid)
        )).first()
        project.render_status = RENDER_RENDERING
        project.render_progress = "3/8"
        await memory_db.commit()
        await reset_stale_rendering(memory_db)
        await memory_db.refresh(project)
        assert project.render_status == RENDER_FAILED
        assert project.render_progress is None
        assert "中断" in project.render_error
    finally:
        app.dependency_overrides.clear()

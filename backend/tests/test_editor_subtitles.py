# =====================================================
# 剪辑器字幕转写端点测试（POST /api/editor/projects/{uid}/subtitles/preview）
# whisper 打桩隔离（不依赖 faster-whisper 安装）；轨道校验；时间映射
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.media.transcribe_service as transcribe_service
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.asset import Asset
from app.models.user import User

pytestmark = pytest.mark.asyncio

URL = "/api/editor/projects"


def _doc():
    return {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {}},
            {"id": "s1", "kind": "subtitle", "order": 0, "flags": {}},
        ],
        "clips": [
            {"id": "c-a1", "trackId": "a1", "assetId": 1, "start": 2.0,
             "duration": 4.0, "trimStart": 1.0, "props": {}},
        ],
    }


def _override_db_factory(memory_db):
    async def _override_db():
        yield memory_db
    return _override_db


async def test_preview_requires_track_and_whisper(memory_db, monkeypatch):
    from app.services.editor import transcribe_bridge

    user = User(username="u1", email="u1@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    memory_db.add(Asset(id=1, type="material", name="配音", description=None, visual_description="",
                        user_id=user.id, is_public=False, tags=[], version=1,
                        source="upload", kind="audio", asset_url="/uploads/a.mp3"))
    await memory_db.commit()
    await memory_db.refresh(user)
    app.dependency_overrides[get_async_db] = _override_db_factory(memory_db)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=headers) as client:
            uid = (await client.post(URL, json={"title": "x", "document": _doc()})).json()["data"]["uid"]

            # 轨道不存在 404 / 非音视频轨 400（字幕轨不可转写）
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "vx"})
            assert resp.status_code == 404
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "s1"})
            assert resp.status_code == 400

            # faster-whisper 未安装 → 503
            monkeypatch.setattr(transcribe_bridge, "is_whisper_available", lambda: False)
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "a1"})
            assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()


async def test_preview_time_mapping(memory_db, monkeypatch):
    """trimStart 偏移 + 片段时间线定位 + 越界截断"""
    from app.services.editor import transcribe_bridge

    user = User(username="u1", email="u1@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    asset = Asset(id=1, type="material", name="配音", description=None, visual_description="",
                  user_id=user.id, is_public=False, tags=[], version=1,
                  source="upload", kind="audio", asset_url="/uploads/a.mp3")
    memory_db.add(asset)
    await memory_db.commit()
    app.dependency_overrides[get_async_db] = _override_db_factory(memory_db)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    # 打桩：转写返回源内时间（trimStart=1.0 之后的段落才应出现）
    async def _fake_transcribe(path, language="zh", **kw):
        return [
            {"start": 0.2, "end": 0.8, "text": "早于入点丢弃"},
            {"start": 1.5, "end": 2.5, "text": "你好世界"},
            {"start": 4.0, "end": 6.0, "text": "尾部截断"},
        ]

    async def _fake_resolve(asset, tmp_dir):
        return "/tmp/fake.mp3"

    monkeypatch.setattr(transcribe_bridge, "is_whisper_available", lambda: True)
    monkeypatch.setattr(transcribe_bridge, "transcribe_audio", _fake_transcribe)
    monkeypatch.setattr(transcribe_bridge, "resolve_asset_local_file", _fake_resolve)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=headers) as client:
            uid = (await client.post(URL, json={"title": "x", "document": _doc()})).json()["data"]["uid"]
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "a1"})
        assert resp.status_code == 200
        segs = resp.json()["data"]["segments"]
        # clip.start=2.0, trimStart=1.0：源 1.5-2.5 → 时间线 2.5-3.5；源 4.0-6.0 截断到片段尾 6.0 → 5.0-6.0
        assert [(s["start"], s["end"], s["text"]) for s in segs] == [
            (2.5, 3.5, "你好世界"), (5.0, 6.0, "尾部截断")]
    finally:
        app.dependency_overrides.clear()


def test_transcribe_service_exports():
    """公共域导出齐全（项目域兼容 re-export）"""
    assert hasattr(transcribe_service, "is_whisper_available")
    assert hasattr(transcribe_service, "get_whisper_model")
    assert hasattr(transcribe_service, "transcribe_audio")


def _av_doc():
    """视频轨 + 音频轨各一片段（视频轨可作转写源）"""
    return {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 1, "flags": {}},
        ],
        "clips": [
            {"id": "c-v1", "trackId": "v1", "assetId": 2, "start": 1.0, "duration": 3.0,
             "trimStart": 0.5, "props": {}},
            {"id": "c-a1", "trackId": "a1", "assetId": 1, "start": 2.0, "duration": 4.0,
             "trimStart": 1.0, "props": {}},
        ],
    }


async def test_preview_video_track_source(memory_db, monkeypatch):
    """视频轨作为转写源：视频素材文件直接交 whisper（decode_audio 解容器音轨）"""
    from app.services.editor import transcribe_bridge

    user = User(username="u1", email="u1@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    for aid, kind in ((1, "audio"), (2, "video")):
        memory_db.add(Asset(id=aid, type="material", name=f"素材{aid}", description=None,
                            visual_description="", user_id=user.id, is_public=False, tags=[],
                            version=1, source="upload", kind=kind, asset_url=f"/uploads/{aid}.mp4"))
    await memory_db.commit()
    app.dependency_overrides[get_async_db] = _override_db_factory(memory_db)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    async def _fake_transcribe(path, language="zh", **kw):
        return [{"start": 1.0, "end": 2.0, "text": "视频里的话"}]

    async def _fake_resolve(asset, tmp_dir):
        return "/tmp/fake.mp4"

    monkeypatch.setattr(transcribe_bridge, "is_whisper_available", lambda: True)
    monkeypatch.setattr(transcribe_bridge, "transcribe_audio", _fake_transcribe)
    monkeypatch.setattr(transcribe_bridge, "resolve_asset_local_file", _fake_resolve)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=headers) as client:
            create_resp = await client.post(URL, json={"title": "x", "document": _av_doc()})
            assert create_resp.status_code == 200, create_resp.text
            uid = create_resp.json()["data"]["uid"]
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "v1"})
        assert resp.status_code == 200
        segs = resp.json()["data"]["segments"]
        # clip.start=1.0, trimStart=0.5：源 1.0-2.0 → 时间线 1.5-2.5
        assert [(s["start"], s["end"], s["text"]) for s in segs] == [(1.5, 2.5, "视频里的话")]
    finally:
        app.dependency_overrides.clear()


async def test_preview_skips_failing_clips(memory_db, monkeypatch):
    """单片段转写失败（无声视频等）跳过不阻塞整轨"""
    from app.services.editor import transcribe_bridge

    user = User(username="u1", email="u1@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    for aid in (1, 2, 3):
        memory_db.add(Asset(id=aid, type="material", name=f"素材{aid}", description=None,
                            visual_description="", user_id=user.id, is_public=False, tags=[],
                            version=1, source="upload", kind="audio", asset_url=f"/uploads/a{aid}.mp3"))
    await memory_db.commit()
    app.dependency_overrides[get_async_db] = _override_db_factory(memory_db)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    async def _resolve(asset, tmp_dir):
        return "/tmp/bad.mp3" if asset.id == 3 else "/tmp/ok.mp3"

    async def _fake_transcribe(path, language="zh", **kw):
        if "bad" in path:
            raise RuntimeError("no audio stream")
        # 源内 1.5-2.5s（trimStart=1.0 之内）→ 时间线 2.5-3.5
        return [{"start": 1.5, "end": 2.5, "text": "正常片段"}]

    monkeypatch.setattr(transcribe_bridge, "is_whisper_available", lambda: True)
    monkeypatch.setattr(transcribe_bridge, "transcribe_audio", _fake_transcribe)
    monkeypatch.setattr(transcribe_bridge, "resolve_asset_local_file", _resolve)

    doc = _av_doc()
    # 音频轨追加第二个片段（asset 3 = 坏素材）
    doc["clips"].append({"id": "c-a2", "trackId": "a1", "assetId": 3, "start": 6.0,
                         "duration": 2.0, "trimStart": 0.0, "props": {}})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=headers) as client:
            create_resp = await client.post(URL, json={"title": "x", "document": doc})
            assert create_resp.status_code == 200, create_resp.text
            uid = create_resp.json()["data"]["uid"]
            resp = await client.post(f"{URL}/{uid}/subtitles/preview", json={"track_id": "a1"})
        assert resp.status_code == 200
        segs = resp.json()["data"]["segments"]
        # 只有 asset 1 出草稿（clip.start=2.0, trimStart=1.0 → 时间线 2.5-3.5），坏片段跳过
        assert [(s["start"], s["end"], s["text"]) for s in segs] == [(2.5, 3.5, "正常片段")]
    finally:
        app.dependency_overrides.clear()

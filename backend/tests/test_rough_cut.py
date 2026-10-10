# =====================================================
# AI 粗剪分析测试（/api/editor/assets/{id}/analyze + 检测层）
# 401 未登录 / 404 他人素材 / 400 非媒体；scenes 三段切分 / silence 静音剔除（真实编码视频端到端）
# =====================================================

import math

import av
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.asset import Asset
from app.models.user import User
from app.services.editor.rough_cut_service import _norm_segments, detect_scenes, detect_silence_speech

pytestmark = pytest.mark.asyncio

URL = "/api/editor/assets"


# ---------- 测试视频：红(有声) 3s + 蓝(静音) 3s + 绿(有声) 3s，15fps 320x240 ----------

@pytest.fixture(scope="session")
def test_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("rough") / "three_scenes.mp4"
    container = av.open(str(path), "w")
    vs = container.add_stream("mpeg4", rate=15)
    vs.width, vs.height, vs.pix_fmt = 320, 240, "yuv420p"
    as_ = container.add_stream("aac", rate=44100)
    as_.layout = "mono"

    def _frame(t: float) -> av.VideoFrame:
        color = {"r": 200, "g": 40, "b": 40} if t < 3 else {"r": 40, "g": 40, "b": 200} if t < 6 else {"r": 40, "g": 200, "b": 40}
        img = np.full((240, 320, 3), [color["r"], color["g"], color["b"]], dtype=np.uint8)
        f = av.VideoFrame(320, 240, "rgb24")
        f.planes[0].update(img.tobytes())
        return f

    audio_pts = 0.0
    for i in range(135):
        pkt = vs.encode(_frame(i / 15))
        container.mux(pkt)
        # 音频按 1024 采样/帧推进到 9s：0~3s 与 6~9s 440Hz 正弦，3~6s 数字静音
        while audio_pts < (i + 1) / 15 and audio_pts < 9.0:
            samples = 1024
            seg_t = np.arange(samples) / 44100.0
            if 3.0 <= audio_pts < 6.0:
                data = np.zeros(samples, dtype=np.float32)
            else:
                data = (0.5 * np.sin(2 * math.pi * 440 * (audio_pts + seg_t))).astype(np.float32)
            af = av.AudioFrame.from_ndarray(data.reshape(1, -1), format="flt", layout="mono")
            af.sample_rate = 44100
            af.pts = int(audio_pts * 44100)
            for p in as_.encode(af):
                container.mux(p)
            audio_pts += samples / 44100.0
    for p in vs.encode(None):
        container.mux(p)
    for p in as_.encode(None):
        container.mux(p)
    container.close()
    return str(path)


# ---------- 检测层（真实视频端到端） ----------

async def test_detect_scenes_three_color_bands(test_video):
    r = detect_scenes(test_video)
    segs = r["segments"]
    assert len(segs) == 3
    assert abs(segs[0]["end"] - 3.0) < 0.5
    assert abs(segs[1]["start"] - 3.0) < 0.5
    assert abs(segs[2]["end"] - 9.0) < 0.5
    assert r["duration_total"] == pytest.approx(9.0, abs=0.2)


async def test_detect_silence_removes_middle(test_video):
    r = detect_silence_speech(test_video)
    segs = r["segments"]
    assert len(segs) == 2
    # 中段 3~6s 数字静音被剔除，首尾保留
    assert segs[0]["end"] <= 3.4
    assert segs[1]["start"] >= 5.6
    assert 0.6 <= r["kept_ratio"] <= 0.72


async def test_detect_silence_threshold_above_signal_keeps_all(test_video):
    # 阈值低于一切信号（-120 之下不再有真静音）→ 全片判有声
    r = detect_silence_speech(test_video, threshold_db=-130.0)
    assert r["kept_ratio"] == 1.0


def test_norm_segments_merge_and_clamp():
    # 相邻不合并（切点天然首尾相接），真重叠合并，碎段剔除（含钳位后变碎的），越界钳位
    segs = _norm_segments([(0, 3), (3, 6), (6, 9)], 9.0, min_keep=0.5)
    assert len(segs) == 3
    segs = _norm_segments([(0, 2), (1.5, 4)], 9.0, min_keep=0.5)
    assert segs == [{"start": 0.0, "end": 4.0}]
    segs = _norm_segments([(-1, 0.2), (3, 3.2), (5, 99)], 9.0, min_keep=0.5)
    assert segs == [{"start": 5.0, "end": 9.0}]


# ---------- 端点 ----------

async def _seed_asset(memory_db, user: User, kind: str, url: str, storage_key: str | None = None) -> Asset:
    asset = Asset(
        user_id=user.id, type=kind, kind=kind, name=f"{kind}-素材", description="",
        visual_description="测试素材", reference_images=[], is_public=False,
        moderation_status="approved", asset_url=url, storage_key=storage_key,
    )
    memory_db.add(asset)
    await memory_db.commit()
    await memory_db.refresh(asset)
    return asset


async def _build_client(memory_db, user: User | None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def test_analyze_anon_401(memory_db, test_video):
    user = await _seed_user_test(memory_db)
    asset = await _seed_asset(memory_db, user, "video", "/uploads/rough-cut/none.mp4")
    async for client in _build_client(memory_db, None):
        r = await client.post(f"{URL}/{asset.id}/analyze", json={"mode": "scenes"})
        assert r.status_code == 401


async def _seed_user_test(memory_db) -> User:
    user = User(username="roughcut_user", email="roughcut@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def test_analyze_other_user_404(memory_db, test_video):
    owner = await _seed_user_test(memory_db)
    other = User(username="other_rc", email="other_rc@example.com",
                 password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(other)
    await memory_db.commit()
    await memory_db.refresh(other)
    asset = await _seed_asset(memory_db, owner, "video", "/uploads/rough-cut/none.mp4")
    async for client in _build_client(memory_db, other):
        r = await client.post(f"{URL}/{asset.id}/analyze", json={"mode": "scenes"})
        assert r.status_code == 404


async def test_analyze_non_media_400(memory_db):
    user = await _seed_user_test(memory_db)
    asset = await _seed_asset(memory_db, user, "image", "/uploads/rough-cut/x.png")
    async for client in _build_client(memory_db, user):
        r = await client.post(f"{URL}/{asset.id}/analyze", json={"mode": "scenes"})
        assert r.status_code == 400


async def test_analyze_bad_mode_400(memory_db):
    user = await _seed_user_test(memory_db)
    asset = await _seed_asset(memory_db, user, "video", "/uploads/rough-cut/none.mp4")
    async for client in _build_client(memory_db, user):
        r = await client.post(f"{URL}/{asset.id}/analyze", json={"mode": "magic"})
        assert r.status_code == 400


async def test_analyze_scenes_local_file_200(memory_db, test_video):
    """本地路径素材（storage_key 指向 uploads 真实文件）→ 场景切分三段"""
    import shutil
    from app.services.upload_service import UPLOADS_DIR

    user = await _seed_user_test(memory_db)
    key = "rough-cut/three_scenes.mp4"
    from pathlib import Path
    dest = Path(UPLOADS_DIR) / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_video, dest)
    try:
        asset = await _seed_asset(memory_db, user, "video", f"/uploads/{key}", storage_key=key)
        async for client in _build_client(memory_db, user):
            r = await client.post(f"{URL}/{asset.id}/analyze", json={"mode": "scenes"})
            assert r.status_code == 200
            data = r.json()["data"]
            assert len(data["segments"]) == 3
            assert data["duration_total"] == pytest.approx(9.0, abs=0.2)
    finally:
        dest.unlink(missing_ok=True)


async def test_analyze_silence_local_file_200(memory_db, test_video):
    import shutil
    from app.services.upload_service import UPLOADS_DIR

    user = await _seed_user_test(memory_db)
    key = "rough-cut/silence.mp4"
    from pathlib import Path
    dest = Path(UPLOADS_DIR) / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_video, dest)
    try:
        asset = await _seed_asset(memory_db, user, "video", f"/uploads/{key}", storage_key=key)
        async for client in _build_client(memory_db, user):
            r = await client.post(
                f"{URL}/{asset.id}/analyze",
                json={"mode": "silence", "params": {"threshold_db": -30.0}},
            )
            assert r.status_code == 200
            data = r.json()["data"]
            assert len(data["segments"]) == 2
            assert 0.6 <= data["kept_ratio"] <= 0.72
    finally:
        dest.unlink(missing_ok=True)

# =====================================================
# 剪辑成片导出单测
# - GIF/音频命令构建（纯函数）
# - export_final 服务（monkeypatch probe/ffmpeg/配额记账，tmp_path 收口）
# - 剪映草稿 build_draft 黄金测试（微秒时间/轨序/PIP 变换/字幕任务/素材登记/转场挂载）
# - 剪映 zip 全链（fake db + 桩素材本地化，断言 zip 清单与 JSON 可解析）
# =====================================================

import json
import zipfile
from pathlib import Path

import pytest

from app.services.editor import export_service
from app.services.editor.export_service import (
    build_audio_cmd,
    build_gif_cmds,
    export_final,
)
from app.services.editor.jianying_export import build_draft

pytestmark = pytest.mark.asyncio


# ---------- GIF / 音频命令 ----------

def test_build_gif_cmds_two_pass():
    cmds = build_gif_cmds("in.mp4", "out.gif", 480, 12)
    assert len(cmds) == 2
    assert "palettegen" in cmds[0][5]  # -vf 滤镜串
    assert cmds[0][-1].endswith("out.gif.palette.png")
    lavfi = next(c for c in cmds[1] if "paletteuse" in c)  # -lavfi 滤镜串
    assert cmds[1][-1] == "out.gif"
    assert "fps=12,scale=480:-1" in lavfi


def test_build_audio_cmd():
    cmd = build_audio_cmd("in.mp4", "out.m4a")
    assert "-vn" in cmd and "aac" in cmd and cmd[-1] == "out.m4a"


# ---------- export_final 服务 ----------

class _Project:
    def __init__(self, tmp: Path, *, status="succeeded", final_url="/uploads/editor/final.mp4"):
        self.uid = "u1"
        self.user_id = 1
        self.title = "测试工程"
        self.render_status = status
        self.final_url = final_url
        self.document = {"timebase": 30, "width": 1280, "height": 720, "tracks": [], "clips": []}
        self._tmp = tmp

    def staged(self) -> Path:
        return self._tmp / "editor" / "final.mp4"


@pytest.fixture()
def export_env(tmp_path, monkeypatch):
    """UPLOADS_DIR 收口到 tmp_path；probe/ffmpeg/记账全部打桩"""
    (tmp_path / "editor").mkdir()
    (tmp_path / "editor" / "final.mp4").write_bytes(b"fake")
    monkeypatch.setattr(export_service, "UPLOADS_DIR", str(tmp_path))

    import app.services.storage_quota as quota

    calls = {"record": []}

    async def fake_record(*, user_id, storage_key, source, kind=None, **kw):
        calls["record"].append((user_id, storage_key, kind))

    monkeypatch.setattr(quota, "record_file", fake_record)

    async def fake_probe(paths):
        return [5.0 for _ in paths]

    monkeypatch.setattr(export_service, "probe_durations", fake_probe)

    ff_calls: list[list[str]] = []

    async def fake_ffmpeg(cmd, timeout=0, error_label=""):
        ff_calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"x")  # 真实产物文件（os.replace 需要）

    monkeypatch.setattr(export_service, "run_ffmpeg", fake_ffmpeg)
    return {"ff_calls": ff_calls, "record": calls["record"], "tmp": tmp_path}


@pytest.mark.asyncio
async def test_export_gif_two_pass_and_palette_cleanup(export_env):
    project = _Project(export_env["tmp"])
    result = await export_final(project, "gif", 480, 12, db=None)
    assert result["format"] == "gif"
    assert result["url"].startswith("/uploads/editor/")
    assert len(export_env["ff_calls"]) == 2  # 调色板两遍
    palette = export_env["ff_calls"][0][-1]
    assert not Path(palette).exists()  # 调色板临时文件已清理


@pytest.mark.asyncio
async def test_export_audio_single_pass(export_env):
    project = _Project(export_env["tmp"])
    result = await export_final(project, "audio", db=None)
    assert result["format"] == "audio"
    assert result["url"].endswith(".m4a")
    assert len(export_env["ff_calls"]) == 1


@pytest.mark.asyncio
async def test_export_guards(export_env):
    project = _Project(export_env["tmp"], status="idle", final_url=None)
    with pytest.raises(Exception, match="先渲染"):
        await export_final(project, "gif", db=None)
    with pytest.raises(Exception, match="format"):
        await export_final(_Project(export_env["tmp"]), "mp3", db=None)


# ---------- 剪映草稿 build_draft 黄金测试 ----------

def _doc() -> dict:
    return {
        "timebase": 30,
        "width": 1280,
        "height": 720,
        "tracks": [
            {"id": "v_top", "kind": "video", "order": 1, "flags": {}},
            {"id": "v_main", "kind": "video", "order": 0, "flags": {}, "transitions": [
                {"id": "tr1", "afterClipId": "c1", "type": "fade", "duration": 0.5},
            ]},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {"muted": False}},
            {"id": "s1", "kind": "subtitle", "order": 0, "flags": {}},
        ],
        "clips": [
            {"id": "c1", "trackId": "v_main", "assetId": 1, "start": 0, "duration": 2, "trimStart": 0.5,
             "props": {"fadeIn": 0.5, "fadeOut": 0.5}},
            {"id": "c2", "trackId": "v_main", "assetId": 1, "start": 2, "duration": 2, "trimStart": 0, "props": {}},
            # PIP：上层轨带 rect（归一化 0~1）
            {"id": "c3", "trackId": "v_top", "assetId": 2, "start": 1, "duration": 1.5, "trimStart": 0,
             "props": {"rect": {"x": 0.5, "y": 0.5, "w": 0.25, "h": 0.25}}},
            {"id": "c4", "trackId": "v_top", "assetId": 3, "start": 2.5, "duration": 1, "trimStart": 0, "props": {}},
            {"id": "a_c1", "trackId": "a1", "assetId": 4, "start": 0, "duration": 3, "trimStart": 0,
             "props": {"volume": 0.8, "fadeIn": 0.2, "fadeOut": 0.3}},
            {"id": "s_c1", "trackId": "s1", "assetId": None, "start": 0.5, "duration": 1, "trimStart": 0,
             "props": {}, "text": "你好世界"},
        ],
        "subtitleStyle": {"font": "Noto Sans CJK SC", "size": 48, "color": "#FFEEDD", "outline": True,
                          "position": "bottom"},
    }


def _media() -> dict:
    return {
        1: {"path": "assets/1_a.mp4", "kind": "video", "width": 1920, "height": 1080,
            "duration_us": 6_000_000},
        2: {"path": "assets/2_b.mp4", "kind": "video", "width": 1280, "height": 720,
            "duration_us": 3_000_000},
        3: {"path": "assets/3_c.jpg", "kind": "image", "width": 800, "height": 600, "duration_us": 0},
        4: {"path": "assets/4_d.mp3", "kind": "audio", "width": 0, "height": 0, "duration_us": 5_000_000},
    }


def test_draft_microseconds_and_tracks():
    info, meta = build_draft(_doc(), "测试", _media(), now_ms=1_000)
    fps = 30

    def us(sec: float) -> int:
        return round(round(sec * fps) * 1_000_000 / fps)

    assert info["canvas_config"] == {"width": 1280, "height": 720, "ratio": "original"}
    assert info["fps"] == 30
    assert info["duration"] == us(4)  # c2 末端 2+2（c4 末端 3.5 更短）

    # 轨序：order 小的 video 轨在前（剪映主轨=底部），render_index 递增
    v_tracks = [t for t in info["tracks"] if t["type"] == "video"]
    assert [t["name"] for t in v_tracks] == ["v_main", "v_top"]
    assert [s["render_index"] for s in v_tracks[0]["segments"]] == [0, 0]
    assert v_tracks[1]["segments"][0]["render_index"] == 1

    # 微秒时间 + 源内跨度（trimStart=0.5 → 500000µs）
    seg_c1 = v_tracks[0]["segments"][0]
    assert seg_c1["target_timerange"] == {"start": 0, "duration": us(2)}
    assert seg_c1["source_timerange"] == {"start": us(0.5), "duration": us(2)}


def test_draft_pip_transform_and_audio_fade():
    info, _meta = build_draft(_doc(), "测试", _media(), now_ms=1_000)
    v_top = next(t for t in info["tracks"] if t["name"] == "v_top")
    seg_c3 = v_top["segments"][0]
    # PIP：display 宽 0.25×1280 / (src 1280×fit)，fit=min(1280/1280,720/720)=1 → scale 0.25
    assert abs(seg_c3["clip"]["scale"]["x"] - 0.25) < 1e-6
    # 中心 (0.625, 0.625)：x=2*(0.625-0.5)=0.25；y 向上取负=-0.25
    assert abs(seg_c3["clip"]["transform"]["x"] - 0.25) < 1e-6
    assert abs(seg_c3["clip"]["transform"]["y"] + 0.25) < 1e-6

    # 音频轨：音量/fade material 引用
    a_track = next(t for t in info["tracks"] if t["type"] == "audio")
    seg = a_track["segments"][0]
    assert seg["volume"] == 0.8
    fades = info["materials"]["audio_fades"]
    assert len(fades) == 1
    assert fades[0]["fade_in_duration"] == 200_000 and fades[0]["fade_out_duration"] == 300_000
    assert fades[0]["id"] in seg["extra_material_refs"]


def test_draft_transition_attached_to_previous_segment():
    info, _meta = build_draft(_doc(), "测试", _media(), now_ms=1_000)
    v_main = next(t for t in info["tracks"] if t["name"] == "v_main")
    prev, nxt = v_main["segments"]
    trans = info["materials"]["transitions"]
    assert len(trans) == 1 and trans[0]["name"] == "叠化"
    assert trans[0]["id"] in prev["extra_material_refs"]  # 挂前一片段
    assert trans[0]["id"] not in nxt["extra_material_refs"]


def test_draft_photo_material_and_library():
    info, meta = build_draft(_doc(), "测试", _media(), now_ms=1_000)
    photos = [v for v in info["materials"]["videos"] if v["type"] == "photo"]
    assert len(photos) == 1 and photos[0]["duration"] == 10_800_000_000  # 3 小时占位
    # 素材库（group 0）= 唯一素材数，local_material_id 关联
    lib = meta["draft_materials"][0]
    assert lib["type"] == 0
    assert len(lib["value"]) == 4
    video_mat = next(v for v in info["materials"]["videos"] if v["type"] == "video")
    lib_ids = {e["id"] for e in lib["value"]}
    assert video_mat["local_material_id"] in lib_ids


def test_draft_subtitle_track_and_task():
    info, _meta = build_draft(_doc(), "测试", _media(), now_ms=1_000)
    sub = next(t for t in info["tracks"] if t["flag"] == 1)
    assert sub["type"] == "text"
    texts = info["materials"]["texts"]
    assert len(texts) == 1
    assert texts[0]["recognize_text"] == "你好世界"
    task = info["config"]["subtitle_taskinfo"][0]
    assert task["language"] == "zh-CN"
    assert texts[0]["recognize_task_id"] == task["id"]
    content = json.loads(texts[0]["content"])
    assert content["text"] == "你好世界"
    # 字幕颜色 #FFEEDD → [1.0, 0.9333, 0.8667]
    assert content["styles"][0]["fill"]["content"]["solid"]["color"][1] == pytest.approx(238 / 255, abs=1e-3)


# ---------- 剪映 zip 全链 ----------

class _FakeResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeDB:
    def __init__(self, items):
        self._items = items

    async def scalars(self, _q):
        return _FakeResult(self._items)


@pytest.mark.asyncio
async def test_export_jianying_zip(tmp_path, monkeypatch):
    from app.models.asset import Asset
    from app.services.editor import jianying_export

    asset = Asset(id=1, user_id=1, kind="video", asset_url="/uploads/a.mp4", type="material", version=1)
    (tmp_path / "a.mp4").write_bytes(b"fake")

    async def fake_resolve(_asset, dest):
        return str(tmp_path / "a.mp4")

    monkeypatch.setattr(
        "app.services.editor.media_source.resolve_asset_local_file", fake_resolve,
    )
    async def fake_probe(path, kind, fps):
        return _probe_stub(kind)

    monkeypatch.setattr(jianying_export, "_probe_media", fake_probe)
    monkeypatch.setattr(jianying_export, "tempfile",
                        type("T", (), {"mkdtemp": staticmethod(lambda prefix="": str(tmp_path / "stage"))}))

    doc = _doc()
    project = type("P", (), {"uid": "u1", "user_id": 1, "title": "测试/工程:名", "document": doc})()
    zip_path, folder = await jianying_export.export_jianying_zip(_FakeDB([asset]), project)
    assert folder == "测试工程名"  # 非法字符剔除
    assert Path(zip_path).exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert f"{folder}/draft_info.json" in names
        assert f"{folder}/draft_meta_info.json" in names
        assert any(n.startswith(f"{folder}/assets/") for n in names)
        info = json.loads(zf.read(f"{folder}/draft_info.json"))
        assert info["platform"]["app_source"] == "lv"
        assert info["materials"]


def _probe_stub(kind: str) -> dict:
    if kind == "video":
        return {"kind": kind, "width": 1920, "height": 1080, "duration_us": 6_000_000}
    if kind == "image":
        return {"kind": kind, "width": 800, "height": 600, "duration_us": 0}
    return {"kind": kind, "width": 0, "height": 0, "duration_us": 5_000_000}

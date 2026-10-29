# =====================================================
# 3D 场景导演台 v2 测试：翻译器多机位/shot 编译 + 严格 schema 校验
# - scene_to_prompt_suffix：cameras[active]/stage.environment 读取、shot 按 cameraId
#   选机位并追加景别/运镜（枚举全覆盖）
# - POST /api/scenes：非法 scene_data 被严格模型拒绝（400）
# - POST /api/scenes/preview-prompt：携带 shot 的编译透出
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services.scene_service import (
    _CAMERA_MOVE_TERMS,
    _SHOT_SIZE_TERMS,
    scene_to_prompt_suffix,
)


def _scene_data() -> dict:
    """双机位 + 单主体的 v2 场景（A 激活俯视高位，B 近距平视）"""
    return {
        "stage": {"environment": {"type": "studio", "label": "工作室"}, "aspect_ratio": "16:9"},
        "subjects": [
            {"id": "sub-1", "label": "主角", "x": 0, "y": 0, "z": 0,
             "rotation": {"x": 0, "y": 0, "z": 0}, "pose": {"preset": "arms_crossed"}},
        ],
        "cameras": [
            {"id": "cam-a", "name": "A 机位", "position": {"x": 0, "y": 4, "z": 8},
             "target": {"x": 0, "y": 0, "z": 0}, "fov": 50, "active": True},
            {"id": "cam-b", "name": "B 机位", "position": {"x": 0, "y": 1.6, "z": 1.2},
             "target": {"x": 0, "y": 1, "z": 0}, "fov": 50, "active": False},
        ],
        "lights": [
            {"id": "l-1", "type": "directional", "x": 5, "y": 8, "z": 5, "intensity": 1.0,
             "direction": {"x": -0.47, "y": -0.75, "z": -0.47}},
        ],
        "props": [],
        "shots": [],
        "activeShotId": None,
    }


def _shot(camera_id: str = "cam-b", shot_size: str = "close_up", move: str = "push_in") -> dict:
    return {
        "id": "shot-1", "cameraId": camera_id, "duration": 4, "fps": 24,
        "shotSize": shot_size, "cameraMove": move,
        "keyframes": [], "prompt": "雨夜巷战", "coverUrl": None, "derivedTaskIds": [],
        "cameraPath": {
            "path": {"shape": "ring", "facePath": False,
                     "points": [{"x": 5, "y": 1.6, "z": 0}, {"x": 0, "y": 1.6, "z": 5}]},
            "sampleCount": 6,
        },
    }


def test_scene_level_uses_active_camera_and_stage_env():
    suffix, details = scene_to_prompt_suffix(_scene_data())
    # A 机位 y=4 俯视；环境来自 stage.environment
    assert "俯视视角" in suffix
    assert "工作室布光" in details["environment"]
    assert "逆光" not in details  # 灯光编译存在即可
    assert details["light"]


def test_shot_selects_camera_by_id_and_appends_terms():
    suffix, details = scene_to_prompt_suffix(_scene_data(), _shot())
    # B 机位 y=1.6 平视 + 距离≈1.2 → 特写 85mm
    assert "平视视角" in suffix
    assert "85mm" in suffix
    assert "特写" in suffix and "推镜" in suffix
    assert "雨夜巷战" in suffix
    assert details["shot_size"] == "特写"
    assert details["camera_move"] == "推镜"


def test_shot_without_prompt_still_compiles_terms():
    shot = _shot(camera_id="cam-a", shot_size="wide", move="orbit")
    shot["prompt"] = ""
    suffix, details = scene_to_prompt_suffix(_scene_data(), shot)
    assert "全景" in suffix and "环绕运镜" in suffix
    assert details["shot_size"] == "全景"


def test_all_enum_terms_covered():
    """景别 6 档 / 运镜 9 种全部有中文词条（枚举与编译表锁死）"""
    assert len(_SHOT_SIZE_TERMS) == 6
    assert len(_CAMERA_MOVE_TERMS) == 9
    for size in ["extreme_wide", "wide", "medium", "medium_close", "close_up", "extreme_close_up"]:
        shot = _shot(shot_size=size, move="static")
        _, details = scene_to_prompt_suffix(_scene_data(), shot)
        assert details["shot_size"], size
    for move in _CAMERA_MOVE_TERMS:
        shot = _shot(move=move)
        _, details = scene_to_prompt_suffix(_scene_data(), shot)
        assert details["camera_move"], move


def test_no_cameras_falls_back_to_defaults():
    data = _scene_data()
    data["cameras"] = []
    suffix, details = scene_to_prompt_suffix(data)
    assert suffix  # 空机位仍产出（中性默认：平视/中景）


# ---------- API 层 ----------

async def _build_client(memory_db, user):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username):
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_rejects_invalid_scene_data(memory_db):
    user = await _seed_user(memory_db, "scene_v2_owner")
    async for client in _build_client(memory_db, user):
        resp = await client.post("/api/scenes", json={
            "name": "坏场景",
            # 主体缺 id、shot 枚举非法 —— 严格模型应拒绝
            "scene_data": {
                "subjects": [{"label": "主角", "x": 0, "y": 0, "z": 0}],
                "shots": [{"id": "s", "cameraId": "c", "shotSize": "bad_size"}],
            },
        })
        assert resp.status_code == 400
        assert not resp.json().get("data")


@pytest.mark.asyncio
async def test_create_and_update_roundtrip_camel_case(memory_db):
    user = await _seed_user(memory_db, "scene_v2_roundtrip")
    async for client in _build_client(memory_db, user):
        data = _scene_data()
        data["shots"] = [_shot()]
        resp = await client.post("/api/scenes", json={"name": "v2 场景", "scene_data": data})
        assert resp.status_code == 200
        stored = resp.json()["data"]
        # 落库/响应保持 camelCase（前端形态）；主体姿势预设与运镜路径透传
        assert stored["scene_data"]["cameras"][0]["id"] == "cam-a"
        assert stored["scene_data"]["shots"][0]["cameraId"] == "cam-b"
        assert stored["scene_data"]["subjects"][0]["pose"]["preset"] == "arms_crossed"
        assert stored["scene_data"]["shots"][0]["cameraPath"]["path"]["shape"] == "ring"
        assert stored["scene_data"]["shots"][0]["cameraPath"]["sampleCount"] == 6

        data["shots"][0]["shotSize"] = "wide"
        upd = await client.put(f"/api/scenes/{stored['id']}", json={"scene_data": data})
        assert upd.status_code == 200
        assert upd.json()["data"]["scene_data"]["shots"][0]["shotSize"] == "wide"


@pytest.mark.asyncio
async def test_preview_prompt_with_shot(memory_db):
    user = await _seed_user(memory_db, "scene_v2_preview")
    async for client in _build_client(memory_db, user):
        resp = await client.post("/api/scenes/preview-prompt", json={
            "scene_data": _scene_data(),
            "shot": _shot(),
        })
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert "推镜" in payload["prompt_suffix"]
        assert payload["details"]["shot_size"] == "特写"

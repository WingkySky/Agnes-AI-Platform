# =====================================================
# 生图/生视频模型解析链单测（model_registry）
#
# 链路：显式指定 > 用户偏好 default_{type}_model_id > 该类型第一个
# 背景：对话生图/生视频此前直接取列表第一个，无视用户偏好，
#       造成"用户无感知用错模型"的费用偏差，本组测试锁死解析链。
#
# 依赖 fixture（见 conftest.py）：
#   - memory_db：内存 SQLite session
#   - seed_user：测试用户
# =====================================================

import pytest

from app.models.user_preference import UserPreference
from app.schemas.common import ModelInfo
from app.services import model_registry
from app.services.provider_registry import _detect_gen_params, provider_registry

_MODELS = [
    ModelInfo(id="agnes-video-2.5", name="Agnes Video 2.5", type="video"),
    ModelInfo(id="seedance-pro", name="Seedance Pro", type="video"),
    ModelInfo(id="agnes-image-2.1", name="Agnes Image 2.1", type="image"),
]


@pytest.fixture(autouse=True)
def _fake_registry(monkeypatch):
    """跳过真实 provider 注册表（读 .env / 数据库），用固定模型表测解析链"""

    async def _list_by_type(model_type: str):
        return [m for m in _MODELS if m.type == model_type]

    monkeypatch.setattr(provider_registry, "list_models_by_type", _list_by_type)


async def _set_video_pref(db, user_id: int, model_id: str):
    db.add(UserPreference(user_id=user_id, preferences={"generation": {"default_video_model_id": model_id}}))
    await db.commit()


@pytest.mark.asyncio
async def test_explicit_valid_model_wins(memory_db):
    model_id = await model_registry.resolve_user_media_model_id(memory_db, 0, "video", explicit="seedance-pro")
    assert model_id == "seedance-pro"


@pytest.mark.asyncio
async def test_user_preference_beats_first(memory_db, seed_user):
    await _set_video_pref(memory_db, seed_user.id, "seedance-pro")
    model_id = await model_registry.resolve_user_media_model_id(memory_db, seed_user.id, "video")
    assert model_id == "seedance-pro"


@pytest.mark.asyncio
async def test_stale_preference_falls_to_first(memory_db, seed_user):
    await _set_video_pref(memory_db, seed_user.id, "removed-model")
    model_id = await model_registry.resolve_user_media_model_id(memory_db, seed_user.id, "video")
    assert model_id == "agnes-video-2.5"


@pytest.mark.asyncio
async def test_no_user_uses_first(memory_db):
    model_id = await model_registry.resolve_user_media_model_id(memory_db, 0, "video")
    assert model_id == "agnes-video-2.5"


@pytest.mark.asyncio
async def test_no_user_and_explicit_invalid_falls_to_first(memory_db):
    model_id = await model_registry.resolve_user_media_model_id(memory_db, 0, "image", explicit="not-exist")
    assert model_id == "agnes-image-2.1"


# =====================================================
# 模型生成能力画像（_detect_gen_params）锁死
# 背景：Agnes Image 2.x 上游参考图上限 6 张（超出 HTTP 400 "too many input
# images: N provided, at most 6 allowed"），官方文档均未标注，靠画像预检拦截。
# =====================================================


def test_agnes_image_2x_ref_limit_is_six():
    assert _detect_gen_params("agnes-image-2.1-flash").max_ref_images == 6
    assert _detect_gen_params("agnes-image-2.5-flash").max_ref_images == 6


def test_gen_params_profile_returns_none_for_unknown_family():
    assert _detect_gen_params("some-other-image-model") is None

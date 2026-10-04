# =====================================================
# 模型倍率定价测试（credits_service 动态定价）
# 实扣 = credit_rules 基准价 × model_definitions.cost_multiplier；退款原额不受影响
# =====================================================

import pytest

from sqlalchemy import select

from app.models.api_provider import ApiProvider
from app.models.model_definition import ModelDefinition
from app.services.credits_service import get_image_cost_async, get_video_cost_async

pytestmark = pytest.mark.asyncio


async def _seed_model(db, model_id: str, multiplier: float, model_type: str = "image"):
    db.add(ApiProvider(name="p1", provider_type="agnes", base_url="https://x", is_active=True))
    await db.flush()
    provider_id = (await db.scalars(select(ApiProvider.id).limit(1))).first()
    db.add(ModelDefinition(provider_id=provider_id, model_id=model_id, type=model_type, cost_multiplier=multiplier))
    await db.commit()


async def test_image_cost_without_model_unchanged(memory_db):
    """不传 model：行为与旧版完全一致"""
    cost = await get_image_cost_async(memory_db, mode="text2image", size="1024x1024")
    assert cost == 10  # 默认基准 10 × 1MP(1.0) → 10


async def test_image_cost_multiplier_amplifies(memory_db):
    """倍率 1.5：实扣 = 基准 × 1.5（四舍五入）"""
    await _seed_model(memory_db, "agnes-image-2.1-flash", 1.5)
    cost = await get_image_cost_async(memory_db, mode="text2image", size="1024x1024", model="agnes-image-2.1-flash")
    assert cost == 15


async def test_video_cost_multiplier(memory_db):
    """视频：基准 5/秒 × 5s(1.0) × 33帧(1.0) × mode(1.0) = 10 下限；倍率 2.0 → 20"""
    await _seed_model(memory_db, "agnes-video-2.5", 2.0, model_type="video")
    cost = await get_video_cost_async(memory_db, mode="text2video", seconds=5, model="agnes-video-2.5")
    assert cost == 20


async def test_unknown_model_multiplier_defaults_to_one(memory_db):
    """模型不存在（已被删除）：按 1.0，不影响扣费"""
    cost = await get_image_cost_async(memory_db, mode="text2image", size="1024x1024", model="removed-model")
    assert cost == 10


async def test_multiplier_floor_enforced(memory_db):
    """异常低倍率（<0.1）按 0.1 兜底，防止 0 元刷生成"""
    await _seed_model(memory_db, "cheap-model", 0.0)
    cost = await get_image_cost_async(memory_db, mode="text2image", size="1024x1024", model="cheap-model")
    assert cost >= 5  # 图片下限 5

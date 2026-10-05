# =====================================================
# 生成结果统一入库测试（影子转正，子批次 2a）
# 独立/画布生成全量入库、work_id 标记、去重幂等、失败跳过
# =====================================================

import pytest
from sqlalchemy import select

from app.models.asset import Asset
from app.models.generation import Generation
from app.models.user import User
from app.services import asset_archive

pytestmark = pytest.mark.asyncio


async def _seed_user(memory_db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


def _generation(user_id: int, **kwargs) -> Generation:
    defaults = dict(
        type="image", user_id=user_id, prompt="一只猫", model="m", params={},
        result_url="/uploads/x/y.png", status="success", credits_consumed=0,
    )
    defaults.update(kwargs)
    return Generation(**defaults)


async def test_ingest_independent_generation(memory_db):
    """独立生成也入库：source=generation、/uploads/ 直推导 storage_key、无 work_id"""
    user = await _seed_user(memory_db, "u1")
    gen = _generation(user.id)
    memory_db.add(gen)
    await memory_db.commit()
    await memory_db.refresh(gen)

    asset = await asset_archive.ingest_generation_asset(memory_db, gen)
    assert asset is not None
    assert asset.source == "generation"
    assert asset.storage_key == "x/y.png"
    assert asset.work_id is None
    assert asset.kind == "image"
    assert asset.asset_url == "/uploads/x/y.png"
    assert asset.user_id == user.id


async def test_ingest_canvas_with_work_id(memory_db):
    """画布生成：context 携带 work_id → 资产打作品标记；container 仅作来源维度"""
    user = await _seed_user(memory_db, "u2")
    gen = _generation(user.id)
    memory_db.add(gen)
    await memory_db.commit()
    await memory_db.refresh(gen)

    asset = await asset_archive.ingest_generation_asset(
        memory_db, gen,
        {"source": "canvas", "container_type": "canvas", "container_id": "canvas", "work_id": 7},
    )
    assert asset is not None
    assert asset.work_id == 7
    assert asset.container_type == "canvas"
    assert asset.source == "generation"


async def test_ingest_dedup_and_failure_skip(memory_db):
    """去重：同一 generation 只建一行；失败/取消生成不入库；非法 work_id 忽略"""
    user = await _seed_user(memory_db, "u3")
    gen = _generation(user.id)
    memory_db.add(gen)
    await memory_db.commit()
    await memory_db.refresh(gen)

    first = await asset_archive.ingest_generation_asset(memory_db, gen, {"work_id": "abc"})
    assert first is not None
    assert first.work_id is None  # 非整数 work_id 忽略

    again = await asset_archive.ingest_generation_asset(memory_db, gen, {"work_id": 9})
    assert again is None  # 去重

    failed = _generation(user.id, status="failed")
    memory_db.add(failed)
    await memory_db.commit()
    await memory_db.refresh(failed)
    assert await asset_archive.ingest_generation_asset(memory_db, failed) is None


async def test_backfill_generations_to_assets(memory_db):
    """存量补课：历史成功生成批量入库（幂等；失败记录跳过；remaining 归零）"""
    from app.services.asset_library import backfill_generations_to_assets

    user = await _seed_user(memory_db, "u4")
    ok_gen = _generation(user.id, result_url="/uploads/legacy/a.png")
    ok_gen2 = _generation(user.id, result_url="/uploads/legacy/b.png")
    failed_gen = _generation(user.id, status="failed")
    memory_db.add_all([ok_gen, ok_gen2, failed_gen])
    await memory_db.commit()

    data = await backfill_generations_to_assets(memory_db, limit=100)
    assert data["created"] == 2  # 失败记录不入库

    assets = (await memory_db.scalars(select(Asset))).all()
    assert len(assets) == 2
    assert all(a.source == "generation" for a in assets)

    # 幂等：再跑一次不重复建行
    again = await backfill_generations_to_assets(memory_db, limit=100)
    assert again["created"] == 0
    assert again["remaining"] == 0


async def test_backfill_dead_link_processed(memory_db):
    """上游死链：转存失败时置空串标记已处理（防死循环），资产行仍保留"""
    from app.services.asset_library import backfill_asset_storage

    user = await _seed_user(memory_db, "u5")
    asset = Asset(
        type="material", name="死链素材", visual_description="", reference_images=[],
        user_id=user.id, is_public=False, tags=[], version=1,
        kind="image", asset_url="https://expired.example.com/x.png",
    )
    memory_db.add(asset)
    await memory_db.commit()
    await memory_db.refresh(asset)

    data = await backfill_asset_storage(memory_db, limit=10)
    assert data["remaining"] == 0
    await memory_db.refresh(asset)
    assert asset.storage_key == ""

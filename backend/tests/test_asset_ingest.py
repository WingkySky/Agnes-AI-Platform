# =====================================================
# 生成结果统一入库测试（影子转正，子批次 2a）
# 独立/画布生成全量入库、work_id 标记、去重幂等、失败跳过
# =====================================================

import pytest

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

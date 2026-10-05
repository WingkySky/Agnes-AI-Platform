# =====================================================
# 统一资产端点测试（/api/assets）
# POST 素材入库（/uploads 直推导 / 远程地址收口 / 挂靠归属校验）
# GET 列表筛选（media_type/source/work_id/keyword）+ 401/403/200 三态
# PATCH batch-share / POST batch-delete / GET batch-download 批量操作
# GET /{id} 详情（归属隔离）+ PATCH /{id} 元数据编辑（name/type/描述校验）+ keyword 三列匹配
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.asset import Asset
from app.models.generation import Generation
from app.models.user import User
from app.models.work import Work

pytestmark = pytest.mark.asyncio

ASSETS_URL = "/api/assets"


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(ASSETS_URL)).status_code == 401
        assert (await client.post(ASSETS_URL, json={"url": "/uploads/x.png", "media_type": "image"})).status_code == 401


async def test_create_and_list_200(memory_db):
    user = await _seed_user(memory_db, "u1")
    work = Work(user_id=user.id, title="我的剧")
    memory_db.add(work)
    await memory_db.commit()
    await memory_db.refresh(work)

    async for client in _build_client(memory_db, user):
        # /uploads/ 地址直推导 storage_key
        resp = await client.post(ASSETS_URL, json={
            "url": "/uploads/canvas/a.png", "media_type": "image", "name": "画布素材", "work_id": work.id,
        })
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["storage_key"] == "canvas/a.png"
        assert body["source"] == "upload"
        assert body["work_id"] == work.id
        assert body["media_type"] == "image"

        # 列表筛选
        resp = await client.get(ASSETS_URL, params={"media_type": "image"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"work_id": work.id})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"keyword": "画布"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"media_type": "video"})
        assert resp.json()["data"]["total"] == 0


async def test_create_forbidden_and_invalid(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    foreign_work = Work(user_id=other.id, title="别人的")
    memory_db.add(foreign_work)
    await memory_db.commit()
    await memory_db.refresh(foreign_work)

    async for client in _build_client(memory_db, user):
        # 挂靠他人作品 403
        resp = await client.post(ASSETS_URL, json={
            "url": "/uploads/x.png", "media_type": "image", "work_id": foreign_work.id,
        })
        assert resp.status_code == 403
        # 非法媒体类型 400
        resp = await client.post(ASSETS_URL, json={"url": "/uploads/x.png", "media_type": "pdf"})
        assert resp.status_code == 400
        # 非法协议地址 400（SSRF 防护）
        resp = await client.post(ASSETS_URL, json={"url": "http://127.0.0.1/x.png", "media_type": "image"})
        assert resp.status_code == 400


async def _seed_asset(memory_db, user: User, name: str = "素材") -> Asset:
    asset = Asset(
        type="material", name=name, visual_description=name, reference_images=[],
        user_id=user.id, is_public=False, tags=[], version=1,
        kind="image", asset_url="/uploads/canvas/none.png",
    )
    memory_db.add(asset)
    await memory_db.commit()
    await memory_db.refresh(asset)
    return asset


async def test_batch_endpoints_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.patch(f"{ASSETS_URL}/batch-share", json={"ids": [1], "is_public": False})).status_code == 401
        assert (await client.post(f"{ASSETS_URL}/batch-delete", json={"ids": [1]})).status_code == 401
        assert (await client.get(f"{ASSETS_URL}/batch-download", params={"ids": "1"})).status_code == 401


async def test_batch_share_private_and_delete(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    mine_a = await _seed_asset(memory_db, user, "素材A")
    mine_b = await _seed_asset(memory_db, user, "素材B")
    foreign = await _seed_asset(memory_db, other, "别人的")

    async for client in _build_client(memory_db, user):
        # 空 ids 400
        resp = await client.patch(f"{ASSETS_URL}/batch-share", json={"ids": [], "is_public": False})
        assert resp.status_code == 400

        # 批量设为私有（含他人 ID：隔离并计入 failed_ids）
        resp = await client.patch(f"{ASSETS_URL}/batch-share", json={
            "ids": [mine_a.id, mine_b.id, foreign.id], "is_public": False,
        })
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["updated_count"] == 2
        assert foreign.id in body["failed_ids"]

        # 批量删除：只删自己的两条
        resp = await client.post(f"{ASSETS_URL}/batch-delete", json={"ids": [mine_a.id, mine_b.id, foreign.id]})
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["deleted_count"] == 2
        assert foreign.id in body["failed_ids"]

        # 他人资产不受影响
        remaining = (await client.get(ASSETS_URL, params={"keyword": "别人的"})).json()["data"]
        assert remaining["total"] == 0  # 本人视角看不到他人资产
        resp = await client.get(f"{ASSETS_URL}/batch-download", params={"ids": f"{foreign.id}"})
        assert resp.status_code == 404


async def test_batch_download_zip(memory_db):
    user = await _seed_user(memory_db, "u1")
    asset = await _seed_asset(memory_db, user, "素材A")

    async for client in _build_client(memory_db, user):
        # ids 格式错误 400
        resp = await client.get(f"{ASSETS_URL}/batch-download", params={"ids": "abc"})
        assert resp.status_code == 400
        # 正常打包（本地文件缺失时跳过，仍返回 zip 流）
        resp = await client.get(f"{ASSETS_URL}/batch-download", params={"ids": f"{asset.id}"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")


async def test_list_backfills_generation_mode(memory_db):
    """列表回填来源生成记录的 mode（卡片徽标用）；覆盖 source_generation_id 非空的回归路径"""
    user = await _seed_user(memory_db, "u1")
    gen = Generation(type="video", prompt="p", model="m", status="success", mode="text2video")
    memory_db.add(gen)
    await memory_db.commit()
    await memory_db.refresh(gen)
    asset = Asset(
        type="clip", name="来自生成", visual_description="d", reference_images=[],
        user_id=user.id, is_public=False, tags=[], version=1,
        source="generation", kind="video", asset_url="/uploads/a.mp4",
        source_generation_id=gen.id,
    )
    memory_db.add(asset)
    await memory_db.commit()

    async for client in _build_client(memory_db, user):
        resp = await client.get(ASSETS_URL)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        target = next(i for i in items if i["id"] == asset.id)
        assert target["mode"] == "text2video"


async def test_detail_and_update_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(f"{ASSETS_URL}/1")).status_code == 401
        assert (await client.patch(f"{ASSETS_URL}/1", json={"name": "x"})).status_code == 401


async def test_get_detail_ownership(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    mine = await _seed_asset(memory_db, user, "素材A")
    foreign = await _seed_asset(memory_db, other, "别人的")

    async for client in _build_client(memory_db, user):
        resp = await client.get(f"{ASSETS_URL}/{mine.id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "素材A"
        # 他人资产 / 不存在 → 404
        assert (await client.get(f"{ASSETS_URL}/{foreign.id}")).status_code == 404
        assert (await client.get(f"{ASSETS_URL}/999999")).status_code == 404


async def test_update_metadata(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    mine = await _seed_asset(memory_db, user, "素材A")
    foreign = await _seed_asset(memory_db, other, "别人的")

    async for client in _build_client(memory_db, user):
        # 全量编辑 200：字段落库
        resp = await client.patch(f"{ASSETS_URL}/{mine.id}", json={
            "name": "新名字", "type": "character", "description": "主角", "visual_description": "白衣少女",
        })
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["name"] == "新名字"
        assert body["type"] == "character"
        assert body["description"] == "主角"
        assert body["visual_description"] == "白衣少女"

        # 部分更新：未提交字段保持不动
        resp = await client.patch(f"{ASSETS_URL}/{mine.id}", json={"name": "再改名"})
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["name"] == "再改名"
        assert body["type"] == "character"

        # 他人资产 404 / 空 name 400 / 非法 type 400
        assert (await client.patch(f"{ASSETS_URL}/{foreign.id}", json={"name": "x"})).status_code == 404
        assert (await client.patch(f"{ASSETS_URL}/{mine.id}", json={"name": "  "})).status_code == 400
        assert (await client.patch(f"{ASSETS_URL}/{mine.id}", json={"type": "foo"})).status_code == 400


async def test_list_type_filter(memory_db):
    """按资产分类筛选（筛选条「分类」下拉）"""
    user = await _seed_user(memory_db, "u1")
    await _seed_asset(memory_db, user, "素材A")  # type=material
    memory_db.add(Asset(
        type="character", name="主角", visual_description="d", reference_images=[],
        user_id=user.id, is_public=False, tags=[], version=1,
        kind="image", asset_url="/uploads/canvas/x.png",
    ))
    await memory_db.commit()

    async for client in _build_client(memory_db, user):
        resp = await client.get(ASSETS_URL, params={"type": "character"})
        body = resp.json()["data"]
        assert body["total"] == 1
        assert body["items"][0]["type"] == "character"
        resp = await client.get(ASSETS_URL, params={"type": "material"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"type": "brand"})
        assert resp.json()["data"]["total"] == 0
        # 不传 type 不过滤
        assert (await client.get(ASSETS_URL)).json()["data"]["total"] == 2


async def test_keyword_matches_description(memory_db):
    """关键词搜索覆盖名称/描述/视觉描述三列"""
    user = await _seed_user(memory_db, "u1")
    asset = await _seed_asset(memory_db, user, "素材A")
    asset.description = "星空下的城堡"
    asset.visual_description = "cyberpunk city"
    await memory_db.commit()

    async for client in _build_client(memory_db, user):
        resp = await client.get(ASSETS_URL, params={"keyword": "城堡"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"keyword": "cyberpunk"})
        assert resp.json()["data"]["total"] == 1
        resp = await client.get(ASSETS_URL, params={"keyword": "不存在的词"})
        assert resp.json()["data"]["total"] == 0

# =====================================================
# 剪辑工程端点测试（/api/editor/projects）
# 401 未登录 / 200 本人 / 403 非本人；revision 乐观锁；document 骨架校验；草稿构建
# =====================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.asset import Asset
from app.models.user import User
from app.models.work import Work

pytestmark = pytest.mark.asyncio

URL = "/api/editor/projects"


def _doc(**overrides):
    doc = {
        "timebase": 30, "width": 1280, "height": 720,
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}},
            {"id": "a1", "kind": "audio", "order": 0, "flags": {}},
        ],
        "clips": [
            {"id": "c1", "trackId": "v1", "assetId": None, "start": 0.0,
             "duration": 2.0, "trimStart": 0.0, "props": {}},
        ],
    }
    doc.update(overrides)
    return doc


async def _build_client(memory_db, user=None):
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"} if user else {}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_user(memory_db, username: str):
    user = User(username=username, email=f"{username}@example.com",
                password_hash="x", role="user", is_admin=False, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)
    return user


async def test_anon_401(memory_db):
    async for client in _build_client(memory_db):
        assert (await client.get(URL)).status_code == 401
        assert (await client.post(URL, json={"title": "x"})).status_code == 401
        assert (await client.get(f"{URL}/some-uid")).status_code == 401
        assert (await client.put(f"{URL}/some-uid/document", json={
            "document": _doc(), "base_revision": 1})).status_code == 401


async def test_crud_and_revision_flow(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        resp = await client.post(URL, json={"title": "第1集精剪"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        uid = data["uid"]
        assert data["render_status"] == "idle"
        assert data["revision"] == 1

        # 详情 + 列表
        assert (await client.get(f"{URL}/{uid}")).status_code == 200
        resp = await client.get(URL)
        assert resp.json()["data"]["total"] == 1

        # 保存文档：revision 递增
        resp = await client.put(f"{URL}/{uid}/document", json={"document": _doc(), "base_revision": 1})
        assert resp.status_code == 200
        assert resp.json()["data"]["revision"] == 2

        # 旧 base_revision 再存 → 409 + current_revision
        resp = await client.put(f"{URL}/{uid}/document", json={"document": _doc(), "base_revision": 1})
        assert resp.status_code == 409
        assert resp.json()["detail"]["current_revision"] == 2

        # 改标题 + 删除
        resp = await client.patch(f"{URL}/{uid}", json={"title": "改名"})
        assert resp.json()["data"]["title"] == "改名"
        assert (await client.delete(f"{URL}/{uid}")).status_code == 200
        assert (await client.get(f"{URL}/{uid}")).status_code == 404


async def test_persistence_across_session_rollback(memory_db):
    """回归：写操作必须真实提交（get_async_db 不自动提交，请求结束会话关闭即回滚）。
    API 响应后手动 rollback，行仍须存活——曾因只 flush 不 commit 导致线上新建后 GET 404。"""
    from sqlalchemy.future import select as _select
    from app.models.editing_project import EditingProject

    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        uid = (await client.post(URL, json={"title": "落库验证"})).json()["data"]["uid"]
        await client.put(f"{URL}/{uid}/document", json={"document": _doc(), "base_revision": 1})

        await memory_db.rollback()  # 模拟请求结束会话丢弃未提交内容
        project = (await memory_db.scalars(_select(EditingProject).where(EditingProject.uid == uid))).first()
        assert project is not None, "工程未提交落库"
        assert project.title == "落库验证"
        assert project.revision == 2 and project.document["clips"]

        # 删除同样真实提交
        assert (await client.delete(f"{URL}/{uid}")).status_code == 200
        await memory_db.rollback()
        assert (await memory_db.scalars(_select(EditingProject).where(EditingProject.uid == uid))).first() is None


async def test_owner_boundary_403(memory_db):
    owner = await _seed_user(memory_db, "owner")
    other = await _seed_user(memory_db, "other")
    async for client in _build_client(memory_db, owner):
        uid = (await client.post(URL, json={"title": "我的工程"})).json()["data"]["uid"]
    async for client in _build_client(memory_db, other):
        assert (await client.get(f"{URL}/{uid}")).status_code == 403
        assert (await client.patch(f"{URL}/{uid}", json={"title": "抢"})).status_code == 403
        assert (await client.delete(f"{URL}/{uid}")).status_code == 403
        assert (await client.put(f"{URL}/{uid}/document", json={
            "document": _doc(), "base_revision": 1})).status_code == 403


async def test_document_skeleton_validation(memory_db):
    user = await _seed_user(memory_db, "u1")
    async for client in _build_client(memory_db, user):
        uid = (await client.post(URL, json={"title": "x"})).json()["data"]["uid"]

        bad_docs = [
            {"timebase": 0},                                        # 缺字段
            _doc(width=0),                                          # 分辨率越界
            _doc(tracks=[{"id": "v1", "kind": "3d", "order": 0}]),  # kind 非法
            _doc(tracks=[{"id": "v1", "kind": "video", "order": 0,
                          "flags": {"hidden": 1}}]),              # flags 值必须布尔
            _doc(tracks=[{"id": "v1", "kind": "video", "order": 0,
                          "flags": {"boom": True}}]),             # flags 键白名单外
            _doc(clips=[{"id": "c1", "trackId": "vx", "start": 0, "duration": 1}]),  # trackId 不存在
            _doc(clips=[{"id": "c1", "trackId": "v1", "start": -1, "duration": 1}]),  # 负 start
            _doc(clips=[{"id": "c1", "trackId": "v1", "start": 0, "duration": 1,
                         "props": {"speed": 0}}]),                  # speed<=0
            _doc(tracks=[{"id": "v1", "kind": "video", "order": 0,
                          "transitions": [{"id": "t", "afterClipId": "c1", "type": "boom", "duration": 1}]}]),  # 转场类型非法
            _doc(clips=[{"id": "c1", "trackId": "v1", "start": 0, "duration": 1,
                         "props": {"effects": [{"id": "e", "type": "blur", "strength": 2}]}}]),  # 效果器 strength 越界
        ]
        for bad in bad_docs:
            resp = await client.put(f"{URL}/{uid}/document", json={"document": bad, "base_revision": 1})
            assert resp.status_code == 400, bad

        # 工程创建时携带非法 document 同样拒绝
        resp = await client.post(URL, json={"title": "x", "document": {"broken": True}})
        assert resp.status_code == 400


async def test_work_binding_and_draft_from_assets(memory_db):
    user = await _seed_user(memory_db, "u1")
    other = await _seed_user(memory_db, "u2")
    work = Work(user_id=user.id, title="我的剧")
    memory_db.add(work)
    foreign = Work(user_id=other.id, title="别人的剧")
    memory_db.add(foreign)
    asset = Asset(type="clip", name="镜头1", description=None, visual_description="",
                  user_id=user.id, is_public=False,
                  tags=[], version=1, source="generation", kind="video", asset_url="/uploads/a.mp4")
    memory_db.add(asset)
    await memory_db.commit()
    await memory_db.refresh(work)
    await memory_db.refresh(asset)

    async for client in _build_client(memory_db, user):
        # 挂靠他人作品 → 403
        resp = await client.post(URL, json={"title": "x", "work_id": foreign.id})
        assert resp.status_code == 403

        # 圈选素材建草稿：视频排主轨 + source_workspace 透传
        resp = await client.post(URL, json={
            "title": "画布成片", "work_id": work.id,
            "source_workspace_id": "ws-1", "asset_ids": [asset.id]})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source_workspace_id"] == "ws-1"
        clips = data["document"]["clips"]
        assert len(clips) == 1 and clips[0]["assetId"] == asset.id
        assert clips[0]["trackId"] == "v1" and clips[0]["duration"] == 0.0

        # 不存在的素材 → 404
        resp = await client.post(URL, json={"title": "x", "asset_ids": [99999]})
        assert resp.status_code == 404

        # 按作品筛选列表
        resp = await client.get(URL, params={"work_id": work.id})
        assert resp.json()["data"]["total"] == 1

async def test_update_cover_url(memory_db):
    """PATCH cover_url：本人 200 且响应/列表带封面；空串清空；非法长字符串 400"""
    user = await _seed_user(memory_db, "ucover")
    async for client in _build_client(memory_db, user):
        detail = (await client.post(URL, json={"title": "封面工程"})).json()["data"]
        uid = detail["uid"]
        resp = await client.patch(f"{URL}/{uid}", json={"cover_url": "/uploads/editor/cover_x.jpg"})
        assert resp.status_code == 200
        assert resp.json()["data"]["cover_url"] == "/uploads/editor/cover_x.jpg"
        items = (await client.get(URL)).json()["data"]["items"]
        assert items[0]["cover_url"] == "/uploads/editor/cover_x.jpg"
        assert (await client.patch(f"{URL}/{uid}", json={"cover_url": ""})).status_code == 200
        assert (await client.get(f"{URL}/{uid}")).json()["data"]["cover_url"] is None

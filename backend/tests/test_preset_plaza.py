# =====================================================
# 统一预设广场接口测试
# 覆盖：广场可见性 / pipeline 排除 / 类型与搜索过滤 /
#       收藏 toggle / 最近使用记录 / hot 官方优先 / Fork 重置
# =====================================================

import pytest

from app.models.prompt_preset import PromptPreset


async def _make_preset(db, user_id=None, name="测试预设", type="style",
                       is_public=False, is_approved=False, **kwargs) -> PromptPreset:
    preset = PromptPreset(
        user_id=user_id, name=name, type=type,
        is_public=is_public, is_approved=is_approved, **kwargs,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


@pytest.mark.asyncio
async def test_plaza_list_visibility(auth_client, db, seed_user):
    """plaza tab：自己的可见、他人私有不可见、公开已审核可见"""
    await _make_preset(db, user_id=seed_user.id, name="我的私有风格")
    await _make_preset(db, user_id=999, name="他人私有风格")
    await _make_preset(db, user_id=999, name="他人公开风格", is_public=True, is_approved=True)

    resp = await auth_client.get("/api/presets")
    assert resp.status_code == 200
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert "我的私有风格" in names
    assert "他人私有风格" not in names
    assert "他人公开风格" in names


@pytest.mark.asyncio
async def test_plaza_excludes_pipeline(auth_client, db, seed_user):
    """pipeline 类型不进广场"""
    await _make_preset(db, user_id=seed_user.id, name="流水线配置", type="pipeline")
    resp = await auth_client.get("/api/presets")
    assert all(i["type"] != "pipeline" for i in resp.json()["data"]["items"])


@pytest.mark.asyncio
async def test_type_filter_and_search(auth_client, db, seed_user):
    """type 多类型过滤 + q 搜索名称"""
    await _make_preset(db, user_id=seed_user.id, name="水墨风格", type="style")
    await _make_preset(db, user_id=seed_user.id, name="穿云而入", type="effect")

    resp = await auth_client.get("/api/presets", params={"type": "effect"})
    assert {i["name"] for i in resp.json()["data"]["items"]} == {"穿云而入"}

    resp = await auth_client.get("/api/presets", params={"type": "style,effect"})
    assert len(resp.json()["data"]["items"]) == 2

    resp = await auth_client.get("/api/presets", params={"q": "水墨"})
    assert {i["name"] for i in resp.json()["data"]["items"]} == {"水墨风格"}


@pytest.mark.asyncio
async def test_favorite_toggle_and_favorites_tab(auth_client, db, seed_user):
    """收藏 toggle 幂等互斥，favorites tab 联表正确"""
    preset = await _make_preset(db, user_id=999, name="可收藏风格", is_public=True, is_approved=True)

    resp = await auth_client.post(f"/api/presets/{preset.id}/favorite")
    assert resp.json()["data"] == {"is_favorite": True}
    resp = await auth_client.post(f"/api/presets/{preset.id}/favorite")
    assert resp.json()["data"] == {"is_favorite": False}

    await auth_client.post(f"/api/presets/{preset.id}/favorite")
    resp = await auth_client.get("/api/presets", params={"tab": "favorites"})
    items = resp.json()["data"]["items"]
    assert [i["name"] for i in items] == ["可收藏风格"]
    assert items[0]["is_favorite"] is True

    # 取消收藏后 favorites tab 为空
    await auth_client.post(f"/api/presets/{preset.id}/favorite")
    resp = await auth_client.get("/api/presets", params={"tab": "favorites"})
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_use_records_recent_and_usage(auth_client, db, seed_user):
    """use 记录 upsert：recent tab 可见，usage_count 累加"""
    preset = await _make_preset(db, user_id=seed_user.id, name="常用风格")

    await auth_client.post(f"/api/presets/{preset.id}/use")
    await auth_client.post(f"/api/presets/{preset.id}/use")

    resp = await auth_client.get("/api/presets", params={"tab": "recent"})
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "常用风格"

    await db.refresh(preset)
    assert preset.usage_count == 2


@pytest.mark.asyncio
async def test_hot_sort_official_first(auth_client, db, seed_user):
    """hot 排序官方卡优先，其次按使用量"""
    await _make_preset(db, user_id=None, name="官方热门", is_public=True, is_approved=True,
                       is_official=True, usage_count=10)
    await _make_preset(db, user_id=999, name="普通热门", is_public=True, is_approved=True,
                       usage_count=100)
    resp = await auth_client.get("/api/presets", params={"sort": "hot"})
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert names.index("官方热门") < names.index("普通热门")


@pytest.mark.asyncio
async def test_fork_resets_flags(auth_client, db, seed_user):
    """Fork：私有副本、去官方标记、热度清零、prompt_config 保留"""
    src = await _make_preset(db, user_id=999, name="官方风格", type="style",
                             is_public=True, is_approved=True, is_official=True,
                             usage_count=42, prompt_config={"suffix": "，电影感"})

    resp = await auth_client.post(f"/api/presets/{src.id}/fork")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_official"] is False
    assert data["is_public"] is False
    assert data["usage_count"] == 0
    assert data["prompt_config"] == {"suffix": "，电影感"}


@pytest.mark.asyncio
async def test_generate_cover_admin_only(auth_client, db, seed_user, monkeypatch):
    """封面生成：普通用户 403，管理员成功写回 cover_image"""
    from app.core.security import create_access_token
    from app.models.user import User
    from app.services import preset_cover_service

    preset = await _make_preset(db, user_id=None, name="官方卡", is_public=True,
                                is_approved=True, is_official=True)

    # 普通用户被拒
    resp = await auth_client.post(f"/api/presets/{preset.id}/generate-cover")
    assert resp.status_code == 403

    # 切换为管理员身份
    admin = User(username="adminx", email="adminx@example.com", password_hash="x",
                 role="admin", is_admin=True)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    auth_client.headers["Authorization"] = f"Bearer {create_access_token(admin.id)}"

    # mock 掉真实生图调用
    async def _fake_generate(p):
        return "/uploads/preset-covers/fake.png"

    monkeypatch.setattr(preset_cover_service, "generate_cover_image", _fake_generate)
    resp = await auth_client.post(f"/api/presets/{preset.id}/generate-cover")
    assert resp.status_code == 200
    assert resp.json()["data"]["cover_image"] == "/uploads/preset-covers/fake.png"

    await db.refresh(preset)
    assert preset.cover_image == "/uploads/preset-covers/fake.png"

    # effect 类型走动态封面分支（视频封面）
    effect = await _make_preset(db, user_id=None, name="穿云而入", type="effect",
                                is_public=True, is_approved=True, is_official=True)

    async def _fake_video(p):
        return "/uploads/preset-videos/fake.mp4"

    monkeypatch.setattr(preset_cover_service, "generate_cover_video", _fake_video)
    resp = await auth_client.post(f"/api/presets/{effect.id}/generate-cover")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"cover_video": "/uploads/preset-videos/fake.mp4"}

    await db.refresh(effect)
    assert effect.cover_video == "/uploads/preset-videos/fake.mp4"

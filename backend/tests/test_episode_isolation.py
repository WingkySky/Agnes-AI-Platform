# =====================================================
# 集数隔离后端测试
#
# 功能模块：
#   1. 创建校验：四类资源创建时必须传 script_id，且 script_id 必须属于项目
#   2. 按集过滤：list 接口 ?script_id=N 只返回该集资源
#   3. 不传 script_id：list 接口返回全部集资源
#   4. 序号按集重置：分镜 sequence_no 按集独立从 1 开始
#   5. 跨集复制：copy-to 接口深拷贝到目标集，名称冲突加（副本）后缀
#   6. 级联删除：删除剧本后该集下资源被 CASCADE 删除
#   7. Response 带 episode_no：列表响应包含 episode_no 字段
#
# 依赖 fixture（见 conftest.py）：
#   - memory_db / db：内存 SQLite + foreign_keys pragma
#   - seed_user：测试用户
#   - auth_client：带 JWT 的 httpx AsyncClient，覆盖 get_async_db
# =====================================================

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectCharacter,
    ProjectScript,
    ProjectShot,
)
from app.models.user import User


# =====================================================
# 共享 fixture：项目含两集剧本
# =====================================================

@pytest_asyncio.fixture
async def project_with_two_episodes(db: AsyncSession, seed_user: User):
    """创建一个项目，含第一集和第二集两个剧本"""
    project = Project(
        title="集数隔离测试项目",
        user_id=seed_user.id,
        status="in_progress",
    )
    db.add(project)
    await db.flush()  # 拿到 project.id

    s1 = ProjectScript(
        project_id=project.id,
        episode_no=1,
        title="第一集",
        content="第一集剧本内容",
    )
    s2 = ProjectScript(
        project_id=project.id,
        episode_no=2,
        title="第二集",
        content="第二集剧本内容",
    )
    db.add_all([s1, s2])
    await db.commit()
    await db.refresh(project)
    await db.refresh(s1)
    await db.refresh(s2)
    return project, s1, s2


# =====================================================
# 1. 创建校验：script_id 必填
# =====================================================

@pytest.mark.asyncio
async def test_create_character_requires_script_id(auth_client: AsyncClient, project_with_two_episodes):
    """不传 script_id 创建角色返回 400（项目自定义校验异常处理器返回 400 而非 422）"""
    project, _, _ = project_with_two_episodes
    resp = await auth_client.post(
        f"/api/projects/{project.id}/characters",
        json={"name": "角色A"},
    )
    assert resp.status_code == 400


# =====================================================
# 2. 创建校验：script_id 必须属于项目
# =====================================================

@pytest.mark.asyncio
async def test_create_character_with_script_id(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """传 script_id 创建角色成功，且归属正确"""
    project, _, s2 = project_with_two_episodes
    resp = await auth_client.post(
        f"/api/projects/{project.id}/characters",
        json={"script_id": s2.id, "name": "角色B"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["script_id"] == s2.id
    # 数据库验证归属
    char = await db.get(ProjectCharacter, data["id"])
    assert char is not None
    assert char.script_id == s2.id


@pytest.mark.asyncio
async def test_create_character_invalid_script_id_returns_404(
    auth_client: AsyncClient, project_with_two_episodes
):
    """script_id 不属于项目时返回 404"""
    project, _, _ = project_with_two_episodes
    resp = await auth_client.post(
        f"/api/projects/{project.id}/characters",
        json={"script_id": 999999, "name": "角色X"},
    )
    assert resp.status_code == 404


# =====================================================
# 3. 按集过滤：?script_id=N 只返回该集资源
# =====================================================

@pytest.mark.asyncio
async def test_list_characters_filter_by_script_id(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """?script_id=N 只返回该集角色"""
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(
            project_id=project.id, script_id=s1.id, name="角色1", sort_order=1,
        ),
        ProjectCharacter(
            project_id=project.id, script_id=s2.id, name="角色2", sort_order=1,
        ),
    ])
    await db.commit()

    resp = await auth_client.get(
        f"/api/projects/{project.id}/characters?script_id={s2.id}"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "角色2"
    assert data[0]["script_id"] == s2.id


# =====================================================
# 4. 不传 script_id：list 接口返回全部集资源
# =====================================================

@pytest.mark.asyncio
async def test_list_characters_without_script_id_returns_all(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """不传 script_id 返回全部集角色"""
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(
            project_id=project.id, script_id=s1.id, name="角色1", sort_order=1,
        ),
        ProjectCharacter(
            project_id=project.id, script_id=s2.id, name="角色2", sort_order=1,
        ),
    ])
    await db.commit()

    resp = await auth_client.get(f"/api/projects/{project.id}/characters")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2


# =====================================================
# 5. 分镜序号按集重置（按集独立从 1 开始递增）
# =====================================================

@pytest.mark.asyncio
async def test_shot_sequence_no_resets_per_script(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """分镜序号按集重置——第二集分镜序号从 1 开始"""
    project, s1, s2 = project_with_two_episodes
    # 第一集两个分镜（sequence_no 1, 2）
    db.add_all([
        ProjectShot(
            project_id=project.id, script_id=s1.id,
            sequence_no=1, sort_order=1,
        ),
        ProjectShot(
            project_id=project.id, script_id=s1.id,
            sequence_no=2, sort_order=2,
        ),
    ])
    await db.commit()

    # 第二集创建分镜，不传 sequence_no，应由 service 自动计算为 1
    resp = await auth_client.post(
        f"/api/projects/{project.id}/shots",
        json={"script_id": s2.id},
    )
    assert resp.status_code == 200, resp.text
    shot = resp.json()
    assert shot["sequence_no"] == 1
    assert shot["script_id"] == s2.id


# =====================================================
# 6. split 接口校验：不存在的 script_id 返回 404
# =====================================================

@pytest.mark.asyncio
async def test_split_shots_invalid_script_id_returns_404(
    auth_client: AsyncClient, project_with_two_episodes
):
    """不存在的 script_id 返回 404"""
    project, _, _ = project_with_two_episodes
    resp = await auth_client.post(
        f"/api/projects/{project.id}/shots/split",
        json={"script_id": 999999},
    )
    assert resp.status_code == 404


# =====================================================
# 7. 跨集复制：copy-to 深拷贝到目标集
# =====================================================

@pytest.mark.asyncio
async def test_copy_character_to_other_episode(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """跨集复制角色——目标集出现新记录，名称/外观一致，id 不同"""
    project, s1, s2 = project_with_two_episodes
    src = ProjectCharacter(
        project_id=project.id,
        script_id=s1.id,
        name="主角",
        description="描述",
        appearance_desc="外观",
        sort_order=1,
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    resp = await auth_client.post(
        f"/api/projects/{project.id}/characters/{src.id}/copy-to",
        json={"target_script_id": s2.id},
    )
    assert resp.status_code == 200, resp.text
    new_char = resp.json()
    assert new_char["script_id"] == s2.id
    assert new_char["name"] == "主角"
    assert new_char["id"] != src.id


# =====================================================
# 8. 跨集复制：名称冲突加（副本）后缀
# =====================================================

@pytest.mark.asyncio
async def test_copy_character_name_conflict_adds_suffix(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """目标集已有同名时加（副本）后缀"""
    project, s1, s2 = project_with_two_episodes
    src = ProjectCharacter(
        project_id=project.id, script_id=s1.id, name="主角", sort_order=1,
    )
    dst = ProjectCharacter(
        project_id=project.id, script_id=s2.id, name="主角", sort_order=1,
    )
    db.add_all([src, dst])
    await db.commit()
    await db.refresh(src)

    resp = await auth_client.post(
        f"/api/projects/{project.id}/characters/{src.id}/copy-to",
        json={"target_script_id": s2.id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "主角（副本）"


# =====================================================
# 9. 级联删除：删除某集剧本后该集角色被 CASCADE 删除
# =====================================================

@pytest.mark.asyncio
async def test_delete_script_cascades_characters(
    db: AsyncSession, project_with_two_episodes
):
    """删除第一集剧本后该集角色级联删除，第二集角色保留

    使用 SQL DELETE（而非 ORM db.delete）触发数据库层的 ON DELETE CASCADE，
    避免 SQLAlchemy ORM 级 cascade 在 async 环境下加载 relationship 报 MissingGreenlet。
    """
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(
            project_id=project.id, script_id=s1.id, name="角色1", sort_order=1,
        ),
        ProjectCharacter(
            project_id=project.id, script_id=s2.id, name="角色2", sort_order=1,
        ),
    ])
    await db.commit()

    # 用 SQL DELETE 删除第一集剧本，由数据库 ON DELETE CASCADE 级联删除该集角色
    await db.execute(delete(ProjectScript).where(ProjectScript.id == s1.id))
    await db.commit()

    # 在 expire_all 前先保存 id 到本地变量（expire_all 后访问 ORM 对象属性会触发 lazy load）
    project_id = project.id
    s2_id = s2.id

    # 清掉 session 缓存，确保后续查询从数据库重新加载
    db.expire_all()

    # 第一集角色应被级联删除，第二集角色保留
    remaining = (
        await db.execute(
            select(ProjectCharacter).where(
                ProjectCharacter.project_id == project_id
            )
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].script_id == s2_id


# =====================================================
# 10. Response 带 episode_no 字段
# =====================================================

@pytest.mark.asyncio
async def test_response_includes_episode_no(
    auth_client: AsyncClient, db: AsyncSession, project_with_two_episodes
):
    """列表 Response 带 episode_no 字段（来自 join ProjectScript）"""
    project, s1, _ = project_with_two_episodes
    db.add(
        ProjectCharacter(
            project_id=project.id, script_id=s1.id, name="角色", sort_order=1,
        )
    )
    await db.commit()

    resp = await auth_client.get(f"/api/projects/{project.id}/characters")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["episode_no"] == 1

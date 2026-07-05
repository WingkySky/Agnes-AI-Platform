# =====================================================
# conftest fixture sanity check
# 验证 memory_db / seed_user / seed_template / seed_run_with_steps 正常工作
# =====================================================

import pytest
from sqlalchemy import select

from app.models.pipeline import PipelineRun, PipelineStep, PipelineTemplate
from app.models.user import User


@pytest.mark.asyncio
async def test_memory_db_creates_tables(memory_db):
    """内存数据库应能查到所有已建表"""
    result = await memory_db.execute(select(PipelineRun))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_seed_user_created(seed_user):
    """seed_user 应正确插入并返回主键"""
    assert seed_user.id is not None
    assert seed_user.username == "tester"


@pytest.mark.asyncio
async def test_seed_template_created(seed_template):
    """seed_template 应正确插入并返回主键"""
    assert seed_template.id is not None
    assert seed_template.key == "test_tpl"
    assert len(seed_template.steps_config) == 3


@pytest.mark.asyncio
async def test_seed_run_with_steps_created(seed_run_with_steps):
    """seed_run_with_steps 应返回 run + 3 个步骤"""
    run = seed_run_with_steps["run"]
    steps = seed_run_with_steps["steps"]
    assert run.id is not None
    assert len(steps) == 3
    # 验证依赖链 A→B→C
    assert steps[0].step_key == "step_a"
    assert steps[1].depends_on == ["step_a"]
    assert steps[2].depends_on == ["step_b"]

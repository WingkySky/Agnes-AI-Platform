# =====================================================
# 剧本服务 — 剧本 CRUD + 重新生成
#
# 剧本是项目创作的源头，向导 4 步链路第 1 步产物。
# 用户可在向导完成后随时编辑/重生成剧本。
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectScript
from app.schemas.project import ScriptCreate, ScriptUpdate
from app.services.agnes_client import agnes_client
from app.services.model_registry import resolve_project_chat_model_id
from app.services.model_registry import resolve_user_chat_model_id

logger = logging.getLogger("agnes_platform.project.script")


# =====================================================
# 剧本 CRUD
# =====================================================

async def list_scripts(db: AsyncSession, project_id: int) -> List[ProjectScript]:
    """列出项目所有剧本分集（按 episode_no 升序）"""
    result = await db.execute(
        select(ProjectScript)
        .where(ProjectScript.project_id == project_id)
        .order_by(ProjectScript.episode_no)
    )
    return result.scalars().all()


async def get_script(db: AsyncSession, script_id: int) -> Optional[ProjectScript]:
    """获取剧本详情"""
    result = await db.execute(
        select(ProjectScript).where(ProjectScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def create_script(
    db: AsyncSession, project_id: int, data: ScriptCreate
) -> ProjectScript:
    """新增剧本分集"""
    script = ProjectScript(
        project_id=project_id,
        episode_no=data.episode_no,
        title=data.title,
        content=data.content,
        outline=data.outline,
        status="draft",
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


async def update_script(
    db: AsyncSession, script_id: int, data: ScriptUpdate
) -> Optional[ProjectScript]:
    """编辑剧本"""
    script = await get_script(db, script_id)
    if not script:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(script, k, v)
    await db.commit()
    await db.refresh(script)
    return script


async def delete_script(db: AsyncSession, script_id: int) -> bool:
    """删除剧本分集"""
    script = await get_script(db, script_id)
    if not script:
        return False
    await db.delete(script)
    await db.commit()
    return True


# =====================================================
# 重新生成剧本（调用 LLM）
# =====================================================

async def regenerate_script(
    db: AsyncSession,
    script_id: int,
    prompt_template: Optional[str] = None,
    model: Optional[str] = None,
    inputs: Optional[dict] = None,
) -> Optional[ProjectScript]:
    """
    重新生成剧本内容（保留原 script 记录，覆盖 content）

    Args:
        prompt_template: 自定义 prompt 模板，不传则用原记录的模板
        model: 自定义模型，不传则用原记录的模型
        inputs: prompt_template 的格式化参数
    """
    script = await get_script(db, script_id)
    if not script:
        return None

    template = prompt_template or script.prompt_template
    if not template:
        raise ValueError("缺少 prompt_template，无法重新生成剧本")

    format_args = inputs or {}
    prompt = template.format(**format_args)

    body_model = await resolve_user_chat_model_id(
        db, 0, explicit=model or script.model
    ) if (model or script.model) else await resolve_project_chat_model_id(db, script.project_id)
    if not body_model:
        raise HTTPException(400, "未配置可用的对话模型，请先在配置页同步或添加对话模型")
    content = await agnes_client.chat_text(
        body_model, [{"role": "user", "content": prompt}], temperature=0.8,
    )

    script.content = content
    if prompt_template:
        script.prompt_template = prompt_template
    if model:
        script.model = model
    script.status = "approved"
    await db.commit()
    await db.refresh(script)
    return script

# =====================================================
# 项目制创作 API 路由
#
# 路由分组（前缀 /api/projects）:
#   1. 项目 CRUD:           POST/GET/PATCH/DELETE /projects[/{id}]
#   2. 项目操作:            POST /projects/{id}/archive, PATCH /projects/{id}/active-view
#   3. 向导:                POST /projects/wizard, POST /projects/{id}/wizard/resume
#   4. SSE:                 GET /projects/{id}/events
#   5. 剧本:                /projects/{id}/scripts[/{sid}][/regenerate]
#   6. 角色/场景/道具:      /projects/{id}/characters|scenes|props[/{eid}]
#                           + 子路由 generate-image / batch-generate / versions / set-active / upload / extract
#   7. 分镜:                /projects/{id}/shots[/{sid}][/reorder][/bind-character|bind-prop]
#   8. 帧图:                /projects/{id}/shots/{sid}/frame-images[/{vid}][/generate][/upload]
#   9. 视频:                /projects/{id}/shots/{sid}/videos[/{vid}][/generate][/upload]
#  10. 资产桥接:            /projects/{id}/entities/{etype}/{eid}/import-asset, /promote-asset
#  11. 画布:                /projects/{id}/canvas[/init]
#  12. 合成:                /projects/{id}/merge[/status][/advanced]
#  13. 配音（Phase 2）:     /projects/{id}/shots/{sid}/audios[/{vid}][/generate][/batch][/upload][/set-active]
#  14. 音色（Phase 2）:     /projects/{id}/voices/builtin, /projects/{id}/character-voices[/{cid}]
#  15. 字幕（Phase 2）:     /projects/{id}/subtitles[/generate][/generate-whisper][/clips][/style]
#  16. 时间线（Phase 2）:   /projects/{id}/timeline[/init][/clips[/{cid}]][/data]
#  17. BGM 库（Phase 2）:   /projects/{id}/bgms[/moods]
#  18. 素材库（Phase 2 增强）: /projects/{id}/media-library
#  19. 标记 Markers（Phase 2 增强）: /projects/{id}/markers[/{mid}]
# =====================================================

import asyncio
import logging
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import (
    get_current_user,
    decode_access_token,
    _extract_token_from_header,
)
from app.models.user import User
from app.models.project import (
    Project,
    ProjectScript,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectShot,
    ProjectEntityAsset,
    ProjectShotFrameImage,
    ProjectShotVideo,
    PROJECT_STATUS_CREATING,
)
from app.schemas.project import (
    # 项目
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse,
    ActiveViewUpdate,
    # 向导
    WizardCreateRequest, WizardResumeRequest,
    # 剧本
    ScriptCreate, ScriptUpdate, ScriptResponse, ScriptRegenerateRequest,
    # 角色/场景/道具
    CharacterCreate, CharacterUpdate, CharacterResponse,
    SceneCreate, SceneUpdate, SceneResponse,
    PropCreate, PropUpdate, PropResponse,
    # 实体素材
    EntityAssetResponse, SetActiveVersionRequest,
    # 分镜
    ShotCreate, ShotUpdate, ShotResponse, ReorderRequest, BindEntityRequest,
    # 帧图/视频
    FrameImageResponse, VideoResponse,
    GenerateImageRequest, BatchGenerateRequest, GenerateVideoRequest,
    # 资产桥接
    ImportAssetRequest, PromoteAssetRequest,
    # 画布
    CanvasDataUpdate, CanvasLayoutResponse,
    # 合成
    MergeRequest, MergeStatusResponse, MergeAdvancedRequest,
    # Phase 2 — 配音 / 音色 / 字幕 / 时间线
    ProjectShotAudioResponse,
    GenerateTTSRequest, BatchGenerateTTSRequest, SetActiveAudioRequest,
    CharacterVoiceResponse, AssignCharacterVoiceRequest, VoiceOption,
    GenerateSubtitleRequest, GenerateSubtitleAdvancedRequest,
    SubtitleStyle, SubtitleClip,
    TimelineClipResponse, TimelineClipCreate, TimelineClipUpdate,
    TimelineDataUpdate, TimelineDataResponse,
    # Phase 2 增强 — 素材库 / 标记
    MediaLibraryResponse, MarkerCreate, MarkerResponse,
)
from app.services.project import project_sse_manager
from app.services.project.project_service import (
    create_project, create_draft_for_wizard, get_project, list_projects,
    update_project, delete_project, archive_project, update_active_view, update_status,
    rebuild_project_cover, set_project_cover_from_frame,
)
from app.services.project.wizard import run_wizard
from app.services.project.script_service import (
    list_scripts, get_script, create_script, update_script, delete_script,
    regenerate_script,
)
from app.services.project.character_service import (
    list_characters, get_character, create_character, update_character, delete_character,
    reorder_characters, generate_character_image, batch_generate_characters,
    upload_character_image, list_character_versions, set_active_character_version,
    delete_character_version, extract_characters_from_script,
    claim_character_image,
)
from app.services.project.scene_service import (
    list_scenes, get_scene, create_scene, update_scene, delete_scene,
    reorder_scenes, generate_scene_image, batch_generate_scenes,
    upload_scene_image, list_scene_versions, set_active_scene_version,
    delete_scene_version, extract_scenes_from_script,
    claim_scene_image,
)
from app.services.project.prop_service import (
    list_props, get_prop, create_prop, update_prop, delete_prop,
    reorder_props, generate_prop_image, batch_generate_props,
    upload_prop_image, list_prop_versions, set_active_prop_version,
    delete_prop_version, extract_props_from_script,
    claim_prop_image,
)
from app.services.project.shot_service import (
    list_shots, get_shot, create_shot, update_shot, delete_shot, reorder_shots,
    bind_character, unbind_character, bind_prop, unbind_prop,
    generate_frame_prompt, split_shots_from_script,
)
from app.services.project.frame_image_service import (
    list_frame_images, get_frame_image, generate_frame_image,
    batch_generate_frame_images, upload_frame_image,
    set_active_frame_image, delete_frame_image,
    claim_frame_image,
)
from app.services.project.video_service import (
    list_videos, get_video, generate_video, upload_video,
    set_active_video, delete_video,
    claim_video,
)
from app.services.project.asset_bridge import (
    import_asset_to_project, promote_entity_to_asset,
)
from app.services.project.canvas_bridge import (
    init_canvas_layout, get_canvas_data, save_canvas_data,
)
from app.services.project.merge_service import (
    merge_project, get_merge_status,
)
from app.services.project.audio_service import (
    list_builtin_voices as list_builtin_voice_options,
    generate_audio, batch_generate_audios, upload_audio,
    set_active_audio, list_audios, delete_audio,
    assign_character_voice, list_character_voices,
)
from app.services.project.subtitle_service import (
    generate_subtitles, generate_subtitles_with_whisper,
    is_whisper_available, get_subtitle_clips,
)
from app.services.project.timeline_service import (
    init_timeline, list_clips as list_timeline_clips,
    create_clip as create_timeline_clip,
    update_clip as update_timeline_clip,
    delete_clip as delete_timeline_clip,
    split_clip as split_timeline_clip,
    ripple_delete_clip as ripple_delete_timeline_clip,
    get_timeline_data, save_timeline_data,
    get_subtitle_style, update_subtitle_style,
    get_media_library,
)
from app.services.project.bgm_library import (
    list_bgms as list_bgm_library,
    list_moods as list_bgm_moods,
    get_bgm_path,
)
from app.services.project.marker_service import (
    list_markers as list_project_markers,
    create_marker as create_project_marker,
    delete_marker as delete_project_marker,
    find_nearest_marker as find_nearest_project_marker,
)

logger = logging.getLogger("agnes_platform.project.routes")

router = APIRouter(prefix="/projects", tags=["项目制创作"])


# =====================================================
# 工具函数
# =====================================================

def _check_project_owner(project: Project, user: User) -> None:
    """校验项目所有权"""
    if project.user_id != user.id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="无权操作此项目")


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    project = await get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


# =====================================================
# 1. 项目 CRUD
# =====================================================

@router.post("", response_model=ProjectResponse, summary="创建项目（空白）")
async def create_project_api(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建空白项目（不通过向导）"""
    project = await create_project(db, current_user.id, data)
    project_sse_manager.init_snapshot(project.id, project.status)
    return project


@router.get("", response_model=ProjectListResponse, summary="列出项目")
async def list_projects_api(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await list_projects(db, current_user.id, status, page, page_size)
    return ProjectListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{project_id}", response_model=ProjectResponse, summary="获取项目详情")
async def get_project_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return project


@router.patch("/{project_id}", response_model=ProjectResponse, summary="更新项目")
async def update_project_api(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    updated = await update_project(db, project_id, data)
    return updated


@router.delete("/{project_id}", summary="删除项目")
async def delete_project_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_project(db, project_id)
    return {"success": ok}


@router.post("/{project_id}/archive", response_model=ProjectResponse, summary="归档项目")
async def archive_project_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await archive_project(db, project_id)


@router.patch("/{project_id}/active-view", response_model=ProjectResponse, summary="切换活动视图")
async def update_active_view_api(
    project_id: int,
    data: ActiveViewUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await update_active_view(db, project_id, data.view)


@router.post("/{project_id}/rebuild-cover", response_model=ProjectResponse, summary="自动选取封面")
async def rebuild_cover_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """从分镜帧图中自动选取封面（按分镜顺序取第一个激活帧图）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    updated = await rebuild_project_cover(db, project_id)
    if not updated:
        raise HTTPException(status_code=404, detail="项目不存在")
    return updated


@router.post("/{project_id}/set-cover", response_model=ProjectResponse, summary="指定帧图设置封面")
async def set_cover_api(
    project_id: int,
    data: dict,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """将指定帧图设为项目封面"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    frame_image_id = data.get("frame_image_id")
    if not frame_image_id:
        raise HTTPException(status_code=400, detail="缺少 frame_image_id 参数")
    updated = await set_project_cover_from_frame(db, project_id, int(frame_image_id))
    if not updated:
        raise HTTPException(status_code=400, detail="帧图不存在或不属于该项目")
    return updated


@router.post("/rebuild-missing-covers", summary="批量回填当前用户无封面的项目")
async def rebuild_missing_covers_api(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """为当前用户所有缺少封面但已有激活帧图的项目自动补全封面"""
    from sqlalchemy import select as sa_select, and_
    from app.models.project import Project, ProjectShot, ProjectShotFrameImage

    result = await db.execute(
        sa_select(Project).where(
            Project.user_id == current_user.id,
            (Project.cover_url.is_(None)) | (Project.cover_url == ""),
        )
    )
    projects = result.scalars().all()
    updated = 0
    skipped = 0
    for project in projects:
        frame_result = await db.execute(
            sa_select(ProjectShotFrameImage)
            .join(ProjectShot, ProjectShot.id == ProjectShotFrameImage.shot_id)
            .where(
                ProjectShot.project_id == project.id,
                ProjectShotFrameImage.is_active.is_(True),
                ProjectShotFrameImage.thumbnail_url.isnot(None),
                ProjectShotFrameImage.thumbnail_url != "",
            )
            .order_by(ProjectShot.sort_order, ProjectShot.sequence_no, ProjectShotFrameImage.version.desc())
            .limit(1)
        )
        frame = frame_result.scalar_one_or_none()
        if frame and frame.thumbnail_url:
            project.cover_url = frame.thumbnail_url
            updated += 1
        else:
            skipped += 1
    await db.commit()
    return {"total": len(projects), "updated": updated, "skipped": skipped}


# =====================================================
# 2. 向导
# =====================================================

@router.post("/wizard", response_model=ProjectResponse, summary="通过模板向导创建项目")
async def create_via_wizard_api(
    data: WizardCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    通过模板向导创建项目（4 步 LLM 链）

    使用 category 模式：从 wizard_chains.WIZARD_CHAINS 预设链路查找（drama/ad/education/anime）

    1. 创建草稿项目（status=creating）
    2. 后台异步执行 wizard 链
    3. 前端通过 SSE 监听进度
    """
    from app.services.project.wizard_chains import get_wizard_chain, is_wizard_chain

    category: Optional[str] = data.category

    if not category:
        raise HTTPException(
            status_code=400,
            detail="必须提供 category 参数",
        )

    # 从预设 WIZARD_CHAINS 查找
    wizard_chain = get_wizard_chain(category)

    # 把 category 写入 wizard_inputs，便于 resume 时找回链路
    merged_inputs = dict(data.inputs or {})
    merged_inputs.setdefault("_category", category)

    # 创建草稿项目
    project = await create_draft_for_wizard(
        db,
        current_user.id,
        ProjectCreate(
            title=data.title,
            description=data.description,
            aspect_ratio=data.aspect_ratio,
            resolution=data.resolution,
            wizard_inputs=merged_inputs,
        ),
    )
    project_sse_manager.init_snapshot(project.id, project.status)

    # 后台执行向导（独立 session）
    asyncio.create_task(_run_wizard_async(project.id, wizard_chain, merged_inputs))
    return project


async def _run_wizard_async(
    project_id: int, wizard_chain: list, inputs: dict
) -> None:
    """后台执行向导（独立 session）"""
    from app.core.database import new_async_session

    db = new_async_session()
    try:
        project = await get_project(db, project_id)
        if not project:
            return
        await run_wizard(db, project, wizard_chain, inputs)
    except Exception as e:
        logger.error(f"向导执行失败 project_id={project_id}: {e}")
        await update_status(db, project_id, "in_progress")
        await project_sse_manager.push(
            project_id,
            "wizard_step_failed",
            {"step": "*", "error": str(e)},
        )
    finally:
        await db.close()


@router.post("/{project_id}/wizard/resume", response_model=ProjectResponse, summary="恢复中断的向导")
async def resume_wizard_api(
    project_id: int,
    data: WizardResumeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)

    if project.status != PROJECT_STATUS_CREATING:
        raise HTTPException(status_code=400, detail="项目不在向导中，无需恢复")

    from app.services.project.wizard_chains import get_wizard_chain

    inputs = dict(project.wizard_inputs or {})
    category = inputs.get("_category")

    if not category:
        raise HTTPException(
            status_code=400,
            detail="无法找回 wizard_chain（缺少 category）",
        )

    wizard_chain = get_wizard_chain(category)

    asyncio.create_task(
        _run_wizard_async(project.id, wizard_chain, inputs)
    )
    return project


# =====================================================
# 3. SSE 实时事件
# =====================================================

@router.get("/{project_id}/events", summary="SSE 项目事件推送")
async def project_sse_events(
    project_id: int,
    request: Request,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Server-Sent Events 实时推送项目事件（向导进度/生成进度/实体变更等）

    事件类型详见 sse_manager.py 模块文档
    """
    # 认证（支持 header 与 query 两种方式，供 EventSource 使用）
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    resolved_token = _extract_token_from_header(auth_header) if auth_header else token
    if not resolved_token:
        raise HTTPException(status_code=401, detail="未登录或 token 无效")
    user_id = decode_access_token(resolved_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 已过期或无效")

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")

    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, user)

    queue = await project_sse_manager.subscribe(project_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await project_sse_manager.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =====================================================
# 4. 剧本
# =====================================================

@router.get("/{project_id}/scripts", response_model=List[ScriptResponse], summary="列出剧本")
async def list_scripts_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_scripts(db, project_id)


@router.post("/{project_id}/scripts", response_model=ScriptResponse, summary="新增剧本")
async def create_script_api(
    project_id: int,
    data: ScriptCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await create_script(db, project_id, data)


@router.get("/{project_id}/scripts/{script_id}", response_model=ScriptResponse, summary="获取剧本")
async def get_script_api(
    project_id: int,
    script_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    script = await get_script(db, script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return script


@router.patch("/{project_id}/scripts/{script_id}", response_model=ScriptResponse, summary="编辑剧本")
async def update_script_api(
    project_id: int,
    script_id: int,
    data: ScriptUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    script = await update_script(db, script_id, data)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return script


@router.delete("/{project_id}/scripts/{script_id}", summary="删除剧本")
async def delete_script_api(
    project_id: int,
    script_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_script(db, script_id)
    return {"success": ok}


@router.post("/{project_id}/scripts/{script_id}/regenerate", response_model=ScriptResponse, summary="重新生成剧本")
async def regenerate_script_api(
    project_id: int,
    script_id: int,
    data: ScriptRegenerateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        script = await regenerate_script(
            db, script_id, data.prompt_template, data.model,
            project.wizard_inputs or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return script


# =====================================================
# 5. 角色 / 场景 / 道具（统一模式）
# =====================================================

# 通用实体路由工厂（避免 character/scene/prop 三套几乎相同的代码）
def _build_entity_routes(prefix: str, entity_type: str):
    """生成角色/场景/道具的统一路由"""

    # 按类型选择对应的服务函数
    if entity_type == "character":
        list_fn = list_characters
        get_fn = get_character
        create_fn = create_character
        update_fn = update_character
        delete_fn = delete_character
        reorder_fn = reorder_characters
        gen_image_fn = generate_character_image
        batch_gen_fn = batch_generate_characters
        upload_fn = upload_character_image
        list_v_fn = list_character_versions
        set_v_fn = set_active_character_version
        del_v_fn = delete_character_version
        extract_fn = extract_characters_from_script
        claim_fn = claim_character_image
        create_schema = CharacterCreate
        update_schema = CharacterUpdate
        response_schema = CharacterResponse
        entity_label = "角色"
    elif entity_type == "scene":
        list_fn = list_scenes
        get_fn = get_scene
        create_fn = create_scene
        update_fn = update_scene
        delete_fn = delete_scene
        reorder_fn = reorder_scenes
        gen_image_fn = generate_scene_image
        batch_gen_fn = batch_generate_scenes
        upload_fn = upload_scene_image
        list_v_fn = list_scene_versions
        set_v_fn = set_active_scene_version
        del_v_fn = delete_scene_version
        extract_fn = extract_scenes_from_script
        claim_fn = claim_scene_image
        create_schema = SceneCreate
        update_schema = SceneUpdate
        response_schema = SceneResponse
        entity_label = "场景"
    else:  # prop
        list_fn = list_props
        get_fn = get_prop
        create_fn = create_prop
        update_fn = update_prop
        delete_fn = delete_prop
        reorder_fn = reorder_props
        gen_image_fn = generate_prop_image
        batch_gen_fn = batch_generate_props
        upload_fn = upload_prop_image
        list_v_fn = list_prop_versions
        set_v_fn = set_active_prop_version
        del_v_fn = delete_prop_version
        extract_fn = extract_props_from_script
        claim_fn = claim_prop_image
        create_schema = PropCreate
        update_schema = PropUpdate
        response_schema = PropResponse
        entity_label = "道具"

    @router.get(
        f"/{{project_id}}/{prefix}",
        response_model=List[response_schema],
        summary=f"列出{entity_label}",
    )
    async def list_api(
        project_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        return await list_fn(db, project_id)

    @router.post(
        f"/{{project_id}}/{prefix}",
        response_model=response_schema,
        summary=f"添加{entity_label}",
    )
    async def create_api(
        project_id: int,
        data: create_schema,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        return await create_fn(db, project_id, data)

    @router.get(
        f"/{{project_id}}/{prefix}/{{entity_id}}",
        response_model=response_schema,
        summary=f"获取{entity_label}",
    )
    async def get_api(
        project_id: int,
        entity_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        entity = await get_fn(db, entity_id)
        if not entity or entity.project_id != project_id:
            raise HTTPException(status_code=404, detail=f"{entity_label}不存在")
        return entity

    @router.patch(
        f"/{{project_id}}/{prefix}/{{entity_id}}",
        response_model=response_schema,
        summary=f"编辑{entity_label}",
    )
    async def update_api(
        project_id: int,
        entity_id: int,
        data: update_schema,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        entity = await update_fn(db, entity_id, data)
        if not entity:
            raise HTTPException(status_code=404, detail=f"{entity_label}不存在")
        return entity

    @router.delete(
        f"/{{project_id}}/{prefix}/{{entity_id}}",
        summary=f"删除{entity_label}",
    )
    async def delete_api(
        project_id: int,
        entity_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        ok = await delete_fn(db, entity_id)
        return {"success": ok}

    @router.patch(
        f"/{{project_id}}/{prefix}/reorder",
        summary=f"重排{entity_label}",
    )
    async def reorder_api(
        project_id: int,
        data: ReorderRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        await reorder_fn(db, project_id, data.ids)
        return {"success": True}

    @router.post(
        f"/{{project_id}}/{prefix}/{{entity_id}}/generate-image",
        summary=f"生成{entity_label}形象图（异步）",
    )
    async def generate_image_api(
        project_id: int,
        entity_id: int,
        data: GenerateImageRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        try:
            return await gen_image_fn(
                db, entity_id, current_user.id,
                data.style_config, data.model, data.size or "1024x1024",
            )
        except (ValueError, RuntimeError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post(
        f"/{{project_id}}/{prefix}/{{entity_id}}/claim-image",
        response_model=response_schema,
        summary=f"认领{entity_label}生成结果",
    )
    async def claim_image_api(
        project_id: int,
        entity_id: int,
        task_id: str = Query(..., description="图片任务 ID"),
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        """任务完成后认领结果：从 Generation 拿 result_url，创建实体形象图新版本"""
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        try:
            entity = await claim_fn(db, entity_id, task_id)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not entity:
            raise HTTPException(status_code=404, detail="实体不存在或任务结果未就绪")
        return entity

    @router.post(
        f"/{{project_id}}/{prefix}/batch-generate",
        summary=f"批量生成{entity_label}形象图",
    )
    async def batch_generate_api(
        project_id: int,
        data: BatchGenerateRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        results = await batch_gen_fn(
            db, data.ids, current_user.id,
            data.style_config, data.model, data.size or "1024x1024",
        )
        return {"results": results}

    @router.post(
        f"/{{project_id}}/{prefix}/{{entity_id}}/upload-image",
        response_model=response_schema,
        summary=f"上传{entity_label}形象图",
    )
    async def upload_image_api(
        project_id: int,
        entity_id: int,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        # 简化处理：将文件保存到本地临时目录（实际生产应上传到对象存储）
        from app.services.upload_service import save_upload_file
        file_url = await save_upload_file(file, folder=f"projects/{project_id}/{prefix}")
        return await upload_fn(db, entity_id, current_user.id, file_url)

    @router.get(
        f"/{{project_id}}/{prefix}/{{entity_id}}/versions",
        response_model=List[EntityAssetResponse],
        summary=f"列出{entity_label}形象图版本",
    )
    async def list_versions_api(
        project_id: int,
        entity_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        return await list_v_fn(db, entity_id)

    @router.post(
        f"/{{project_id}}/{prefix}/{{entity_id}}/set-active",
        response_model=EntityAssetResponse,
        summary=f"设为采用版",
    )
    async def set_active_api(
        project_id: int,
        entity_id: int,
        data: SetActiveVersionRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        asset = await set_v_fn(db, entity_id, data.version_id)
        if not asset:
            raise HTTPException(status_code=400, detail="版本不存在或不属于该实体")
        return asset

    @router.delete(
        f"/{{project_id}}/{prefix}/{{entity_id}}/versions/{{version_id}}",
        summary=f"删除{entity_label}形象图版本",
    )
    async def delete_version_api(
        project_id: int,
        entity_id: int,
        version_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        ok = await del_v_fn(db, entity_id, version_id)
        if not ok:
            raise HTTPException(status_code=400, detail="无法删除（激活版不允许删除或版本不存在）")
        return {"success": ok}

    @router.post(
        f"/{{project_id}}/{prefix}/extract-from-script",
        summary=f"从剧本提取{entity_label}",
    )
    async def extract_api(
        project_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ):
        project = await _get_project_or_404(db, project_id)
        _check_project_owner(project, current_user)
        return await extract_fn(db, project_id)


# 注册三类实体路由
_build_entity_routes("characters", "character")
_build_entity_routes("scenes", "scene")
_build_entity_routes("props", "prop")


# =====================================================
# 6. 分镜
# =====================================================

@router.get("/{project_id}/shots", response_model=List[ShotResponse], summary="列出分镜")
async def list_shots_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    shots = await list_shots(db, project_id)
    # 将关联实体附加到响应
    result = []
    for shot in shots:
        item = ShotResponse.model_validate(shot)
        item.characters = [
            CharacterResponse.model_validate(c)
            for c in getattr(shot, "_characters", [])
        ]
        item.props = [
            PropResponse.model_validate(p)
            for p in getattr(shot, "_props", [])
        ]
        result.append(item)
    return result


@router.post("/{project_id}/shots", response_model=ShotResponse, summary="添加分镜")
async def create_shot_api(
    project_id: int,
    data: ShotCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await create_shot(db, project_id, data)


@router.post("/{project_id}/shots/split", summary="从剧本 AI 拆分分镜")
async def split_shots_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        return await split_shots_from_script(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}/shots/{shot_id}", response_model=ShotResponse, summary="获取分镜")
async def get_shot_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    shot = await get_shot(db, shot_id)
    if not shot or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="分镜不存在")
    item = ShotResponse.model_validate(shot)
    item.characters = [
        CharacterResponse.model_validate(c)
        for c in getattr(shot, "_characters", [])
    ]
    item.props = [
        PropResponse.model_validate(p)
        for p in getattr(shot, "_props", [])
    ]
    return item


@router.patch("/{project_id}/shots/{shot_id}", response_model=ShotResponse, summary="编辑分镜")
async def update_shot_api(
    project_id: int,
    shot_id: int,
    data: ShotUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    shot = await update_shot(db, shot_id, data)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return shot


@router.delete("/{project_id}/shots/{shot_id}", summary="删除分镜")
async def delete_shot_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_shot(db, shot_id)
    return {"success": ok}


@router.patch("/{project_id}/shots/reorder", summary="重排分镜")
async def reorder_shots_api(
    project_id: int,
    data: ReorderRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await reorder_shots(db, project_id, data.ids)
    return {"success": True}


@router.post("/{project_id}/shots/{shot_id}/bind-character", summary="绑定角色")
async def bind_character_api(
    project_id: int,
    shot_id: int,
    data: BindEntityRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await bind_character(db, shot_id, data.entity_id)
    return {"success": True}


@router.post("/{project_id}/shots/{shot_id}/unbind-character", summary="解绑角色")
async def unbind_character_api(
    project_id: int,
    shot_id: int,
    data: BindEntityRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await unbind_character(db, shot_id, data.entity_id)
    return {"success": True}


@router.post("/{project_id}/shots/{shot_id}/bind-prop", summary="绑定道具")
async def bind_prop_api(
    project_id: int,
    shot_id: int,
    data: BindEntityRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await bind_prop(db, shot_id, data.entity_id)
    return {"success": True}


@router.post("/{project_id}/shots/{shot_id}/unbind-prop", summary="解绑道具")
async def unbind_prop_api(
    project_id: int,
    shot_id: int,
    data: BindEntityRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await unbind_prop(db, shot_id, data.entity_id)
    return {"success": True}


@router.post(
    "/{project_id}/shots/{shot_id}/generate-frame-prompt",
    response_model=ShotResponse,
    summary="生成帧 prompt",
)
async def generate_frame_prompt_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    shot = await generate_frame_prompt(db, shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return shot


# =====================================================
# 7. 帧图
# =====================================================

@router.get(
    "/{project_id}/shots/{shot_id}/frame-images",
    response_model=List[FrameImageResponse],
    summary="列出帧图版本",
)
async def list_frame_images_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_frame_images(db, shot_id)


@router.post(
    "/{project_id}/shots/{shot_id}/frame-images/generate",
    summary="生成帧图（异步）",
)
async def generate_frame_image_api(
    project_id: int,
    shot_id: int,
    data: GenerateImageRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        return await generate_frame_image(
            db, shot_id, current_user.id,
            data.style_config, data.model, data.size or "1024x1024",
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{project_id}/shots/{shot_id}/frame-images/claim",
    response_model=FrameImageResponse,
    summary="认领帧图生成结果",
)
async def claim_frame_image_api(
    project_id: int,
    shot_id: int,
    task_id: str = Query(..., description="图片任务 ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """任务完成后认领结果：从 Generation 拿 result_url，创建帧图新版本"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        fi = await claim_frame_image(db, shot_id, task_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not fi:
        raise HTTPException(status_code=404, detail="分镜不存在或任务结果未就绪")
    return fi


@router.post(
    "/{project_id}/shots/frame-images/batch-generate",
    summary="批量生成帧图",
)
async def batch_generate_frame_images_api(
    project_id: int,
    data: BatchGenerateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    results = await batch_generate_frame_images(
        db, data.ids, current_user.id,
        data.style_config, data.model, data.size or "1024x1024",
    )
    return {"results": results}


@router.post(
    "/{project_id}/shots/{shot_id}/frame-images/upload",
    response_model=FrameImageResponse,
    summary="上传帧图",
)
async def upload_frame_image_api(
    project_id: int,
    shot_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    from app.services.upload_service import save_upload_file
    file_url = await save_upload_file(file, folder=f"projects/{project_id}/shots/{shot_id}/frames")
    fi = await upload_frame_image(db, shot_id, current_user.id, file_url)
    if not fi:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return fi


@router.post(
    "/{project_id}/shots/{shot_id}/frame-images/{version_id}/set-active",
    response_model=FrameImageResponse,
    summary="设为采用版",
)
async def set_active_frame_image_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    fi = await set_active_frame_image(db, shot_id, version_id)
    if not fi:
        raise HTTPException(status_code=400, detail="版本不存在或不属于该分镜")
    return fi


@router.delete(
    "/{project_id}/shots/{shot_id}/frame-images/{version_id}",
    summary="删除帧图版本",
)
async def delete_frame_image_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_frame_image(db, shot_id, version_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法删除（激活版不允许删除或版本不存在）")
    return {"success": ok}


# =====================================================
# 8. 视频
# =====================================================

@router.get(
    "/{project_id}/shots/{shot_id}/videos",
    response_model=List[VideoResponse],
    summary="列出视频版本",
)
async def list_videos_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_videos(db, shot_id)


@router.post(
    "/{project_id}/shots/{shot_id}/videos/generate",
    summary="生成视频（异步）",
)
async def generate_video_api(
    project_id: int,
    shot_id: int,
    data: GenerateVideoRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        return await generate_video(
            db, shot_id, current_user.id,
            data.frame_image_id, data.model, data.duration_ms,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{project_id}/shots/{shot_id}/videos/claim",
    response_model=VideoResponse,
    summary="认领视频生成结果",
)
async def claim_video_api(
    project_id: int,
    shot_id: int,
    task_id: str = Query(..., description="视频任务 ID"),
    frame_image_id: Optional[int] = Query(None, description="来源帧图 ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """任务完成后认领结果：从 Generation 拿 result_url，创建视频新版本"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        video = await claim_video(db, shot_id, task_id, frame_image_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not video:
        raise HTTPException(status_code=404, detail="分镜不存在或任务结果未就绪")
    return video


@router.post(
    "/{project_id}/shots/{shot_id}/videos/upload",
    response_model=VideoResponse,
    summary="上传视频",
)
async def upload_video_api(
    project_id: int,
    shot_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    from app.services.upload_service import save_upload_file
    file_url = await save_upload_file(file, folder=f"projects/{project_id}/shots/{shot_id}/videos")
    video = await upload_video(db, shot_id, current_user.id, file_url)
    if not video:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return video


@router.post(
    "/{project_id}/shots/{shot_id}/videos/{version_id}/set-active",
    response_model=VideoResponse,
    summary="设为采用版",
)
async def set_active_video_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    video = await set_active_video(db, shot_id, version_id)
    if not video:
        raise HTTPException(status_code=400, detail="版本不存在或不属于该分镜")
    return video


@router.delete(
    "/{project_id}/shots/{shot_id}/videos/{version_id}",
    summary="删除视频版本",
)
async def delete_video_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_video(db, shot_id, version_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法删除（激活版不允许删除或版本不存在）")
    return {"success": ok}


# =====================================================
# 9. 资产桥接
# =====================================================

@router.post(
    "/{project_id}/entities/{entity_type}/import-asset",
    summary="从资产库导入到项目",
)
async def import_asset_api(
    project_id: int,
    entity_type: str,
    data: ImportAssetRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        entity = await import_asset_to_project(
            db, data.asset_id, project_id, entity_type, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "entity_id": entity.id}


@router.post(
    "/{project_id}/entities/{entity_type}/{entity_id}/promote-asset",
    summary="沉淀到资产库",
)
async def promote_asset_api(
    project_id: int,
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        asset = await promote_entity_to_asset(
            db, entity_type, entity_id, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "asset_id": asset.id}


# =====================================================
# 10. 画布
# =====================================================

@router.get(
    "/{project_id}/canvas",
    response_model=CanvasLayoutResponse,
    summary="获取画布数据",
)
async def get_canvas_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    canvas_data = await get_canvas_data(db, project_id)
    return CanvasLayoutResponse(canvas_data=canvas_data)


@router.post(
    "/{project_id}/canvas/init",
    response_model=CanvasLayoutResponse,
    summary="初始化画布布局",
)
async def init_canvas_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    canvas_data = await init_canvas_layout(db, project_id)
    return CanvasLayoutResponse(canvas_data=canvas_data)


@router.patch(
    "/{project_id}/canvas",
    response_model=CanvasLayoutResponse,
    summary="保存画布布局",
)
async def save_canvas_api(
    project_id: int,
    data: CanvasDataUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await save_canvas_data(db, project_id, data.canvas_data)
    return CanvasLayoutResponse(canvas_data=data.canvas_data)


# =====================================================
# 11. 合成
# =====================================================

@router.post("/{project_id}/merge", response_model=MergeStatusResponse, summary="触发合成（简单拼接）")
async def merge_project_api(
    project_id: int,
    data: MergeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """简单合成：按分镜顺序 concat 拼接视频（无音频/字幕/转场）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        await merge_project(db, project_id, current_user.id, use_timeline=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return MergeStatusResponse(status="started")


@router.post(
    "/{project_id}/merge/advanced",
    response_model=MergeStatusResponse,
    summary="触发高级合成（多轨 + 转场 + 音频 + 字幕 + BGM）",
)
async def merge_project_advanced_api(
    project_id: int,
    data: MergeAdvancedRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    高级合成（Phase 2）:
    - 视频轨: xfade 转场（fade/slide/wipe/dissolve）
    - 音频轨: TTS 拼接（30ms 淡入淡出）+ BGM amix 混音
    - 字幕轨: ASS 烧录
    - BGM: 内置库选择（with_bgm=True 时需指定 bgm_id）
    """
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        await merge_project(
            db, project_id, current_user.id,
            with_audio=data.with_audio,
            with_subtitle=data.with_subtitle,
            with_bgm=data.with_bgm,
            bgm_id=data.bgm_id,
            use_timeline=data.use_timeline,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return MergeStatusResponse(status="started")


@router.get("/{project_id}/merge/status", response_model=MergeStatusResponse, summary="查询合成状态")
async def get_merge_status_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return MergeStatusResponse(**await get_merge_status(db, project_id))


@router.get("/{project_id}/final-video", summary="下载/播放项目最终成片")
async def get_final_video_api(
    project_id: int,
    request: Request,
    token: Optional[str] = Query(None, description="JWT token（用于 <video> / window.open 无法设置 header 的场景）"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    流式返回项目合成后的最终成片 mp4 文件。

    - 文件存储位置：backend/outputs/projects/{project_id}/final.mp4
    - 用途：前端通过 <video> 标签或 window.open 播放
    - 认证：支持 Authorization header 和 ?token=<jwt> query 参数两种方式
      （<video> 标签和 window.open 无法设置 header，必须用 query token）
    """
    import os

    # 认证：优先 header，其次 query 参数
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    jwt_token = _extract_token_from_header(auth_header) or token
    if not jwt_token:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = decode_access_token(jwt_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 已过期或无效")
    result = await db.execute(select(User).filter(User.id == user_id))
    current_user = result.scalar_one_or_none()
    if current_user is None or not current_user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)

    if not project.final_video_url:
        raise HTTPException(status_code=404, detail="项目尚未合成最终视频")

    # 文件持久化在 backend/outputs/projects/{project_id}/final.mp4
    file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs", "projects", str(project_id), "final.mp4",
    )
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="成片文件不存在或已被清理")

    file_size = os.path.getsize(file_path)

    def iterfile():
        # 1MB 分块读取，避免大文件一次性加载到内存
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="video/mp4",
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        },
    )


# =====================================================
# 13. 配音（Phase 2）— TTS 生成 / 多版本管理
# -------------------------------------------------
# 路由:
#   POST   /projects/{id}/shots/{sid}/audios/generate         生成 TTS（异步）
#   POST   /projects/{id}/shots/audios/batch-generate         批量 TTS
#   POST   /projects/{id}/shots/{sid}/audios/upload           上传音频
#   GET    /projects/{id}/shots/{sid}/audios                  列出音频版本
#   POST   /projects/{id}/shots/{sid}/audios/{vid}/set-active 设为采用版
#   DELETE /projects/{id}/shots/{sid}/audios/{vid}            删除音频版本
# =====================================================

@router.post(
    "/{project_id}/shots/{shot_id}/audios/generate",
    response_model=ProjectShotAudioResponse,
    summary="生成 TTS 配音（异步）",
)
async def generate_audio_api(
    project_id: int,
    shot_id: int,
    data: GenerateTTSRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """生成分镜 TTS 配音（同角色同声音自动分配音色）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        return await generate_audio(
            db, shot_id, current_user.id,
            voice_id=data.voice_id,
            character_id=data.character_id,
            text=data.text,
            model=data.model,
            provider=data.provider,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{project_id}/shots/audios/batch-generate",
    summary="批量生成 TTS 配音",
)
async def batch_generate_audios_api(
    project_id: int,
    data: BatchGenerateTTSRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """批量 TTS 生成（并行），返回成功生成的 audio_id 列表"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    audio_ids = await batch_generate_audios(
        db, data.shot_ids, current_user.id, voice_id=data.voice_id,
    )
    return {"audio_ids": audio_ids, "success_count": len(audio_ids)}


@router.post(
    "/{project_id}/shots/{shot_id}/audios/upload",
    response_model=ProjectShotAudioResponse,
    summary="上传音频（替代 TTS）",
)
async def upload_audio_api(
    project_id: int,
    shot_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """用户上传音频替代 TTS（is_manual=True）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    from app.services.upload_service import save_upload_file
    file_url = await save_upload_file(file, folder=f"projects/{project_id}/shots/{shot_id}/audios")
    audio = await upload_audio(db, shot_id, current_user.id, file_url)
    if not audio:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return audio


@router.get(
    "/{project_id}/shots/{shot_id}/audios",
    response_model=List[ProjectShotAudioResponse],
    summary="列出音频版本",
)
async def list_audios_api(
    project_id: int,
    shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_audios(db, shot_id)


@router.post(
    "/{project_id}/shots/{shot_id}/audios/{version_id}/set-active",
    response_model=ProjectShotAudioResponse,
    summary="设为采用版音频",
)
async def set_active_audio_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        return await set_active_audio(db, shot_id, version_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{project_id}/shots/{shot_id}/audios/{version_id}",
    summary="删除音频版本",
)
async def delete_audio_api(
    project_id: int,
    shot_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_audio(db, shot_id, version_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="无法删除（采用版不允许删除或版本不存在）",
        )
    return {"success": ok}


# =====================================================
# 14. 音色（Phase 2）— 内置音色库 + 角色音色映射
# -------------------------------------------------
# 路由:
#   GET    /projects/{id}/voices/builtin                内置音色清单
#   GET    /projects/{id}/character-voices              角色音色映射列表
#   POST   /projects/{id}/character-voices/{cid}        为角色分配音色
# =====================================================

@router.get(
    "/{project_id}/voices/builtin",
    response_model=List[VoiceOption],
    summary="内置音色清单",
)
async def list_builtin_voices_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """返回内置音色清单（供前端音色选择器）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    voices = list_builtin_voice_options()
    return [
        VoiceOption(
            voice_id=v.get("voice_id", ""),
            name=v.get("name", ""),
            gender=v.get("gender", "neutral"),
            suitable_for=v.get("suitable_for", ""),
        )
        for v in voices
    ]


@router.get(
    "/{project_id}/character-voices",
    response_model=List[CharacterVoiceResponse],
    summary="角色音色映射列表",
)
async def list_character_voices_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_character_voices(db, project_id)


@router.post(
    "/{project_id}/character-voices/{character_id}",
    response_model=CharacterVoiceResponse,
    summary="为角色分配音色",
)
async def assign_character_voice_api(
    project_id: int,
    character_id: int,
    data: AssignCharacterVoiceRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """为角色分配音色（同角色同声音，upsert）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await assign_character_voice(
        db, project_id, character_id,
        voice_id=data.voice_id, voice_name=data.voice_name,
    )


# =====================================================
# 15. 字幕（Phase 2）— LLM 拆分 / Whisper 对齐 / 样式
# -------------------------------------------------
# 路由:
#   POST   /projects/{id}/subtitles/generate             生成字幕（LLM 模式）
#   POST   /projects/{id}/subtitles/generate-whisper     生成字幕（whisper 模式，未安装回退 LLM）
#   GET    /projects/{id}/subtitles/clips                字幕片段列表
#   GET    /projects/{id}/subtitles/style                字幕样式
#   PATCH  /projects/{id}/subtitles/style                更新字幕样式
#   GET    /projects/{id}/subtitles/whisper-available    检查 whisper 是否可用
# =====================================================

@router.post(
    "/{project_id}/subtitles/generate",
    summary="生成字幕（LLM 拆分模式）",
)
async def generate_subtitles_api(
    project_id: int,
    data: GenerateSubtitleRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """LLM 模式：分镜对白拆分为短字幕，按权重分配时长"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clips = await generate_subtitles(
        db, project_id,
        shot_ids=data.shot_ids, mode="llm",
    )
    return {"clips": clips, "count": len(clips), "mode": "llm"}


@router.post(
    "/{project_id}/subtitles/generate-whisper",
    summary="生成字幕（whisper forced alignment 模式）",
)
async def generate_subtitles_whisper_api(
    project_id: int,
    data: GenerateSubtitleAdvancedRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    whisper 模式：基于 TTS 音频做 forced alignment，时间戳精确到毫秒。

    未安装 faster-whisper 时自动回退 LLM 模式。
    """
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clips = await generate_subtitles_with_whisper(
        db, project_id,
        shot_ids=data.shot_ids,
        whisper_model_size=data.whisper_model_size,
    )
    return {
        "clips": clips,
        "count": len(clips),
        "mode": "whisper" if is_whisper_available() else "llm",
        "whisper_available": is_whisper_available(),
    }


@router.get(
    "/{project_id}/subtitles/clips",
    response_model=List[TimelineClipResponse],
    summary="字幕片段列表",
)
async def list_subtitle_clips_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clips = await get_subtitle_clips(db, project_id)
    return [TimelineClipResponse.model_validate(c) for c in clips]


@router.get(
    "/{project_id}/subtitles/style",
    response_model=SubtitleStyle,
    summary="获取字幕样式",
)
async def get_subtitle_style_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    style = await get_subtitle_style(db, project_id)
    return SubtitleStyle(**style)


@router.patch(
    "/{project_id}/subtitles/style",
    response_model=SubtitleStyle,
    summary="更新字幕样式",
)
async def update_subtitle_style_api(
    project_id: int,
    data: SubtitleStyle,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await update_subtitle_style(db, project_id, data.model_dump())
    return data


@router.get(
    "/{project_id}/subtitles/whisper-available",
    summary="检查 whisper 是否可用",
)
async def check_whisper_available_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """前端用于决定是否展示 whisper 模式选项"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return {"available": is_whisper_available()}


# =====================================================
# 16. 时间线（Phase 2）— 多轨编辑
# -------------------------------------------------
# 路由:
#   POST   /projects/{id}/timeline/init              初始化时间线（从分镜自动生成）
#   GET    /projects/{id}/timeline/clips             列出所有片段（可按轨道过滤）
#   POST   /projects/{id}/timeline/clips             创建片段
#   PATCH  /projects/{id}/timeline/clips/{cid}       更新片段
#   DELETE /projects/{id}/timeline/clips/{cid}       删除片段
#   GET    /projects/{id}/timeline/data              获取完整时间线数据
#   PATCH  /projects/{id}/timeline/data              保存时间线草稿（字幕样式等）
# =====================================================

@router.post(
    "/{project_id}/timeline/init",
    response_model=TimelineDataResponse,
    summary="初始化时间线（从分镜自动生成）",
)
async def init_timeline_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """从分镜数据自动初始化时间线（视频轨 + 音频轨）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    try:
        await init_timeline(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = await get_timeline_data(db, project_id)
    return TimelineDataResponse(**data)


@router.get(
    "/{project_id}/timeline/clips",
    response_model=List[TimelineClipResponse],
    summary="列出时间线片段",
)
async def list_timeline_clips_api(
    project_id: int,
    track_type: Optional[str] = Query(None, description="按轨道过滤: video/audio/subtitle"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clips = await list_timeline_clips(db, project_id, track_type=track_type)
    return [TimelineClipResponse.model_validate(c) for c in clips]


@router.post(
    "/{project_id}/timeline/clips",
    response_model=TimelineClipResponse,
    summary="创建时间线片段",
)
async def create_timeline_clip_api(
    project_id: int,
    data: TimelineClipCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clip = await create_timeline_clip(db, project_id, data.model_dump(exclude_none=True))
    return clip


@router.patch(
    "/{project_id}/timeline/clips/{clip_id}",
    response_model=TimelineClipResponse,
    summary="更新时间线片段",
)
async def update_timeline_clip_api(
    project_id: int,
    clip_id: int,
    data: TimelineClipUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clip = await update_timeline_clip(
        db, project_id, clip_id, data.model_dump(exclude_none=True)
    )
    if not clip:
        raise HTTPException(status_code=404, detail="时间线片段不存在")
    return clip


@router.delete(
    "/{project_id}/timeline/clips/{clip_id}",
    summary="删除时间线片段",
)
async def delete_timeline_clip_api(
    project_id: int,
    clip_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_timeline_clip(db, project_id, clip_id)
    if not ok:
        raise HTTPException(status_code=404, detail="时间线片段不存在")
    return {"success": ok}


@router.post(
    "/{project_id}/timeline/clips/{clip_id}/split",
    summary="分割时间线片段",
)
async def split_timeline_clip_api(
    project_id: int,
    clip_id: int,
    split_time: float = Query(..., description="分割点（项目时间线上的绝对时间，秒）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    在指定时间点分割时间线片段（Ctrl+K）

    原片段保留 [start_time, split_time]，新片段承担 [split_time, end_time]。
    """
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    result = await split_timeline_clip(db, project_id, clip_id, split_time)
    if not result:
        raise HTTPException(status_code=400, detail="分割点不在片段范围内")
    return result


@router.delete(
    "/{project_id}/timeline/clips/{clip_id}/ripple",
    summary="波纹删除时间线片段",
)
async def ripple_delete_timeline_clip_api(
    project_id: int,
    clip_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    波纹删除：删除片段后，同轨后续片段自动前移填补空隙

    普通删除留空隙，波纹删除自动收紧。
    """
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    result = await ripple_delete_timeline_clip(db, project_id, clip_id)
    if not result:
        raise HTTPException(status_code=404, detail="时间线片段不存在")
    return result


@router.get(
    "/{project_id}/timeline/data",
    response_model=TimelineDataResponse,
    summary="获取完整时间线数据",
)
async def get_timeline_data_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    data = await get_timeline_data(db, project_id)
    return TimelineDataResponse(**data)


@router.patch(
    "/{project_id}/timeline/data",
    response_model=TimelineDataResponse,
    summary="保存时间线草稿数据",
)
async def save_timeline_data_api(
    project_id: int,
    data: TimelineDataUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """保存时间线草稿（字幕样式、轨道折叠状态等）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    await save_timeline_data(
        db, project_id,
        subtitle_style=data.subtitle_style,
        draft=data.draft,
    )
    refreshed = await get_timeline_data(db, project_id)
    return TimelineDataResponse(**refreshed)


# =====================================================
# 17. BGM 库（Phase 2）— 内置背景音乐
# -------------------------------------------------
# 路由:
#   GET  /projects/{id}/bgms        BGM 列表（可按情绪过滤）
#   GET  /projects/{id}/bgms/moods  情绪分类列表
# =====================================================

@router.get(
    "/{project_id}/bgms",
    summary="BGM 内置库列表",
)
async def list_bgms_api(
    project_id: int,
    mood: Optional[str] = Query(None, description="按情绪过滤: calm/corporate/dramatic/uplifting/sad"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """BGM 内置库列表（available 字段标识文件是否就绪）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return list_bgm_library(mood=mood)


@router.get(
    "/{project_id}/bgms/moods",
    summary="BGM 情绪分类列表",
)
async def list_bgm_moods_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return {"moods": list_bgm_moods()}


@router.get(
    "/{project_id}/bgms/{bgm_id}/file",
    summary="BGM 文件 HTTP URL（供前端预览/拖拽使用）",
)
async def get_bgm_file_api(
    project_id: int,
    bgm_id: str,
    current_user: User = Depends(get_current_user),
):
    """暴露 BGM 文件 HTTP URL（FileResponse）"""
    path = get_bgm_path(bgm_id)
    if not path:
        raise HTTPException(status_code=404, detail="BGM 文件不存在")
    return FileResponse(path, media_type="audio/mpeg")


# =====================================================
# 18. 素材库（Phase 2 增强）
# -------------------------------------------------
# 路由:
#   GET  /projects/{id}/media-library   聚合四类素材
# =====================================================

@router.get(
    "/{project_id}/media-library",
    response_model=MediaLibraryResponse,
    summary="项目素材库（4 类素材聚合）",
)
async def get_media_library_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """聚合项目下所有可拖拽到时间线的素材（视频/音频/帧图/BGM）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await get_media_library(db, project_id)


# =====================================================
# 19. 标记 Markers（Phase 2 增强）
# -------------------------------------------------
# 路由:
#   GET    /projects/{id}/markers        列出标记
#   POST   /projects/{id}/markers        创建标记
#   DELETE /projects/{id}/markers/{mid}  删除标记
# =====================================================

@router.get(
    "/{project_id}/markers",
    response_model=List[MarkerResponse],
    summary="列出项目标记",
)
async def list_markers_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_project_markers(db, project_id)


@router.post(
    "/{project_id}/markers",
    response_model=MarkerResponse,
    status_code=201,
    summary="创建标记",
)
async def create_marker_api(
    project_id: int,
    data: MarkerCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await create_project_marker(
        db, project_id,
        time=data.time, name=data.name, color=data.color,
    )


@router.delete(
    "/{project_id}/markers/{marker_id}",
    summary="删除标记",
)
async def delete_marker_api(
    project_id: int,
    marker_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_project_marker(db, project_id, marker_id)
    if not ok:
        raise HTTPException(status_code=404, detail="标记不存在")
    return {"status": "ok", "message": "标记已删除"}

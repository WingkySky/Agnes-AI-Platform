# =====================================================
# 分镜配音服务 — TTS 生成 + 音色分配 + 多版本管理（Phase 2）
#
# 核心能力:
#   1. generate_audio: 单个分镜 TTS 生成（自动分配音色或指定音色）
#   2. batch_generate_audios: 批量 TTS 生成（并行执行）
#   3. upload_audio: 用户上传音频替代 TTS
#   4. set_active_audio: 设为采用版
#   5. assign_character_voice: 为角色固定音色（同角色同声音）
#
# 音色分配策略（参考 LingGuo-Drama）:
#   - 优先使用角色已分配的音色（project_character_voices）
#   - 未分配时按 role_type 推断：main→narrator_male/female，supporting→young_male/female
#   - 旁白（无角色）使用 default_narrator
#
# 可插拔 TTS provider:
#   - call_tts_provider（services/media/tts_provider.py 公共域）当前实现为 Edge TTS（免费直连）
#   - 后续可接入 Agnes 自有 TTS 或第三方（阿里云 / 字节火山 / ElevenLabs）
# =====================================================

import logging
from typing import Optional, List

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotAudio,
    ProjectShotCharacter,
    ProjectCharacter,
    ProjectCharacterVoice,
)
from app.services.media.tts_provider import BUILTIN_VOICES, call_tts_provider
from app.services.project.sse_manager import project_sse_manager

logger = logging.getLogger("agnes_platform.project.audio")


# =====================================================
# 内部工具
# =====================================================

async def _next_audio_version(db: AsyncSession, shot_id: int) -> int:
    """计算分镜音频的下一个版本号"""
    result = await db.execute(
        select(func.max(ProjectShotAudio.version)).where(
            ProjectShotAudio.shot_id == shot_id
        )
    )
    cur = result.scalar()
    return (cur or 0) + 1


def _infer_voice_by_role(role_type: str, description: str = "") -> str:
    """根据角色类型和描述推断音色"""
    desc = (description or "").lower()
    if "女" in desc or "female" in desc or "girl" in desc:
        return "young_female_zh" if role_type == "main" else "narrator_female_zh"
    if "男" in desc or "male" in desc or "boy" in desc:
        return "young_male_zh" if role_type == "main" else "narrator_male_zh"
    # 默认男声
    return "narrator_male_zh"


def _get_voice_name(voice_id: str) -> Optional[str]:
    """根据 voice_id 查内置音色库名称"""
    for v in BUILTIN_VOICES:
        if v["voice_id"] == voice_id:
            return v["name"]
    return None


async def _resolve_voice_for_shot(
    db: AsyncSession, shot: ProjectShot, character_id: Optional[int] = None
) -> tuple:
    """
    解析分镜的音色（同角色同声音策略）

    返回: (voice_id, voice_name, character_id)
    """
    # 1. 优先使用角色已分配的音色
    if character_id:
        assignment = (await db.execute(
            select(ProjectCharacterVoice).where(
                ProjectCharacterVoice.character_id == character_id
            )
        )).scalar_one_or_none()
        if assignment:
            return assignment.voice_id, assignment.voice_name, character_id

    # 2. 取分镜绑定的主角色的 role_type 推断音色
    if not character_id:
        char_links = (await db.execute(
            select(ProjectShotCharacter)
            .where(ProjectShotCharacter.shot_id == shot.id)
            .order_by(ProjectShotCharacter.sort_order)
        )).scalars().all()
        if char_links:
            # 取第一个角色（按 sort_order）
            first_char = (await db.execute(
                select(ProjectCharacter).where(ProjectCharacter.id == char_links[0].character_id)
            )).scalar_one_or_none()
            if first_char:
                character_id = first_char.id
                # 查已分配音色
                assignment = (await db.execute(
                    select(ProjectCharacterVoice).where(
                        ProjectCharacterVoice.character_id == character_id
                    )
                )).scalar_one_or_none()
                if assignment:
                    return assignment.voice_id, assignment.voice_name, character_id
                # 按 role_type 推断
                voice_id = _infer_voice_by_role(first_char.role_type, first_char.description or "")
                return voice_id, _get_voice_name(voice_id), character_id

    # 3. 无角色 → 默认旁白
    return "narrator_male_zh", "男声旁白", None


# =====================================================
# 配音生成
# =====================================================

async def generate_audio(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    voice_id: Optional[str] = None,
    character_id: Optional[int] = None,
    text: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> ProjectShotAudio:
    """
    为分镜生成 TTS 配音

    1. 解析音色（同角色同声音）
    2. 取对白文本（shot.dialogue 或显式传入）
    3. 调用 TTS provider 生成音频
    4. 创建新版本记录（is_active=False）
    5. 推送 SSE
    """
    shot = (await db.execute(
        select(ProjectShot).where(ProjectShot.id == shot_id)
    )).scalar_one_or_none()
    if not shot:
        raise ValueError(f"分镜 {shot_id} 不存在")

    # 解析音色
    if not voice_id:
        voice_id, voice_name, resolved_char_id = await _resolve_voice_for_shot(db, shot, character_id)
    else:
        voice_name = _get_voice_name(voice_id)
        resolved_char_id = character_id

    if not voice_id:
        raise ValueError("无法解析音色，请显式指定 voice_id")

    # 解析文本
    tts_text = text or shot.dialogue
    if not tts_text:
        raise ValueError("分镜无对白文本，无法生成配音")

    # 调用 TTS provider 生成音频
    audio_url, duration_ms, file_size = await call_tts_provider(
        text=tts_text,
        voice_id=voice_id,
        model=model,
        provider=provider,
        save_folder=f"projects/{shot.project_id}/shots/{shot.id}/audios",
    )

    # 创建新版本记录
    next_version = await _next_audio_version(db, shot_id)
    audio = ProjectShotAudio(
        shot_id=shot_id,
        version=next_version,
        is_active=False,  # 用户手动切换
        is_manual=False,
        file_url=audio_url,
        text=tts_text,
        voice_id=voice_id,
        voice_name=voice_name,
        character_id=resolved_char_id,
        provider=provider or "edge-tts",
        model=model,
        duration_ms=duration_ms,
        file_size=file_size,
        created_by="ai",
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)

    await project_sse_manager.push(shot.project_id, "tts_completed", {
        "shot_id": shot_id,
        "version": next_version,
        "audio_id": audio.id,
        "duration_ms": duration_ms,
    })
    return audio


async def batch_generate_audios(
    db: AsyncSession,
    shot_ids: List[int],
    user_id: int,
    voice_id: Optional[str] = None,
) -> List[int]:
    """
    批量 TTS 生成 — 并行执行多个分镜的 TTS 任务

    返回成功生成的 audio_id 列表（失败的分镜会记录日志但不中断整体流程）
    """
    audios: List[int] = []
    for shot_id in shot_ids:
        try:
            audio = await generate_audio(db, shot_id, user_id, voice_id=voice_id)
            audios.append(audio.id)
        except Exception as e:
            logger.error(f"[批量 TTS] 分镜 {shot_id} 生成失败: {e}")
    return audios


async def upload_audio(
    db: AsyncSession, shot_id: int, user_id: int, file_url: str,
    duration_ms: Optional[int] = None, file_size: Optional[int] = None,
) -> ProjectShotAudio:
    """用户上传音频替代 TTS"""
    shot = (await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))).scalar_one_or_none()
    if not shot:
        raise ValueError(f"分镜 {shot_id} 不存在")

    next_version = await _next_audio_version(db, shot_id)
    audio = ProjectShotAudio(
        shot_id=shot_id,
        version=next_version,
        is_active=False,
        is_manual=True,
        file_url=file_url,
        text=shot.dialogue,
        created_by="manual",
        duration_ms=duration_ms,
        file_size=file_size,
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)
    return audio


async def set_active_audio(db: AsyncSession, shot_id: int, version_id: int) -> ProjectShotAudio:
    """设置采用版音频"""
    # 1. 取消同分镜其他版本的 is_active
    await db.execute(
        update(ProjectShotAudio)
        .where(ProjectShotAudio.shot_id == shot_id, ProjectShotAudio.is_active == True)  # noqa: E712
        .values(is_active=False)
    )
    # 2. 设置目标版本 active
    audio = (await db.execute(
        select(ProjectShotAudio).where(ProjectShotAudio.id == version_id)
    )).scalar_one_or_none()
    if not audio:
        raise ValueError(f"音频版本 {version_id} 不存在")
    audio.is_active = True
    # 3. 更新分镜的 active_audio_id 指针
    shot = (await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))).scalar_one_or_none()
    if shot:
        shot.active_audio_id = audio.id
    await db.commit()
    await db.refresh(audio)

    await project_sse_manager.push(shot.project_id if shot else 0, "audio_activated", {
        "shot_id": shot_id, "version_id": version_id
    })
    return audio


async def list_audios(db: AsyncSession, shot_id: int) -> List[ProjectShotAudio]:
    """列出分镜的所有音频版本"""
    result = await db.execute(
        select(ProjectShotAudio)
        .where(ProjectShotAudio.shot_id == shot_id)
        .order_by(ProjectShotAudio.version)
    )
    return result.scalars().all()


async def delete_audio(db: AsyncSession, shot_id: int, version_id: int) -> bool:
    """删除音频版本（不允许删除当前激活版）"""
    audio = (await db.execute(
        select(ProjectShotAudio).where(ProjectShotAudio.id == version_id)
    )).scalar_one_or_none()
    if not audio:
        return False
    if audio.is_active:
        return False  # 不允许删除激活版
    await db.delete(audio)
    await db.commit()
    return True


# =====================================================
# 角色音色映射
# =====================================================

async def assign_character_voice(
    db: AsyncSession, project_id: int, character_id: int,
    voice_id: str, voice_name: Optional[str] = None,
) -> ProjectCharacterVoice:
    """为角色分配音色（同角色同声音，upsert）"""
    existing = (await db.execute(
        select(ProjectCharacterVoice).where(
            ProjectCharacterVoice.project_id == project_id,
            ProjectCharacterVoice.character_id == character_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.voice_id = voice_id
        existing.voice_name = voice_name or _get_voice_name(voice_id)
        await db.commit()
        await db.refresh(existing)
        return existing

    assignment = ProjectCharacterVoice(
        project_id=project_id,
        character_id=character_id,
        voice_id=voice_id,
        voice_name=voice_name or _get_voice_name(voice_id),
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_character_voices(db: AsyncSession, project_id: int) -> List[ProjectCharacterVoice]:
    """列出项目内所有角色音色映射"""
    result = await db.execute(
        select(ProjectCharacterVoice).where(ProjectCharacterVoice.project_id == project_id)
    )
    return result.scalars().all()

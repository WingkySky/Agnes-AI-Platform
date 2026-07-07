/* =====================================================
 * 项目制创作相关 API 封装
 * - 项目 CRUD / 向导创建 / SSE 订阅 URL
 * - 剧本 CRUD + 重生成
 * - 角色/场景/道具 CRUD + 生成 + 上传 + 版本
 * - 分镜 CRUD + 绑定 + 重排
 * - 帧图/视频 多版本生成与上传
 * - 资产桥接 / 画布 / 合成
 * ===================================================== */

import client from './client'
import type {
  Project,
  ProjectCreateRequest,
  ProjectUpdateRequest,
  ActiveViewUpdateRequest,
  ProjectListParams,
  ProjectListResult,
  ProjectScript,
  ScriptCreateRequest,
  ScriptUpdateRequest,
  ScriptRegenerateRequest,
  ProjectCharacter,
  CharacterCreateRequest,
  CharacterUpdateRequest,
  CharacterGenerateImageRequest,
  BatchGenerateCharactersRequest,
  ProjectScene,
  SceneCreateRequest,
  SceneUpdateRequest,
  ProjectProp,
  PropCreateRequest,
  PropUpdateRequest,
  ProjectShot,
  ShotCreateRequest,
  ShotUpdateRequest,
  ShotReorderRequest,
  ShotBindEntityRequest,
  ProjectFrameImage,
  GenerateFrameImageRequest,
  BatchGenerateFrameImagesRequest,
  ProjectVideo,
  GenerateVideoRequest,
  ProjectEntityAsset,
  SetActiveVersionRequest,
  ImportAssetRequest,
  PromoteAssetRequest,
  CanvasDataUpdate,
  CanvasLayoutResponse,
  MergeStatusResponse,
  WizardCreateRequest,
  WizardResumeRequest,
  EntityType,
  // Phase 2
  ProjectShotAudio,
  GenerateTTSRequest,
  BatchGenerateTTSRequest,
  VoiceOption,
  CharacterVoice,
  AssignCharacterVoiceRequest,
  SubtitleStyle,
  GenerateSubtitleRequest,
  GenerateSubtitleAdvancedRequest,
  SubtitleGenerateResult,
  TimelineClip,
  TimelineClipCreateRequest,
  TimelineClipUpdateRequest,
  TimelineDataResponse,
  TimelineDataUpdateRequest,
  TimelineTrackType,
  BGMItem,
  BGMMood,
  MergeAdvancedRequest,
  // Phase 2 增强
  MediaLibraryItem,
  MediaLibraryResponse,
  ProjectMarker,
  MarkerCreateRequest,
} from '@/types/project'

// =====================================================
// 项目主表 API
// =====================================================

export function listProjects(params: ProjectListParams = {}): Promise<ProjectListResult> {
  return client.get('/api/projects', { params })
}

export function getProject(id: number): Promise<Project> {
  return client.get(`/api/projects/${id}`)
}

export function createProject(data: ProjectCreateRequest): Promise<Project> {
  return client.post('/api/projects', data)
}

export function updateProject(id: number, data: ProjectUpdateRequest): Promise<Project> {
  return client.patch(`/api/projects/${id}`, data)
}

export function deleteProject(id: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${id}`)
}

export function archiveProject(id: number): Promise<Project> {
  return client.post(`/api/projects/${id}/archive`)
}

export function updateActiveView(id: number, data: ActiveViewUpdateRequest): Promise<Project> {
  return client.patch(`/api/projects/${id}/active-view`, data)
}

/** 自动从分镜帧图中选取封面 */
export function rebuildProjectCover(id: number): Promise<Project> {
  return client.post(`/api/projects/${id}/rebuild-cover`)
}

/** 指定帧图设为封面 */
export function setProjectCover(id: number, frameImageId: number): Promise<Project> {
  return client.post(`/api/projects/${id}/set-cover`, { frame_image_id: frameImageId })
}

// =====================================================
// 项目 SSE 订阅 URL
// =====================================================

/**
 * 构造项目 SSE 订阅 URL（带 token query，兼容 EventSource）
 */
export function buildProjectSSEUrl(projectId: number, token: string | null): string {
  const baseUrl: string = import.meta.env?.VITE_API_BASE_URL || ''
  const path = `/api/projects/${projectId}/events`
  const url = `${baseUrl}${path}`
  if (token) {
    return `${url}?token=${encodeURIComponent(token)}`
  }
  return url
}

// =====================================================
// 向导（Wizard）API
// =====================================================

export function createWizardProject(data: WizardCreateRequest): Promise<Project> {
  return client.post('/api/projects/wizard', data)
}

export function resumeWizard(projectId: number, data: WizardResumeRequest): Promise<{ status: string; message: string }> {
  return client.post(`/api/projects/${projectId}/wizard/resume`, data)
}

// =====================================================
// 剧本 API
// =====================================================

export function listScripts(projectId: number): Promise<ProjectScript[]> {
  return client.get(`/api/projects/${projectId}/scripts`)
}

export function getScript(projectId: number, scriptId: number): Promise<ProjectScript> {
  return client.get(`/api/projects/${projectId}/scripts/${scriptId}`)
}

export function createScript(projectId: number, data: ScriptCreateRequest): Promise<ProjectScript> {
  return client.post(`/api/projects/${projectId}/scripts`, data)
}

export function updateScript(projectId: number, scriptId: number, data: ScriptUpdateRequest): Promise<ProjectScript> {
  return client.patch(`/api/projects/${projectId}/scripts/${scriptId}`, data)
}

export function deleteScript(projectId: number, scriptId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/scripts/${scriptId}`)
}

export function regenerateScript(projectId: number, scriptId: number, data: ScriptRegenerateRequest): Promise<ProjectScript> {
  return client.post(`/api/projects/${projectId}/scripts/${scriptId}/regenerate`, data)
}

// =====================================================
// 实体通用 API（角色/场景/道具）
// =====================================================

interface EntityEndpoints {
  list: (projectId: number, scriptId?: number) => Promise<any[]>
  get: (projectId: number, id: number) => Promise<any>
  create: (projectId: number, data: any) => Promise<any>
  update: (projectId: number, id: number, data: any) => Promise<any>
  delete: (projectId: number, id: number) => Promise<{ status: string; message: string }>
  reorder: (projectId: number, ids: number[]) => Promise<any>
  generateImage: (projectId: number, id: number, data: any) => Promise<any>
  batchGenerate: (projectId: number, data: any) => Promise<any>
  uploadImage: (projectId: number, id: number, file: File) => Promise<any>
  listVersions: (projectId: number, id: number) => Promise<ProjectEntityAsset[]>
  setActiveVersion: (projectId: number, id: number, data: SetActiveVersionRequest) => Promise<any>
  deleteVersion: (projectId: number, id: number, versionId: number) => Promise<{ status: string; message: string }>
  extractFromScript: (projectId: number, scriptId: number) => Promise<any>
  /** 跨集复制：将实体复制到目标剧本（集） */
  copyTo: (projectId: number, entityId: number, targetScriptId: number) => Promise<any>
}

/** 构造某实体类型对应的 API 端点集合 */
function buildEntityApi(prefix: string): EntityEndpoints {
  return {
    // list 支持按 scriptId 过滤（集数隔离）
    list: (projectId: number, scriptId?: number) =>
      client.get(`/api/projects/${projectId}/${prefix}`, {
        params: scriptId !== undefined ? { script_id: scriptId } : undefined,
      }),
    get: (projectId: number, id: number) => client.get(`/api/projects/${projectId}/${prefix}/${id}`),
    create: (projectId: number, data: any) => client.post(`/api/projects/${projectId}/${prefix}`, data),
    update: (projectId: number, id: number, data: any) => client.patch(`/api/projects/${projectId}/${prefix}/${id}`, data),
    delete: (projectId: number, id: number) => client.delete(`/api/projects/${projectId}/${prefix}/${id}`),
    reorder: (projectId: number, ids: number[]) => client.patch(`/api/projects/${projectId}/${prefix}/reorder`, { ids }),
    generateImage: (projectId: number, id: number, data: any) =>
      client.post(`/api/projects/${projectId}/${prefix}/${id}/generate-image`, data),
    batchGenerate: (projectId: number, data: any) =>
      client.post(`/api/projects/${projectId}/${prefix}/batch-generate`, data),
    uploadImage: (projectId: number, id: number, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return client.post(`/api/projects/${projectId}/${prefix}/${id}/upload-image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    },
    listVersions: (projectId: number, id: number) =>
      client.get(`/api/projects/${projectId}/${prefix}/${id}/versions`),
    setActiveVersion: (projectId: number, id: number, data: SetActiveVersionRequest) =>
      client.post(`/api/projects/${projectId}/${prefix}/${id}/set-active`, data),
    deleteVersion: (projectId: number, id: number, versionId: number) =>
      client.delete(`/api/projects/${projectId}/${prefix}/${id}/versions/${versionId}`),
    // extractFromScript 真正发送 script_id（修复原来 _scriptId 丢弃的 bug）
    extractFromScript: (projectId: number, scriptId: number) =>
      client.post(`/api/projects/${projectId}/${prefix}/extract-from-script`, { script_id: scriptId }),
    // copyTo 跨集复制：将实体复制到目标剧本
    copyTo: (projectId: number, entityId: number, targetScriptId: number) =>
      client.post(`/api/projects/${projectId}/${prefix}/${entityId}/copy-to`, {
        target_script_id: targetScriptId,
      }),
  }
}

// =====================================================
// 角色 API
// =====================================================

export const charactersApi = buildEntityApi('characters') as EntityEndpoints & {
  list: (projectId: number, scriptId?: number) => Promise<ProjectCharacter[]>
  get: (projectId: number, id: number) => Promise<ProjectCharacter>
  create: (projectId: number, data: CharacterCreateRequest) => Promise<ProjectCharacter>
  update: (projectId: number, id: number, data: CharacterUpdateRequest) => Promise<ProjectCharacter>
  generateImage: (projectId: number, id: number, data: CharacterGenerateImageRequest) => Promise<ProjectCharacter>
  batchGenerate: (projectId: number, data: BatchGenerateCharactersRequest) => Promise<any>
}

// =====================================================
// 场景 API
// =====================================================

export const scenesApi = buildEntityApi('scenes') as EntityEndpoints & {
  list: (projectId: number, scriptId?: number) => Promise<ProjectScene[]>
  get: (projectId: number, id: number) => Promise<ProjectScene>
  create: (projectId: number, data: SceneCreateRequest) => Promise<ProjectScene>
  update: (projectId: number, id: number, data: SceneUpdateRequest) => Promise<ProjectScene>
}

// =====================================================
// 道具 API
// =====================================================

export const propsApi = buildEntityApi('props') as EntityEndpoints & {
  list: (projectId: number, scriptId?: number) => Promise<ProjectProp[]>
  get: (projectId: number, id: number) => Promise<ProjectProp>
  create: (projectId: number, data: PropCreateRequest) => Promise<ProjectProp>
  update: (projectId: number, id: number, data: PropUpdateRequest) => Promise<ProjectProp>
}

// =====================================================
// 分镜 API
// =====================================================

export function listShots(projectId: number, scriptId?: number): Promise<ProjectShot[]> {
  return client.get(`/api/projects/${projectId}/shots`, {
    params: scriptId !== undefined ? { script_id: scriptId } : undefined,
  })
}

export function getShot(projectId: number, shotId: number): Promise<ProjectShot> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}`)
}

export function createShot(projectId: number, data: ShotCreateRequest): Promise<ProjectShot> {
  return client.post(`/api/projects/${projectId}/shots`, data)
}

export function updateShot(projectId: number, shotId: number, data: ShotUpdateRequest): Promise<ProjectShot> {
  return client.patch(`/api/projects/${projectId}/shots/${shotId}`, data)
}

export function deleteShot(projectId: number, shotId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}`)
}

export function reorderShots(projectId: number, data: ShotReorderRequest): Promise<any> {
  return client.patch(`/api/projects/${projectId}/shots/reorder`, data)
}

export function generateFramePrompt(projectId: number, shotId: number): Promise<ProjectShot> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/generate-frame-prompt`)
}

// splitShotsFromScript 真正发送 script_id（修复原来 _scriptId 丢弃的 bug）
export function splitShotsFromScript(projectId: number, scriptId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/split`, { script_id: scriptId })
}

export function bindCharacterToShot(projectId: number, shotId: number, data: ShotBindEntityRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/bind-character`, data)
}

export function unbindCharacterFromShot(projectId: number, shotId: number, characterId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/unbind-character`, { entity_id: characterId })
}

export function bindPropToShot(projectId: number, shotId: number, data: ShotBindEntityRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/bind-prop`, data)
}

export function unbindPropFromShot(projectId: number, shotId: number, propId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/unbind-prop`, { entity_id: propId })
}

// =====================================================
// 帧图 API
// =====================================================

export function listFrameImages(projectId: number, shotId: number): Promise<ProjectFrameImage[]> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}/frame-images`)
}

export function generateFrameImage(projectId: number, shotId: number, data: GenerateFrameImageRequest): Promise<ProjectFrameImage> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/frame-images/generate`, data)
}

export function batchGenerateFrameImages(projectId: number, data: BatchGenerateFrameImagesRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/frame-images/batch-generate`, data)
}

export function uploadFrameImage(projectId: number, shotId: number, file: File): Promise<ProjectFrameImage> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post(`/api/projects/${projectId}/shots/${shotId}/frame-images/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function setActiveFrameImage(projectId: number, shotId: number, versionId: number): Promise<ProjectFrameImage> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/frame-images/${versionId}/set-active`)
}

export function deleteFrameImage(projectId: number, shotId: number, frameImageId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/frame-images/${frameImageId}`)
}

// =====================================================
// 视频 API
// =====================================================

export function listVideos(projectId: number, shotId: number): Promise<ProjectVideo[]> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}/videos`)
}

export function generateVideo(projectId: number, shotId: number, data: GenerateVideoRequest): Promise<ProjectVideo> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/videos/generate`, data)
}

export function uploadVideo(projectId: number, shotId: number, file: File): Promise<ProjectVideo> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post(`/api/projects/${projectId}/shots/${shotId}/videos/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function setActiveVideo(projectId: number, shotId: number, versionId: number): Promise<ProjectVideo> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/videos/${versionId}/set-active`)
}

export function deleteVideo(projectId: number, shotId: number, videoId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/videos/${videoId}`)
}

// =====================================================
// 资产桥接 API
// =====================================================

export function importAssetToProject(projectId: number, entityType: EntityType, data: ImportAssetRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/entities/${entityType}/import-asset`, data)
}

export function promoteEntityToAsset(projectId: number, entityType: EntityType, entityId: number, data: PromoteAssetRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/entities/${entityType}/${entityId}/promote-asset`, data)
}

// =====================================================
// 画布 API
// =====================================================

export function getCanvasLayout(projectId: number): Promise<CanvasLayoutResponse> {
  return client.get(`/api/projects/${projectId}/canvas`)
}

export function saveCanvasLayout(projectId: number, data: CanvasDataUpdate): Promise<CanvasLayoutResponse> {
  return client.patch(`/api/projects/${projectId}/canvas`, data)
}

// =====================================================
// 合成 API
// =====================================================

export function mergeProject(projectId: number): Promise<{ status: string; message: string }> {
  return client.post(`/api/projects/${projectId}/merge`, {})
}

export function getMergeStatus(projectId: number): Promise<MergeStatusResponse> {
  return client.get(`/api/projects/${projectId}/merge/status`)
}

// =====================================================
// 实体类型 → API 映射（动态调度）
// =====================================================

export function getEntityApi(entityType: EntityType): EntityEndpoints {
  switch (entityType) {
    case 'character':
      return charactersApi
    case 'scene':
      return scenesApi
    case 'prop':
      return propsApi
  }
}

// =====================================================
// Phase 2 API — 配音 / 音色 / 字幕 / 时间线 / BGM / 高级合成
// =====================================================

// ---------- 配音（多版本） ----------

export function listAudios(projectId: number, shotId: number): Promise<ProjectShotAudio[]> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}/audios`)
}

export function generateTTS(
  projectId: number,
  shotId: number,
  data: GenerateTTSRequest,
): Promise<ProjectShotAudio> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/audios/generate`, data)
}

export function batchGenerateTTS(
  projectId: number,
  data: BatchGenerateTTSRequest,
): Promise<{ audio_ids: number[]; success_count: number }> {
  return client.post(`/api/projects/${projectId}/shots/audios/batch-generate`, data)
}

export function uploadAudio(projectId: number, shotId: number, file: File): Promise<ProjectShotAudio> {
  const form = new FormData()
  form.append('file', file)
  return client.post(
    `/api/projects/${projectId}/shots/${shotId}/audios/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export function setActiveAudio(
  projectId: number,
  shotId: number,
  versionId: number,
): Promise<ProjectShotAudio> {
  return client.post(
    `/api/projects/${projectId}/shots/${shotId}/audios/${versionId}/set-active`,
    {},
  )
}

export function deleteAudio(
  projectId: number,
  shotId: number,
  versionId: number,
): Promise<{ success: boolean }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/audios/${versionId}`)
}

// ---------- 音色 ----------

export function listBuiltinVoices(projectId: number): Promise<VoiceOption[]> {
  return client.get(`/api/projects/${projectId}/voices/builtin`)
}

export function listCharacterVoices(projectId: number): Promise<CharacterVoice[]> {
  return client.get(`/api/projects/${projectId}/character-voices`)
}

export function assignCharacterVoice(
  projectId: number,
  characterId: number,
  data: AssignCharacterVoiceRequest,
): Promise<CharacterVoice> {
  return client.post(
    `/api/projects/${projectId}/character-voices/${characterId}`,
    data,
  )
}

// ---------- 字幕 ----------

export function generateSubtitles(
  projectId: number,
  data: GenerateSubtitleRequest = {},
): Promise<SubtitleGenerateResult> {
  return client.post(`/api/projects/${projectId}/subtitles/generate`, data)
}

export function generateSubtitlesWithWhisper(
  projectId: number,
  data: GenerateSubtitleAdvancedRequest = {},
): Promise<SubtitleGenerateResult> {
  return client.post(`/api/projects/${projectId}/subtitles/generate-whisper`, data)
}

export function listSubtitleClips(projectId: number): Promise<TimelineClip[]> {
  return client.get(`/api/projects/${projectId}/subtitles/clips`)
}

export function getSubtitleStyle(projectId: number): Promise<SubtitleStyle> {
  return client.get(`/api/projects/${projectId}/subtitles/style`)
}

export function updateSubtitleStyle(
  projectId: number,
  data: SubtitleStyle,
): Promise<SubtitleStyle> {
  return client.patch(`/api/projects/${projectId}/subtitles/style`, data)
}

export function checkWhisperAvailable(
  projectId: number,
): Promise<{ available: boolean }> {
  return client.get(`/api/projects/${projectId}/subtitles/whisper-available`)
}

// ---------- 时间线 ----------

export function initTimeline(projectId: number): Promise<TimelineDataResponse> {
  return client.post(`/api/projects/${projectId}/timeline/init`, {})
}

export function listTimelineClips(
  projectId: number,
  trackType?: TimelineTrackType,
): Promise<TimelineClip[]> {
  const params = trackType ? { track_type: trackType } : {}
  return client.get(`/api/projects/${projectId}/timeline/clips`, { params })
}

export function createTimelineClip(
  projectId: number,
  data: TimelineClipCreateRequest,
): Promise<TimelineClip> {
  return client.post(`/api/projects/${projectId}/timeline/clips`, data)
}

export function updateTimelineClip(
  projectId: number,
  clipId: number,
  data: TimelineClipUpdateRequest,
): Promise<TimelineClip> {
  return client.patch(`/api/projects/${projectId}/timeline/clips/${clipId}`, data)
}

export function deleteTimelineClip(
  projectId: number,
  clipId: number,
): Promise<{ success: boolean }> {
  return client.delete(`/api/projects/${projectId}/timeline/clips/${clipId}`)
}

/** 分割时间线片段（Ctrl+K） */
export function splitTimelineClip(
  projectId: number,
  clipId: number,
  splitTime: number,
): Promise<{ original: { id: number; start_time: number; duration: number; trim_start: number }; new: { id: number; start_time: number; duration: number; trim_start: number } }> {
  return client.post(`/api/projects/${projectId}/timeline/clips/${clipId}/split`, null, {
    params: { split_time: splitTime },
  })
}

/** 波纹删除：删除片段后同轨后续片段自动前移 */
export function rippleDeleteTimelineClip(
  projectId: number,
  clipId: number,
): Promise<{ deleted_clip_id: number; shifted_clips: Array<{ clip_id: number; new_start_time: number }>; shift_duration: number }> {
  return client.delete(`/api/projects/${projectId}/timeline/clips/${clipId}/ripple`)
}

export function getTimelineData(projectId: number): Promise<TimelineDataResponse> {
  return client.get(`/api/projects/${projectId}/timeline/data`)
}

export function saveTimelineData(
  projectId: number,
  data: TimelineDataUpdateRequest,
): Promise<TimelineDataResponse> {
  return client.patch(`/api/projects/${projectId}/timeline/data`, data)
}

// ---------- BGM 库 ----------

export function listBgms(projectId: number, mood?: BGMMood): Promise<BGMItem[]> {
  const params = mood ? { mood } : {}
  return client.get(`/api/projects/${projectId}/bgms`, { params })
}

export function listBgmMoods(projectId: number): Promise<{ moods: string[] }> {
  return client.get(`/api/projects/${projectId}/bgms/moods`)
}

// ---------- 高级合成 ----------

export function mergeProjectAdvanced(
  projectId: number,
  data: MergeAdvancedRequest = {},
): Promise<{ status: string }> {
  return client.post(`/api/projects/${projectId}/merge/advanced`, data)
}

// =====================================================
// 素材库 / BGM 文件 / 标记 API（Phase 2 增强）
// =====================================================

/** 获取项目素材库（4 类素材聚合） */
export function getMediaLibrary(projectId: number): Promise<MediaLibraryResponse> {
  return client.get(`/api/projects/${projectId}/media-library`)
}

/** BGM 文件 URL 拼接（供拖拽到时间线使用） */
export function getBgmFileUrl(projectId: number, bgmId: string): string {
  return `/api/projects/${projectId}/bgms/${bgmId}/file`
}

/** 列出项目标记 */
export function listMarkers(projectId: number): Promise<ProjectMarker[]> {
  return client.get(`/api/projects/${projectId}/markers`)
}

/** 创建标记 */
export function createMarker(projectId: number, data: MarkerCreateRequest): Promise<ProjectMarker> {
  return client.post(`/api/projects/${projectId}/markers`, data)
}

/** 删除标记 */
export function deleteMarker(projectId: number, markerId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/markers/${markerId}`)
}

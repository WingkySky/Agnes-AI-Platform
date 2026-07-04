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
  return client.put(`/api/projects/${id}`, data)
}

export function deleteProject(id: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${id}`)
}

export function archiveProject(id: number): Promise<Project> {
  return client.post(`/api/projects/${id}/archive`)
}

export function updateActiveView(id: number, data: ActiveViewUpdateRequest): Promise<Project> {
  return client.put(`/api/projects/${id}/active-view`, data)
}

// =====================================================
// 项目 SSE 订阅 URL
// =====================================================

/**
 * 构造项目 SSE 订阅 URL（带 token query，兼容 EventSource）
 */
export function buildProjectSSEUrl(projectId: number, token: string | null): string {
  const baseUrl: string = (import.meta as any).env?.VITE_API_BASE_URL || ''
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
  return client.put(`/api/projects/${projectId}/scripts/${scriptId}`, data)
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
  list: (projectId: number) => Promise<any[]>
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
}

/** 构造某实体类型对应的 API 端点集合 */
function buildEntityApi(prefix: string): EntityEndpoints {
  return {
    list: (projectId: number) => client.get(`/api/projects/${projectId}/${prefix}`),
    get: (projectId: number, id: number) => client.get(`/api/projects/${projectId}/${prefix}/${id}`),
    create: (projectId: number, data: any) => client.post(`/api/projects/${projectId}/${prefix}`, data),
    update: (projectId: number, id: number, data: any) => client.put(`/api/projects/${projectId}/${prefix}/${id}`, data),
    delete: (projectId: number, id: number) => client.delete(`/api/projects/${projectId}/${prefix}/${id}`),
    reorder: (projectId: number, ids: number[]) => client.post(`/api/projects/${projectId}/${prefix}/reorder`, { ids }),
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
      client.post(`/api/projects/${projectId}/${prefix}/${id}/versions/set-active`, data),
    deleteVersion: (projectId: number, id: number, versionId: number) =>
      client.delete(`/api/projects/${projectId}/${prefix}/${id}/versions/${versionId}`),
    extractFromScript: (projectId: number, scriptId: number) =>
      client.post(`/api/projects/${projectId}/${prefix}/extract-from-script`, { script_id: scriptId }),
  }
}

// =====================================================
// 角色 API
// =====================================================

export const charactersApi = buildEntityApi('characters') as EntityEndpoints & {
  list: (projectId: number) => Promise<ProjectCharacter[]>
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
  list: (projectId: number) => Promise<ProjectScene[]>
  get: (projectId: number, id: number) => Promise<ProjectScene>
  create: (projectId: number, data: SceneCreateRequest) => Promise<ProjectScene>
  update: (projectId: number, id: number, data: SceneUpdateRequest) => Promise<ProjectScene>
}

// =====================================================
// 道具 API
// =====================================================

export const propsApi = buildEntityApi('props') as EntityEndpoints & {
  list: (projectId: number) => Promise<ProjectProp[]>
  get: (projectId: number, id: number) => Promise<ProjectProp>
  create: (projectId: number, data: PropCreateRequest) => Promise<ProjectProp>
  update: (projectId: number, id: number, data: PropUpdateRequest) => Promise<ProjectProp>
}

// =====================================================
// 分镜 API
// =====================================================

export function listShots(projectId: number): Promise<ProjectShot[]> {
  return client.get(`/api/projects/${projectId}/shots`)
}

export function getShot(projectId: number, shotId: number): Promise<ProjectShot> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}`)
}

export function createShot(projectId: number, data: ShotCreateRequest): Promise<ProjectShot> {
  return client.post(`/api/projects/${projectId}/shots`, data)
}

export function updateShot(projectId: number, shotId: number, data: ShotUpdateRequest): Promise<ProjectShot> {
  return client.put(`/api/projects/${projectId}/shots/${shotId}`, data)
}

export function deleteShot(projectId: number, shotId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}`)
}

export function reorderShots(projectId: number, data: ShotReorderRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/reorder`, data)
}

export function generateFramePrompt(projectId: number, shotId: number): Promise<ProjectShot> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/generate-frame-prompt`)
}

export function splitShotsFromScript(projectId: number, scriptId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/split-from-script`, { script_id: scriptId })
}

export function bindCharacterToShot(projectId: number, shotId: number, data: ShotBindEntityRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/characters`, data)
}

export function unbindCharacterFromShot(projectId: number, shotId: number, characterId: number): Promise<any> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/characters/${characterId}`)
}

export function bindPropToShot(projectId: number, shotId: number, data: ShotBindEntityRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/props`, data)
}

export function unbindPropFromShot(projectId: number, shotId: number, propId: number): Promise<any> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/props/${propId}`)
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
  return client.post(`/api/projects/${projectId}/frame-images/batch-generate`, data)
}

export function uploadFrameImage(projectId: number, shotId: number, file: File): Promise<ProjectFrameImage> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post(`/api/projects/${projectId}/shots/${shotId}/frame-images/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function setActiveFrameImage(projectId: number, shotId: number, data: SetActiveVersionRequest): Promise<ProjectFrameImage> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/frame-images/set-active`, data)
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

export function setActiveVideo(projectId: number, shotId: number, data: SetActiveVersionRequest): Promise<ProjectVideo> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/videos/set-active`, data)
}

export function deleteVideo(projectId: number, shotId: number, videoId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/videos/${videoId}`)
}

// =====================================================
// 资产桥接 API
// =====================================================

export function importAssetToProject(projectId: number, data: ImportAssetRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/assets/import`, data)
}

export function promoteEntityToAsset(projectId: number, data: PromoteAssetRequest): Promise<any> {
  return client.post(`/api/projects/${projectId}/assets/promote`, data)
}

// =====================================================
// 画布 API
// =====================================================

export function getCanvasLayout(projectId: number): Promise<CanvasLayoutResponse> {
  return client.get(`/api/projects/${projectId}/canvas`)
}

export function saveCanvasLayout(projectId: number, data: CanvasDataUpdate): Promise<CanvasLayoutResponse> {
  return client.put(`/api/projects/${projectId}/canvas`, data)
}

// =====================================================
// 合成 API
// =====================================================

export function mergeProject(projectId: number): Promise<{ status: string; message: string }> {
  return client.post(`/api/projects/${projectId}/merge`)
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

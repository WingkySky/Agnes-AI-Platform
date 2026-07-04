/* =====================================================
 * 项目制创作状态管理 Store
 * 职责：
 *   - 项目列表（含分页/搜索）
 *   - 当前项目详情（含所有关联实体）
 *   - 项目 CRUD 操作
 *   - 实体 CRUD 代理（角色/场景/道具/剧本/分镜/帧图/视频）
 *   - 当前活动视图（manager / canvas）
 * ===================================================== */

import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import {
  listProjects as apiListProjects,
  getProject as apiGetProject,
  createProject as apiCreateProject,
  updateProject as apiUpdateProject,
  deleteProject as apiDeleteProject,
  archiveProject as apiArchiveProject,
  updateActiveView as apiUpdateActiveView,
  createWizardProject as apiCreateWizardProject,
  resumeWizard as apiResumeWizard,
  listScripts as apiListScripts,
  createScript as apiCreateScript,
  updateScript as apiUpdateScript,
  deleteScript as apiDeleteScript,
  regenerateScript as apiRegenerateScript,
  charactersApi,
  scenesApi,
  propsApi,
  listShots as apiListShots,
  createShot as apiCreateShot,
  updateShot as apiUpdateShot,
  deleteShot as apiDeleteShot,
  reorderShots as apiReorderShots,
  generateFramePrompt as apiGenerateFramePrompt,
  splitShotsFromScript as apiSplitShotsFromScript,
  bindCharacterToShot as apiBindCharacter,
  unbindCharacterFromShot as apiUnbindCharacter,
  bindPropToShot as apiBindProp,
  unbindPropFromShot as apiUnbindProp,
  generateFrameImage as apiGenerateFrameImage,
  batchGenerateFrameImages as apiBatchGenerateFrameImages,
  uploadFrameImage as apiUploadFrameImage,
  setActiveFrameImage as apiSetActiveFrameImage,
  deleteFrameImage as apiDeleteFrameImage,
  generateVideo as apiGenerateVideo,
  uploadVideo as apiUploadVideo,
  setActiveVideo as apiSetActiveVideo,
  deleteVideo as apiDeleteVideo,
  importAssetToProject as apiImportAsset,
  promoteEntityToAsset as apiPromoteAsset,
  getCanvasLayout as apiGetCanvasLayout,
  saveCanvasLayout as apiSaveCanvasLayout,
  mergeProject as apiMergeProject,
  getMergeStatus as apiGetMergeStatus,
  getEntityApi,
} from '@/api/projects'
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
  MergeStatusResponse,
  WizardCreateRequest,
  WizardResumeRequest,
  EntityType,
  ProjectActiveView,
} from '@/types/project'

interface ProjectState {
  /* 项目列表 */
  projects: Project[]
  listLoading: boolean
  listTotal: number
  listPage: number
  listPageSize: number

  /* 当前项目 */
  currentProjectId: number | null
  currentProject: Project | null
  currentLoading: boolean

  /* 当前项目下的实体（详情接口已返回，这里独立保存便于局部刷新） */
  scripts: ProjectScript[]
  characters: ProjectCharacter[]
  scenes: ProjectScene[]
  props: ProjectProp[]
  shots: ProjectShot[]

  /* 当前活动视图 */
  activeView: ProjectActiveView

  /* 合成状态 */
  mergeStatus: MergeStatusResponse | null
  mergeLoading: boolean
}

export const useProjectStore = defineStore('project', {
  state: (): ProjectState => ({
    projects: [],
    listLoading: false,
    listTotal: 0,
    listPage: 1,
    listPageSize: 20,

    currentProjectId: null,
    currentProject: null,
    currentLoading: false,

    scripts: [],
    characters: [],
    scenes: [],
    props: [],
    shots: [],

    activeView: 'manager',

    mergeStatus: null,
    mergeLoading: false,
  }),

  getters: {
    /** 当前项目是否处于向导创建中 */
    isCreating: (state) => state.currentProject?.status === 'creating',
    /** 当前项目是否可逐个适配 */
    isEditable: (state) => {
      const s = state.currentProject?.status
      return s === 'in_progress' || s === 'completed'
    },
    /** 当前项目是否正在合成 */
    isMerging: (state) => state.currentProject?.status === 'merging',
    /** 按序列号排序的分镜 */
    sortedShots: (state) => [...state.shots].sort((a, b) => a.sequence_no - b.sequence_no),
  },

  actions: {
    // ================ 项目列表 ================
    async fetchList(params: ProjectListParams = {}) {
      this.listLoading = true
      try {
        const result: ProjectListResult = await apiListProjects(params)
        this.projects = result.items
        this.listTotal = result.total
        this.listPage = result.page
        this.listPageSize = result.page_size
      } finally {
        this.listLoading = false
      }
    },

    // ================ 项目详情 ================
    async fetchProject(id: number) {
      this.currentLoading = true
      try {
        const project: Project = await apiGetProject(id)
        this.setCurrentProject(project)
        return project
      } finally {
        this.currentLoading = false
      }
    },

    setCurrentProject(project: Project | null) {
      this.currentProject = project
      this.currentProjectId = project?.id ?? null
      this.activeView = project?.active_view ?? 'manager'
      // 详情接口返回的关联实体同步到本地
      this.scripts = project?.scripts ?? []
      this.characters = project?.characters ?? []
      this.scenes = project?.scenes ?? []
      this.props = project?.props ?? []
      this.shots = project?.shots ?? []
    },

    clearCurrent() {
      this.currentProject = null
      this.currentProjectId = null
      this.scripts = []
      this.characters = []
      this.scenes = []
      this.props = []
      this.shots = []
      this.mergeStatus = null
    },

    // ================ 项目 CRUD ================
    async createProject(data: ProjectCreateRequest) {
      const project = await apiCreateProject(data)
      ElMessage.success('项目已创建')
      return project
    },

    async updateProject(id: number, data: ProjectUpdateRequest) {
      const project = await apiUpdateProject(id, data)
      if (this.currentProjectId === id) {
        this.currentProject = { ...this.currentProject, ...project }
      }
      ElMessage.success('项目已更新')
      return project
    },

    async deleteProject(id: number) {
      await apiDeleteProject(id)
      this.projects = this.projects.filter(p => p.id !== id)
      if (this.currentProjectId === id) this.clearCurrent()
      ElMessage.success('项目已删除')
    },

    async archiveProject(id: number) {
      const project = await apiArchiveProject(id)
      if (this.currentProjectId === id) {
        this.currentProject = project
      }
      ElMessage.success('项目已归档')
      return project
    },

    async updateActiveView(id: number, view: ProjectActiveView) {
      const data: ActiveViewUpdateRequest = { active_view: view }
      const project = await apiUpdateActiveView(id, data)
      this.activeView = view
      if (this.currentProjectId === id) {
        this.currentProject = { ...this.currentProject, ...project }
      }
      return project
    },

    // ================ 向导 ================
    async createWizardProject(data: WizardCreateRequest) {
      const project = await apiCreateWizardProject(data)
      // 创建向导项目后立即设为当前项目，便于 SSE 监听
      this.setCurrentProject(project)
      return project
    },

    async resumeWizard(projectId: number, data: WizardResumeRequest) {
      return await apiResumeWizard(projectId, data)
    },

    /** SSE 推送 project_status_changed 事件时本地同步状态 */
    updateStatusFromEvent(newStatus: string) {
      if (this.currentProject) {
        this.currentProject = { ...this.currentProject, status: newStatus as any }
      }
    },

    /** SSE 推送 wizard_step_completed 事件后，刷新实体列表 */
    async refreshAfterWizardStep(stepKey: string) {
      if (!this.currentProjectId) return
      const pid = this.currentProjectId
      // 根据步骤 key 决定刷新哪些实体
      if (stepKey === 'script_generation') {
        this.scripts = await apiListScripts(pid)
      } else if (stepKey === 'entity_extraction') {
        this.characters = await charactersApi.list(pid)
        this.scenes = await scenesApi.list(pid)
        this.props = await propsApi.list(pid)
      } else if (stepKey === 'storyboard_split' || stepKey === 'frame_prompt_extract') {
        this.shots = await apiListShots(pid)
      }
    },

    // ================ 剧本 ================
    async fetchScripts() {
      if (!this.currentProjectId) return
      this.scripts = await apiListScripts(this.currentProjectId)
    },

    async createScript(data: ScriptCreateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const script = await apiCreateScript(this.currentProjectId, data)
      this.scripts.push(script)
      return script
    },

    async updateScript(scriptId: number, data: ScriptUpdateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const script = await apiUpdateScript(this.currentProjectId, scriptId, data)
      const idx = this.scripts.findIndex(s => s.id === scriptId)
      if (idx >= 0) this.scripts[idx] = script
      return script
    },

    async deleteScript(scriptId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteScript(this.currentProjectId, scriptId)
      this.scripts = this.scripts.filter(s => s.id !== scriptId)
    },

    async regenerateScript(scriptId: number, data: ScriptRegenerateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const script = await apiRegenerateScript(this.currentProjectId, scriptId, data)
      const idx = this.scripts.findIndex(s => s.id === scriptId)
      if (idx >= 0) this.scripts[idx] = script
      return script
    },

    // ================ 实体通用（角色/场景/道具） ================
    /**
     * 刷新某类型实体列表
     */
    async fetchEntities(entityType: EntityType) {
      if (!this.currentProjectId) return
      const api = getEntityApi(entityType)
      const list = await api.list(this.currentProjectId)
      if (entityType === 'character') this.characters = list as ProjectCharacter[]
      else if (entityType === 'scene') this.scenes = list as ProjectScene[]
      else if (entityType === 'prop') this.props = list as ProjectProp[]
    },

    async createEntity(entityType: EntityType, data: any) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const entity = await api.create(this.currentProjectId, data)
      if (entityType === 'character') this.characters.push(entity)
      else if (entityType === 'scene') this.scenes.push(entity)
      else if (entityType === 'prop') this.props.push(entity)
      return entity
    },

    async updateEntity(entityType: EntityType, id: number, data: any) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const entity = await api.update(this.currentProjectId, id, data)
      const replace = (arr: any[]) => {
        const idx = arr.findIndex(e => e.id === id)
        if (idx >= 0) arr[idx] = entity
      }
      if (entityType === 'character') replace(this.characters)
      else if (entityType === 'scene') replace(this.scenes)
      else if (entityType === 'prop') replace(this.props)
      return entity
    },

    async deleteEntity(entityType: EntityType, id: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      await api.delete(this.currentProjectId, id)
      if (entityType === 'character') this.characters = this.characters.filter(e => e.id !== id)
      else if (entityType === 'scene') this.scenes = this.scenes.filter(e => e.id !== id)
      else if (entityType === 'prop') this.props = this.props.filter(e => e.id !== id)
    },

    async generateEntityImage(entityType: EntityType, id: number, data: any) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const entity = await api.generateImage(this.currentProjectId, id, data)
      const replace = (arr: any[]) => {
        const idx = arr.findIndex(e => e.id === id)
        if (idx >= 0) arr[idx] = entity
      }
      if (entityType === 'character') replace(this.characters)
      else if (entityType === 'scene') replace(this.scenes)
      else if (entityType === 'prop') replace(this.props)
      return entity
    },

    async batchGenerateCharacters(data: BatchGenerateCharactersRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await charactersApi.batchGenerate(this.currentProjectId, data)
    },

    async uploadEntityImage(entityType: EntityType, id: number, file: File) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const entity = await api.uploadImage(this.currentProjectId, id, file)
      const replace = (arr: any[]) => {
        const idx = arr.findIndex(e => e.id === id)
        if (idx >= 0) arr[idx] = entity
      }
      if (entityType === 'character') replace(this.characters)
      else if (entityType === 'scene') replace(this.scenes)
      else if (entityType === 'prop') replace(this.props)
      return entity
    },

    async fetchEntityVersions(entityType: EntityType, id: number): Promise<ProjectEntityAsset[]> {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      return await api.listVersions(this.currentProjectId, id)
    },

    async setEntityActiveVersion(entityType: EntityType, id: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const data: SetActiveVersionRequest = { version_id: versionId }
      const entity = await api.setActiveVersion(this.currentProjectId, id, data)
      const replace = (arr: any[]) => {
        const idx = arr.findIndex(e => e.id === id)
        if (idx >= 0) arr[idx] = entity
      }
      if (entityType === 'character') replace(this.characters)
      else if (entityType === 'scene') replace(this.scenes)
      else if (entityType === 'prop') replace(this.props)
      return entity
    },

    async deleteEntityVersion(entityType: EntityType, id: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      await api.deleteVersion(this.currentProjectId, id, versionId)
    },

    async extractEntitiesFromScript(entityType: EntityType, scriptId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      const result = await api.extractFromScript(this.currentProjectId, scriptId)
      // 提取完成后刷新对应实体列表
      await this.fetchEntities(entityType)
      return result
    },

    // ================ 分镜 ================
    async fetchShots() {
      if (!this.currentProjectId) return
      this.shots = await apiListShots(this.currentProjectId)
    },

    async createShot(data: ShotCreateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const shot = await apiCreateShot(this.currentProjectId, data)
      this.shots.push(shot)
      return shot
    },

    async updateShot(shotId: number, data: ShotUpdateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const shot = await apiUpdateShot(this.currentProjectId, shotId, data)
      const idx = this.shots.findIndex(s => s.id === shotId)
      if (idx >= 0) this.shots[idx] = shot
      return shot
    },

    async deleteShot(shotId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteShot(this.currentProjectId, shotId)
      this.shots = this.shots.filter(s => s.id !== shotId)
    },

    async reorderShots(data: ShotReorderRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiReorderShots(this.currentProjectId, data)
      // 重新拉取分镜以保证 sequence_no 正确
      await this.fetchShots()
    },

    async generateFramePrompt(shotId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const shot = await apiGenerateFramePrompt(this.currentProjectId, shotId)
      const idx = this.shots.findIndex(s => s.id === shotId)
      if (idx >= 0) this.shots[idx] = shot
      return shot
    },

    async splitShotsFromScript(scriptId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const result = await apiSplitShotsFromScript(this.currentProjectId, scriptId)
      await this.fetchShots()
      return result
    },

    async bindCharacter(shotId: number, characterId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiBindCharacter(this.currentProjectId, shotId, { entity_id: characterId })
      // 重新拉取该分镜详情
      await this.refreshShot(shotId)
    },

    async unbindCharacter(shotId: number, characterId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiUnbindCharacter(this.currentProjectId, shotId, characterId)
      await this.refreshShot(shotId)
    },

    async bindProp(shotId: number, propId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiBindProp(this.currentProjectId, shotId, { entity_id: propId })
      await this.refreshShot(shotId)
    },

    async unbindProp(shotId: number, propId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiUnbindProp(this.currentProjectId, shotId, propId)
      await this.refreshShot(shotId)
    },

    /** 重新拉取单个分镜详情（绑定/解绑后使用） */
    async refreshShot(shotId: number) {
      if (!this.currentProjectId) return
      const { getShot } = await import('@/api/projects')
      const shot = await getShot(this.currentProjectId, shotId)
      const idx = this.shots.findIndex(s => s.id === shotId)
      if (idx >= 0) this.shots[idx] = shot
    },

    // ================ 帧图 ================
    async generateFrameImage(shotId: number, data: GenerateFrameImageRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const frameImage = await apiGenerateFrameImage(this.currentProjectId, shotId, data)
      await this.refreshShot(shotId)
      return frameImage
    },

    async batchGenerateFrameImages(data: BatchGenerateFrameImagesRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await apiBatchGenerateFrameImages(this.currentProjectId, data)
    },

    async uploadFrameImage(shotId: number, file: File) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const frameImage = await apiUploadFrameImage(this.currentProjectId, shotId, file)
      await this.refreshShot(shotId)
      return frameImage
    },

    async setActiveFrameImage(shotId: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const data: SetActiveVersionRequest = { version_id: versionId }
      const frameImage = await apiSetActiveFrameImage(this.currentProjectId, shotId, data)
      await this.refreshShot(shotId)
      return frameImage
    },

    async deleteFrameImage(shotId: number, frameImageId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteFrameImage(this.currentProjectId, shotId, frameImageId)
      await this.refreshShot(shotId)
    },

    // ================ 视频 ================
    async generateVideo(shotId: number, data: GenerateVideoRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const video = await apiGenerateVideo(this.currentProjectId, shotId, data)
      await this.refreshShot(shotId)
      return video
    },

    async uploadVideo(shotId: number, file: File) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const video = await apiUploadVideo(this.currentProjectId, shotId, file)
      await this.refreshShot(shotId)
      return video
    },

    async setActiveVideo(shotId: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const data: SetActiveVersionRequest = { version_id: versionId }
      const video = await apiSetActiveVideo(this.currentProjectId, shotId, data)
      await this.refreshShot(shotId)
      return video
    },

    async deleteVideo(shotId: number, videoId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteVideo(this.currentProjectId, shotId, videoId)
      await this.refreshShot(shotId)
    },

    // ================ 资产桥接 ================
    async importAsset(data: ImportAssetRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const result = await apiImportAsset(this.currentProjectId, data)
      // 导入后刷新对应实体列表
      await this.fetchEntities(data.entity_type)
      return result
    },

    async promoteAsset(data: PromoteAssetRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await apiPromoteAsset(this.currentProjectId, data)
    },

    // ================ 画布 ================
    async fetchCanvasLayout() {
      if (!this.currentProjectId) return null
      const result = await apiGetCanvasLayout(this.currentProjectId)
      return result.canvas_data
    },

    async saveCanvasLayout(canvasData: Record<string, any>) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const data: CanvasDataUpdate = { canvas_data: canvasData }
      const result = await apiSaveCanvasLayout(this.currentProjectId, data)
      if (this.currentProject) {
        this.currentProject = { ...this.currentProject, canvas_data: result.canvas_data }
      }
      return result.canvas_data
    },

    // ================ 合成 ================
    async mergeProject() {
      if (!this.currentProjectId) throw new Error('未选择项目')
      this.mergeLoading = true
      try {
        await apiMergeProject(this.currentProjectId)
        ElMessage.success('合成任务已启动')
      } finally {
        this.mergeLoading = false
      }
    },

    async fetchMergeStatus() {
      if (!this.currentProjectId) return
      this.mergeStatus = await apiGetMergeStatus(this.currentProjectId)
    },
  },
})

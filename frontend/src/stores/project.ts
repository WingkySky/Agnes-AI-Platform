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
  rebuildProjectCover as apiRebuildProjectCover,
  setProjectCover as apiSetProjectCover,
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
  // Phase 2
  listAudios as apiListAudios,
  generateTTS as apiGenerateTTS,
  batchGenerateTTS as apiBatchGenerateTTS,
  uploadAudio as apiUploadAudio,
  setActiveAudio as apiSetActiveAudio,
  deleteAudio as apiDeleteAudio,
  listBuiltinVoices as apiListBuiltinVoices,
  listCharacterVoices as apiListCharacterVoices,
  assignCharacterVoice as apiAssignCharacterVoice,
  generateSubtitles as apiGenerateSubtitles,
  generateSubtitlesWithWhisper as apiGenerateSubtitlesWithWhisper,
  listSubtitleClips as apiListSubtitleClips,
  getSubtitleStyle as apiGetSubtitleStyle,
  updateSubtitleStyle as apiUpdateSubtitleStyle,
  checkWhisperAvailable as apiCheckWhisperAvailable,
  initTimeline as apiInitTimeline,
  listTimelineClips as apiListTimelineClips,
  createTimelineClip as apiCreateTimelineClip,
  updateTimelineClip as apiUpdateTimelineClip,
  deleteTimelineClip as apiDeleteTimelineClip,
  splitTimelineClip as apiSplitTimelineClip,
  rippleDeleteTimelineClip as apiRippleDeleteTimelineClip,
  getTimelineData as apiGetTimelineData,
  saveTimelineData as apiSaveTimelineData,
  listBgms as apiListBgms,
  listBgmMoods as apiListBgmMoods,
  uploadBgm as apiUploadBgm,
  mergeProjectAdvanced as apiMergeProjectAdvanced,
  // Phase 2 增强
  getMediaLibrary as apiGetMediaLibrary,
  listMarkers as apiListMarkers,
  createMarker as apiCreateMarker,
  deleteMarker as apiDeleteMarker,
} from '@/api/projects'
import type {
  Project,
  ProjectStatus,
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
  MediaLibraryResponse,
  ProjectMarker,
  MarkerCreateRequest,
  TrackState,
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
  /* 当前选中的集剧本 ID（null=全部集视图，number=某集） */
  currentScriptId: number | null

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
  /** 合成进度 SSE 事件（由 ProjectDetailView 同步自 useProjectSSE） */
  mergeProgress: Record<string, any> | null

  /* Phase 2 — 配音 / 音色 / 字幕 / 时间线 / BGM */
  builtinVoices: VoiceOption[]
  characterVoices: CharacterVoice[]
  timelineData: TimelineDataResponse | null
  timelineLoading: boolean
  subtitleStyle: SubtitleStyle | null
  whisperAvailable: boolean
  bgmList: BGMItem[]
  bgmMoods: string[]

  /* Phase 2 增强 — 素材库 / 标记 / 轨道状态 */
  mediaLibrary: MediaLibraryResponse | null
  markers: ProjectMarker[]
  trackStates: Record<string, TrackState>
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
    currentScriptId: null,

    scripts: [],
    characters: [],
    scenes: [],
    props: [],
    shots: [],

    activeView: 'manager',

    mergeStatus: null,
    mergeLoading: false,
    mergeProgress: null,

    // Phase 2
    builtinVoices: [],
    characterVoices: [],
    timelineData: null,
    timelineLoading: false,
    subtitleStyle: null,
    whisperAvailable: false,
    bgmList: [],
    bgmMoods: [],

    // Phase 2 增强
    mediaLibrary: null,
    markers: [],
    trackStates: {},
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

    /** 按 episode_no 分组的分镜（全部集视图用；episode_no 为 null 时归到 0） */
    shotsByEpisode(state): Record<number, ProjectShot[]> {
      const grouped: Record<number, ProjectShot[]> = {}
      for (const shot of state.shots) {
        const ep = shot.episode_no ?? 0
        ;(grouped[ep] ??= []).push(shot)
      }
      return grouped
    },
    /** 按 episode_no 分组的角色 */
    charactersByEpisode(state): Record<number, ProjectCharacter[]> {
      const grouped: Record<number, ProjectCharacter[]> = {}
      for (const c of state.characters) {
        const ep = c.episode_no ?? 0
        ;(grouped[ep] ??= []).push(c)
      }
      return grouped
    },
    /** 按 episode_no 分组的场景 */
    scenesByEpisode(state): Record<number, ProjectScene[]> {
      const grouped: Record<number, ProjectScene[]> = {}
      for (const s of state.scenes) {
        const ep = s.episode_no ?? 0
        ;(grouped[ep] ??= []).push(s)
      }
      return grouped
    },
    /** 按 episode_no 分组的道具 */
    propsByEpisode(state): Record<number, ProjectProp[]> {
      const grouped: Record<number, ProjectProp[]> = {}
      for (const p of state.props) {
        const ep = p.episode_no ?? 0
        ;(grouped[ep] ??= []).push(p)
      }
      return grouped
    },
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

    /** 切换当前集——自动重新拉取四类资源（分镜/角色/场景/道具） */
    async setCurrentScript(scriptId: number | null) {
      this.currentScriptId = scriptId
      if (!this.currentProjectId) return
      await Promise.all([
        this.fetchShots(),
        this.fetchEntities('character'),
        this.fetchEntities('scene'),
        this.fetchEntities('prop'),
      ])
    },

    clearCurrent() {
      this.currentProject = null
      this.currentProjectId = null
      this.currentScriptId = null
      this.scripts = []
      this.characters = []
      this.scenes = []
      this.props = []
      this.shots = []
      this.mergeStatus = null
      this.mergeLoading = false
      this.mergeProgress = null
      // Phase 2 增强
      this.mediaLibrary = null
      this.markers = []
      this.trackStates = {}
      this._stopMergePolling()
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
      const data: ActiveViewUpdateRequest = { view }
      const project = await apiUpdateActiveView(id, data)
      this.activeView = view
      if (this.currentProjectId === id) {
        this.currentProject = { ...this.currentProject, ...project }
      }
      return project
    },

    // ================ 封面管理 ================
    async rebuildCover(id: number) {
      const project = await apiRebuildProjectCover(id)
      if (this.currentProjectId === id) {
        this.currentProject = { ...this.currentProject, ...project }
      }
      // 同步更新列表中的项目
      const idx = this.projects.findIndex(p => p.id === id)
      if (idx >= 0) this.projects[idx] = { ...this.projects[idx], ...project }
      ElMessage.success('封面已自动选取')
      return project
    },

    async setCoverFromFrame(id: number, frameImageId: number) {
      const project = await apiSetProjectCover(id, frameImageId)
      if (this.currentProjectId === id) {
        this.currentProject = { ...this.currentProject, ...project }
      }
      const idx = this.projects.findIndex(p => p.id === id)
      if (idx >= 0) this.projects[idx] = { ...this.projects[idx], ...project }
      ElMessage.success('封面已设置')
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
        this.currentProject = { ...this.currentProject, status: newStatus as ProjectStatus }
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
     * 刷新某类型实体列表（按 currentScriptId 过滤；null=全部集视图）
     */
    async fetchEntities(entityType: EntityType) {
      if (!this.currentProjectId) return
      const api = getEntityApi(entityType)
      const list = await api.list(this.currentProjectId, this.currentScriptId ?? undefined)
      if (entityType === 'character') this.characters = list as ProjectCharacter[]
      else if (entityType === 'scene') this.scenes = list as ProjectScene[]
      else if (entityType === 'prop') this.props = list as ProjectProp[]
    },

    async createEntity(entityType: EntityType, data: any) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      if (!this.currentScriptId) throw new Error('请先选择集数后再新建')
      const api = getEntityApi(entityType)
      // 自动注入当前集 script_id（集数隔离）
      const entity = await api.create(this.currentProjectId, {
        ...data,
        script_id: this.currentScriptId,
      })
      if (entityType === 'character') this.characters.push(entity)
      else if (entityType === 'scene') this.scenes.push(entity)
      else if (entityType === 'prop') this.props.push(entity)
      return entity
    },

    /** 跨集复制角色/场景/道具到目标集（不自动切换到目标集，留在当前集） */
    async copyEntityTo(
      entityType: EntityType,
      entityId: number,
      targetScriptId: number,
    ) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const api = getEntityApi(entityType)
      await api.copyTo(this.currentProjectId, entityId, targetScriptId)
      // 不自动切换到目标集，留在当前集
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
      // 调用 generate-image 端点 → 后端提交到 image_poller，返回 { task_id, status: 'pending' }
      const resp = await api.generateImage(this.currentProjectId, id, data)
      const taskId = resp?.task_id
      if (!taskId) throw new Error('生成任务提交失败：未返回 task_id')

      // 注册到 taskQueue，轮询 + 完成后自动 claim
      const { useTaskQueueStore } = await import('@/stores/taskQueue')
      const taskQueue = useTaskQueueStore()
      const promptText = typeof resp?.prompt === 'string' ? resp.prompt : undefined
      taskQueue.registerProjectTask(
        taskId,
        { type: 'image', prompt: promptText, model: data?.model },
        {
          projectId: this.currentProjectId,
          entityType,
          entityId: id,
          claimUrl: `/api/projects/${this.currentProjectId}/${entityType === 'character' ? 'characters' : entityType === 'scene' ? 'scenes' : 'props'}/${id}/claim-image`,
        },
      )
      return resp
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
      const data: SetActiveVersionRequest = {
        entity_type: entityType,
        entity_id: id,
        version_id: versionId,
      }
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
      // 按 currentScriptId 过滤；null=全部集视图
      this.shots = await apiListShots(this.currentProjectId, this.currentScriptId ?? undefined)
    },

    async createShot(data: ShotCreateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      if (!this.currentScriptId) throw new Error('请先选择集数后再新建分镜')
      // 自动注入当前集 script_id（集数隔离）
      const shot = await apiCreateShot(this.currentProjectId, {
        ...data,
        script_id: this.currentScriptId,
      })
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
      const resp = await apiGenerateFrameImage(this.currentProjectId, shotId, data) as unknown as Record<string, unknown>
      const taskId = resp?.task_id as string | undefined
      if (!taskId) throw new Error('生成任务提交失败：未返回 task_id')

      const { useTaskQueueStore } = await import('@/stores/taskQueue')
      const taskQueue = useTaskQueueStore()
      const promptText = typeof resp?.prompt === 'string' ? resp.prompt : undefined
      taskQueue.registerProjectTask(
        taskId,
        { type: 'image', prompt: promptText, model: data?.model },
        {
          projectId: this.currentProjectId,
          shotId,
          claimUrl: `/api/projects/${this.currentProjectId}/shots/${shotId}/frame-images/claim`,
        },
      )
      return resp
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
      const frameImage = await apiSetActiveFrameImage(this.currentProjectId, shotId, versionId)
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
      const projectId = this.currentProjectId
      const { useTaskQueueStore } = await import('@/stores/taskQueue')
      const taskQueue = useTaskQueueStore()

      // 先在队列中注册 queued 占位任务，让用户立即看到任务
      // （Agnes AI 视频生成有每分钟 1 次的速率限制，后端会串行排队，
      //   如果不先注册 queued，用户点批量生成后要等很久才看到任务进队列）
      const queuedTaskId = taskQueue.registerProjectTaskQueued(
        { type: 'video', prompt: '', model: data?.model },
        {
          projectId,
          shotId,
          claimUrl: `/api/projects/${projectId}/shots/${shotId}/videos/claim`,
        },
      )

      // 异步提交（不 await）：API 调用会因后端速率限制挂起 60+ 秒，
      // 不能阻塞调用方，否则 Promise.all 会卡住无法继续注册其他任务
      // 内部已 try/catch，不会抛 unhandled rejection
      void this._submitVideoTaskInBackground(queuedTaskId, projectId, shotId, data)

      // 立即返回，调用方（如批量生成）可继续处理下一个分镜
      return { task_id: queuedTaskId, shot_id: shotId, status: 'queued' }
    },

    /**
     * 后台异步提交视频生成任务到后端。
     * - 成功：更新 backendTaskId + 状态切换为 processing + 启动轮询
     * - 失败：标记任务为 failed（保留 errorMessage 供 UI 展示）
     */
    async _submitVideoTaskInBackground(
      queuedTaskId: string,
      projectId: number,
      shotId: number,
      data: GenerateVideoRequest,
    ): Promise<void> {
      const { useTaskQueueStore } = await import('@/stores/taskQueue')
      const taskQueue = useTaskQueueStore()
      try {
        const resp = await apiGenerateVideo(projectId, shotId, data) as unknown as Record<string, unknown>
        const backendTaskId = resp?.task_id as string | undefined
        if (!backendTaskId) {
          throw new Error('生成任务提交失败：未返回 task_id')
        }
        // 切换为 processing + 启动轮询
        taskQueue.updateProjectTaskBackendId(queuedTaskId, backendTaskId)
      } catch (e: any) {
        // 标记为 failed，保留错误信息供 UI 展示
        // 注意：HTTP 429 / 503 等错误已经在 axios 拦截器弹过 ElMessage，
        // 这里只需更新队列状态，不再重复提示
        taskQueue.markProjectTaskFailed(queuedTaskId, e?.message || '提交失败')
      }
    },

    async uploadVideo(shotId: number, file: File) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const video = await apiUploadVideo(this.currentProjectId, shotId, file)
      await this.refreshShot(shotId)
      return video
    },

    async setActiveVideo(shotId: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const video = await apiSetActiveVideo(this.currentProjectId, shotId, versionId)
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
      const result = await apiImportAsset(this.currentProjectId, data.entity_type, data)
      // 导入后刷新对应实体列表
      await this.fetchEntities(data.entity_type)
      return result
    },

    async promoteAsset(data: PromoteAssetRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await apiPromoteAsset(this.currentProjectId, data.entity_type, data.entity_id, data)
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
        // 不在此处弹 success 提示，由 ProjectHeader 统一处理（避免重复弹）
      } catch (e: any) {
        // 透传错误给调用方，由 UI 层决定如何提示
        throw e
      } finally {
        this.mergeLoading = false
      }
    },

    // ================ Phase 2: 配音（TTS） ================
    async listAudios(shotId: number) {
      if (!this.currentProjectId) return []
      return await apiListAudios(this.currentProjectId, shotId)
    },

    async generateTTS(shotId: number, data: GenerateTTSRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const audio = await apiGenerateTTS(this.currentProjectId, shotId, data)
      await this.refreshShot(shotId)
      return audio
    },

    async batchGenerateTTS(data: BatchGenerateTTSRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const result = await apiBatchGenerateTTS(this.currentProjectId, data)
      // 刷新涉及的分镜（让 UI 显示新的音频版本）
      for (const shotId of data.shot_ids) {
        await this.refreshShot(shotId)
      }
      return result
    },

    async uploadAudio(shotId: number, file: File) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const audio = await apiUploadAudio(this.currentProjectId, shotId, file)
      await this.refreshShot(shotId)
      return audio
    },

    async setActiveAudio(shotId: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const audio = await apiSetActiveAudio(this.currentProjectId, shotId, versionId)
      await this.refreshShot(shotId)
      return audio
    },

    async deleteAudio(shotId: number, versionId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteAudio(this.currentProjectId, shotId, versionId)
      await this.refreshShot(shotId)
    },

    // ================ Phase 2: 音色 ================
    async fetchBuiltinVoices() {
      if (!this.currentProjectId) return
      this.builtinVoices = await apiListBuiltinVoices(this.currentProjectId)
    },

    async fetchCharacterVoices() {
      if (!this.currentProjectId) return
      this.characterVoices = await apiListCharacterVoices(this.currentProjectId)
    },

    async assignCharacterVoice(
      characterId: number,
      data: AssignCharacterVoiceRequest,
    ) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const assignment = await apiAssignCharacterVoice(
        this.currentProjectId, characterId, data,
      )
      await this.fetchCharacterVoices()
      return assignment
    },

    // ================ Phase 2: 字幕 ================
    async generateSubtitles(data: GenerateSubtitleRequest = {}) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await apiGenerateSubtitles(this.currentProjectId, data)
    },

    async generateSubtitlesWithWhisper(data: GenerateSubtitleAdvancedRequest = {}) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      return await apiGenerateSubtitlesWithWhisper(this.currentProjectId, data)
    },

    async updateSubtitleStyle(data: SubtitleStyle) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      this.subtitleStyle = await apiUpdateSubtitleStyle(this.currentProjectId, data)
      return this.subtitleStyle
    },

    async fetchWhisperAvailable() {
      if (!this.currentProjectId) return
      const result = await apiCheckWhisperAvailable(this.currentProjectId)
      this.whisperAvailable = result.available
    },

    // ================ Phase 2: 时间线 ================
    async initTimeline() {
      if (!this.currentProjectId) throw new Error('未选择项目')
      this.timelineLoading = true
      try {
        this.timelineData = await apiInitTimeline(this.currentProjectId)
        // 初始化后同步字幕样式
        if (this.timelineData.subtitle_style) {
          this.subtitleStyle = this.timelineData.subtitle_style as SubtitleStyle
        }
      } finally {
        this.timelineLoading = false
      }
    },

    async fetchTimelineData() {
      if (!this.currentProjectId) return
      this.timelineLoading = true
      try {
        this.timelineData = await apiGetTimelineData(this.currentProjectId)
        if (this.timelineData.subtitle_style) {
          this.subtitleStyle = this.timelineData.subtitle_style as SubtitleStyle
        }
      } finally {
        this.timelineLoading = false
      }
    },

    async createTimelineClip(data: TimelineClipCreateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const clip = await apiCreateTimelineClip(this.currentProjectId, data)
      await this.fetchTimelineData()
      return clip
    },

    async updateTimelineClip(clipId: number, data: TimelineClipUpdateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const clip = await apiUpdateTimelineClip(this.currentProjectId, clipId, data)
      await this.fetchTimelineData()
      return clip
    },

    async deleteTimelineClip(clipId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      await apiDeleteTimelineClip(this.currentProjectId, clipId)
      await this.fetchTimelineData()
    },

    /** 分割时间线片段（Ctrl+K）— 在指定时间点切两段 */
    async splitTimelineClip(clipId: number, splitTime: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const result = await apiSplitTimelineClip(this.currentProjectId, clipId, splitTime)
      await this.fetchTimelineData()
      return result
    },

    /** 波纹删除：删除片段后同轨后续片段自动前移 */
    async rippleDeleteTimelineClip(clipId: number) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const result = await apiRippleDeleteTimelineClip(this.currentProjectId, clipId)
      await this.fetchTimelineData()
      return result
    },

    async saveTimelineData(data: TimelineDataUpdateRequest) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      this.timelineData = await apiSaveTimelineData(this.currentProjectId, data)
      if (this.timelineData.subtitle_style) {
        this.subtitleStyle = this.timelineData.subtitle_style as SubtitleStyle
      }
      return this.timelineData
    },

    // ================ Phase 2: BGM 库 ================
    async fetchBgms(mood?: BGMMood) {
      if (!this.currentProjectId) return
      this.bgmList = await apiListBgms(this.currentProjectId, mood)
    },

    async fetchBgmMoods() {
      if (!this.currentProjectId) return
      const result = await apiListBgmMoods(this.currentProjectId)
      this.bgmMoods = result.moods
    },

    async uploadBgm(file: File, name: string, mood: string) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      const meta = await apiUploadBgm(this.currentProjectId, file, name, mood)
      await this.fetchBgms()
      return meta
    },

    // ================ Phase 2: 高级合成 ================
    async mergeProjectAdvanced(data: MergeAdvancedRequest = {}) {
      if (!this.currentProjectId) throw new Error('未选择项目')
      this.mergeLoading = true
      // 注意：合成是异步任务，API 立即返回 status="started"
      // mergeLoading 由 ProjectDetailView 的 SSE watch 维护：
      //   - 收到 merge_progress(status=started/downloading/compositing) → 保持 true
      //   - 收到 merge_progress(status=completed) → false + 刷新详情
      //   - 收到 merge_progress(status=failed) → false + 错误提示
      // 轮询兜底：SSE 事件可能丢失，启动轮询作为兜底
      try {
        await apiMergeProjectAdvanced(this.currentProjectId, data)
        this._startMergePolling(this.currentProjectId)
      } catch (e) {
        // API 调用本身失败（网络/路由错误/400校验失败），释放 loading 并清理过时进度
        this.mergeLoading = false
        this.mergeProgress = null
        throw e
      }
    },

    // 合成轮询兜底：SSE 事件丢失时通过轮询项目状态恢复
    // 每 5 秒轮询一次，最多 5 分钟（60 次），超时自动释放并提示
    _mergePollingTimer: null as ReturnType<typeof setInterval> | null,
    _mergePollingCount: 0,
    _startMergePolling(projectId: number) {
      this._stopMergePolling()
      this._mergePollingCount = 0
      this._mergePollingTimer = setInterval(async () => {
        if (!this.mergeLoading) {
          this._stopMergePolling()
          return
        }
        this._mergePollingCount++
        // 超时 5 分钟（60 次 × 5s = 300s）
        if (this._mergePollingCount > 60) {
          this._stopMergePolling()
          this.mergeLoading = false
          this.mergeProgress = null
          console.warn('[merge-polling] 合成超时（5 分钟无完成事件），已自动释放 loading')
          return
        }
        try {
          const project = await apiGetProject(projectId)
          // 项目状态已变为 completed（合成成功）但 SSE 事件丢失
          if (project.status === 'completed' && project.final_video_url) {
            this._stopMergePolling()
            this.mergeLoading = false
            this.mergeProgress = { status: 'completed', progress: 100, final_video_url: project.final_video_url }
            this.setCurrentProject(project)
            console.info('[merge-polling] 检测到合成已完成（SSE 事件丢失），已恢复状态')
            return
          }
          // 项目状态回滚为 in_progress（合成失败）但 SSE 事件丢失
          if (project.status === 'in_progress') {
            this._stopMergePolling()
            this.mergeLoading = false
            this.mergeProgress = null
            this.setCurrentProject(project)
            console.warn('[merge-polling] 检测到合成已失败回滚（SSE 事件丢失），已恢复状态')
            return
          }
        } catch (e) {
          console.warn('[merge-polling] 轮询项目状态失败:', e)
        }
      }, 5000)
    },
    _stopMergePolling() {
      if (this._mergePollingTimer) {
        clearInterval(this._mergePollingTimer)
        this._mergePollingTimer = null
      }
    },

    // ================ Phase 2 增强: 素材库 ================
    async fetchMediaLibrary() {
      if (!this.currentProjectId) return
      this.mediaLibrary = await apiGetMediaLibrary(this.currentProjectId)
    },

    // ================ Phase 2 增强: 标记 ================
    async fetchMarkers() {
      if (!this.currentProjectId) return
      this.markers = await apiListMarkers(this.currentProjectId)
    },

    async addMarker(data: MarkerCreateRequest) {
      if (!this.currentProjectId) return
      const marker = await apiCreateMarker(this.currentProjectId, data)
      this.markers.push(marker)
      this.markers.sort((a, b) => a.time - b.time)
      return marker
    },

    async removeMarker(markerId: number) {
      if (!this.currentProjectId) return
      await apiDeleteMarker(this.currentProjectId, markerId)
      this.markers = this.markers.filter(m => m.id !== markerId)
    },

    // ================ Phase 2 增强: 轨道状态 ================
    setTrackMuted(trackType: string, trackIndex: number, muted: boolean) {
      const key = `${trackType}:${trackIndex}`
      const cur = this.trackStates[key] || { muted: false, locked: false }
      this.trackStates[key] = { ...cur, muted }
    },

    setTrackLocked(trackType: string, trackIndex: number, locked: boolean) {
      const key = `${trackType}:${trackIndex}`
      const cur = this.trackStates[key] || { muted: false, locked: false }
      this.trackStates[key] = { ...cur, locked }
    },

    isTrackMuted(trackType: string, trackIndex: number): boolean {
      return this.trackStates[`${trackType}:${trackIndex}`]?.muted ?? false
    },

    isTrackLocked(trackType: string, trackIndex: number): boolean {
      return this.trackStates[`${trackType}:${trackIndex}`]?.locked ?? false
    },
  },
})

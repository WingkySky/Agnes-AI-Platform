<!-- =====================================================
     SceneEditorView —— 3D 导演台全屏工作台
     布局：顶栏(场景 CRUD/挂载) + 左栏(场景树+场景库) + 中央视口 +
     右栏(属性/Shot 检查器/翻译器预览) + 底部序列器 + 状态栏。
     面板全部可拖拽缩放/可折叠（布局记忆 localStorage），F 一键全屏视口。
     路由：/scene-editor（workbench 变体：藏应用壳、保留浮层面板）
     ===================================================== -->

<template>
  <div ref="rootEl" class="scene-workbench">
    <!-- 顶栏：返回 + 场景信息 + 保存/挂载 -->
    <header class="wb-topbar">
      <el-button text :icon="Back" class="back-btn" @click="goBack">{{ t('common.back') }}</el-button>
      <span class="topbar-divider" />
      <el-input v-model="currentName" size="small" style="width: 200px" :placeholder="t('scene3d.namePlaceholder')" />
      <el-input v-model="currentDesc" size="small" style="width: 240px" :placeholder="t('scene3d.descPlaceholder')" />
      <el-switch v-model="currentIsPublic" size="small" :active-text="t('scene3d.isPublic')" />
      <div class="topbar-actions">
        <el-button size="small" type="primary" :loading="saving" @click="onSave">
          {{ currentId ? t('common.save') : t('scene3d.create') }}
        </el-button>
        <el-button size="small" plain @click="onNew">{{ t('scene3d.newScene') }}</el-button>
        <el-button
          v-if="currentId"
          size="small"
          plain
          :type="scenesStore.isMountedIn('image', currentId) ? 'warning' : 'default'"
          @click="onMountScene('image')"
        >
          {{ t('scene3d.mountToImage') }}
        </el-button>
        <el-button
          v-if="currentId"
          size="small"
          plain
          :type="scenesStore.isMountedIn('video', currentId) ? 'warning' : 'default'"
          @click="onMountScene('video')"
        >
          {{ t('scene3d.mountToVideo') }}
        </el-button>
        <el-button v-if="currentId" size="small" type="danger" plain :loading="deleting" @click="onDelete">
          {{ t('common.delete') }}
        </el-button>
        <el-tooltip :content="t('scene3d.fullViewportHint') + ' (F)'">
          <el-button size="small" plain :icon="FullScreen" @click="toggleFullscreenViewport" />
        </el-tooltip>
      </div>
    </header>

    <!-- 主区：左栏 / 视口 / 右栏 -->
    <div class="wb-main">
      <aside v-if="showPanel('left')" class="wb-aside" :style="{ width: layout.leftWidth + 'px' }">
        <SceneTreePanel
          v-model="sceneData"
          :selected="selected"
          :scenes="scenes"
          :current-scene-id="currentId"
          :loading="listLoading"
          :search="searchKeyword"
          @select="onSelect"
          @select-scene="onSelectScene"
          @update:search="searchKeyword = $event"
          @search-scenes="loadScenes"
        />
        <div class="aside-collapse left" :title="t('scene3d.collapseLeft') + ' ( [ )'" @click="togglePanel('left')">
          <el-icon><ArrowLeft /></el-icon>
        </div>
      </aside>
      <div v-if="showPanel('left')" class="v-grip" @mousedown="startDrag('left', $event)" />

      <main class="wb-viewport">
        <Scene3DEditor ref="viewportRef" v-model="sceneData" @captured="onCaptured" @select="onSelect" />
      </main>

      <div v-if="showPanel('right')" class="v-grip" @mousedown="startDrag('right', $event)" />
      <aside v-if="showPanel('right')" class="wb-aside" :style="{ width: layout.rightWidth + 'px' }">
        <SceneInspector
          v-model="sceneData"
          :selected="selected"
          :shot="activeShot"
          :prompt-suffix="promptSuffix"
          :prompt-details="promptDetails"
          @add-keyframe="addKeyframeFromViewport"
        />
        <div class="aside-collapse right" :title="t('scene3d.collapseRight') + ' ( ] )'" @click="togglePanel('right')">
          <el-icon><ArrowRight /></el-icon>
        </div>
      </aside>

      <!-- 折叠后的展开把手 -->
      <div v-if="!layout.leftOpen && !fullscreenViewport" class="expand-tab left" :title="t('scene3d.expandLeft')" @click="togglePanel('left')">
        <el-icon><ArrowRight /></el-icon>
      </div>
      <div v-if="!layout.rightOpen && !fullscreenViewport" class="expand-tab right" :title="t('scene3d.expandRight')" @click="togglePanel('right')">
        <el-icon><ArrowLeft /></el-icon>
      </div>
    </div>

    <!-- 底部 dock：序列器 -->
    <div v-if="showPanel('dock')" class="h-grip" @mousedown="startDrag('dock', $event)" />
    <footer v-if="showPanel('dock')" class="wb-dock" :style="{ height: layout.dockHeight + 'px' }">
      <div class="dock-collapse" :title="t('scene3d.collapseDock') + ' (B)'" @click="togglePanel('dock')">
        <el-icon><ArrowDown /></el-icon>
      </div>
      <ShotSequencer
        v-model="sceneData"
        :playing-shot-id="playingShotId"
        @select-shot="onSelectShot"
        @add-shot="addShot"
        @play-all="playAll"
        @derive="deriveVisible = true"
        @focus-shot="onFocusShot"
      />
    </footer>
    <div v-if="!layout.dockOpen && !fullscreenViewport" class="expand-tab dock" :title="t('scene3d.expandDock')" @click="togglePanel('dock')">
      <el-icon><ArrowUp /></el-icon>
    </div>

    <!-- 状态栏 -->
    <div class="wb-statusbar">
      <span>{{ statusSelection }}</span>
      <span class="status-hint">{{ t('scene3d.statusHint') }}</span>
      <span v-if="savedAt" class="status-saved">{{ t('scene3d.savedAt') }} {{ savedAt }}</span>
    </div>

    <!-- 视口拍照弹窗：下载 / 复制 / 设为场景封面 -->
    <el-dialog v-model="captureVisible" :title="t('scene3d.captureTitle')" width="560px">
      <img v-if="captureDataUrl" :src="captureDataUrl" class="capture-preview" />
      <template #footer>
        <el-button @click="downloadCapture">{{ t('common.download') }}</el-button>
        <el-button @click="copyCapture">{{ t('scene3d.copyImage') }}</el-button>
        <el-button
          type="primary"
          :loading="settingCover"
          :disabled="!currentId"
          :title="currentId ? '' : t('scene3d.captureSaveFirst')"
          @click="setAsCover"
        >
          {{ t('scene3d.setCover') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量派生弹窗 -->
    <el-dialog v-model="deriveVisible" :title="t('scene3d.deriveTitle')" width="520px">
      <el-form label-width="120px" label-position="left">
        <el-form-item :label="t('scene3d.deriveKind')">
          <el-radio-group v-model="deriveKind">
            <el-radio-button value="image">{{ t('scene3d.deriveImage') }}</el-radio-button>
            <el-radio-button value="video">{{ t('scene3d.deriveVideo') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('scene3d.deriveModel')">
          <el-select v-model="deriveModel" style="width: 100%">
            <el-option
              v-for="m in deriveKind === 'image' ? modelsStore.imageModels : modelsStore.videoModels"
              :key="m.id"
              :label="m.name"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('scene3d.derivePrompt')">
          <el-input v-model="derivePrompt" type="textarea" :rows="3" :placeholder="t('scene3d.derivePromptPlaceholder')" />
        </el-form-item>
        <el-form-item v-if="deriveKind === 'video'" :label="t('scene3d.deriveCoverFirst')">
          <el-switch v-model="deriveUseCover" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deriveVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="deriving" :disabled="!deriveModel" @click="runDerive">
          {{ t('scene3d.deriveSubmit') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * SceneEditorView —— 导演台工作台编排层：
 * 场景 CRUD / 面板布局（拖拽+折叠+记忆）/ 预演播放协调 / 批量派生 / 挂载生成。
 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back,
  FullScreen,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowDown,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import { useScenesStore } from '@/stores/scenes'
import { useModelsStore } from '@/stores/models'
import { useTaskQueueStore } from '@/stores/taskQueue'
import Scene3DEditor from '@/components/scene/Scene3DEditor.vue'
import SceneTreePanel from '@/components/scene/SceneTreePanel.vue'
import SceneInspector from '@/components/scene/SceneInspector.vue'
import ShotSequencer from '@/components/scene/ShotSequencer.vue'
import { uploadImage } from '@/api/uploads'
import {
  getScenes,
  createScene,
  updateScene,
  deleteScene,
  previewScenePrompt,
} from '@/api/scenes'
import {
  activeCamera as pickActiveCamera,
  defaultShot,
  newSceneData,
  normalizeSceneData,
} from '@/lib/scene/normalize'
import { buildShotDeriveParams } from '@/lib/scene/derive'
import {
  loadWorkbenchLayout,
  saveWorkbenchLayout,
  type WorkbenchLayout,
} from '@/lib/scene/workbench-layout'
import type { Scene3D, SceneData, ShotData } from '@/types/scene'

type TreeType = 'camera' | 'subject' | 'light' | 'prop'

const { t } = useI18n()
const { confirm } = useConfirm()
const router = useRouter()
const scenesStore = useScenesStore()
const modelsStore = useModelsStore()
const queue = useTaskQueueStore()

// ---------- 面板布局（拖拽缩放 + 折叠 + 记忆 + 全屏视口） ----------
const layout = reactive<WorkbenchLayout>(loadWorkbenchLayout())
const fullscreenViewport = ref(false)

function showPanel(key: 'left' | 'right' | 'dock'): boolean {
  if (fullscreenViewport.value) return false
  return key === 'left' ? layout.leftOpen : key === 'right' ? layout.rightOpen : layout.dockOpen
}

function togglePanel(key: 'left' | 'right' | 'dock') {
  if (key === 'left') layout.leftOpen = !layout.leftOpen
  else if (key === 'right') layout.rightOpen = !layout.rightOpen
  else layout.dockOpen = !layout.dockOpen
  persistLayout()
}

function toggleFullscreenViewport() {
  fullscreenViewport.value = !fullscreenViewport.value
}

function persistLayout() {
  saveWorkbenchLayout({ ...layout })
}

type DragKey = 'left' | 'right' | 'dock'
let dragState: { key: DragKey; startPos: number; startSize: number } | null = null

function startDrag(key: DragKey, e: MouseEvent) {
  e.preventDefault()
  dragState = {
    key,
    startPos: key === 'dock' ? e.clientY : e.clientX,
    startSize: key === 'left' ? layout.leftWidth : key === 'right' ? layout.rightWidth : layout.dockHeight,
  }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e: MouseEvent) {
  if (!dragState) return
  const cur = dragState.key === 'dock' ? e.clientY : e.clientX
  const delta = cur - dragState.startPos
  const dir = dragState.key === 'right' ? -1 : 1 // 右栏把手往左拖变宽
  const size = Math.round(dragState.startSize + delta * dir)
  if (dragState.key === 'left') layout.leftWidth = clamp(size, 220, 480)
  else if (dragState.key === 'right') layout.rightWidth = clamp(size, 220, 480)
  else layout.dockHeight = clamp(size, 180, 520)
}

function onDragEnd() {
  if (dragState) persistLayout()
  dragState = null
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n))
}

// ---------- 场景数据与选中 ----------
const currentId = ref<number | null>(null)
const currentName = ref('')
const currentDesc = ref('')
const currentIsPublic = ref(false)
const sceneData = ref<SceneData>(newSceneData({ subject: t('scene3d.subjectDefaultLabel'), environment: t('scene3d.envStudio') }))
const saving = ref(false)
const deleting = ref(false)
const savedAt = ref('')
const selected = ref<{ type: TreeType; index: number } | null>(null)
const viewportRef = ref<InstanceType<typeof Scene3DEditor>>()

const activeShot = computed<ShotData | null>(
  () => sceneData.value.shots.find(s => s.id === sceneData.value.activeShotId) ?? null,
)

const statusSelection = computed(() => {
  if (playingShotId.value) return `${t('scene3d.playbackPlaying')} · ${activeShotLabel(playingShotId.value)}`
  const sel = selected.value
  if (!sel) return t('scene3d.statusNoSelection')
  const names: Record<TreeType, string> = {
    camera: t('scene3d.targetCamera'),
    subject: t('scene3d.targetSubject'),
    light: t('scene3d.targetLight'),
    prop: t('scene3d.targetProp'),
  }
  return `${names[sel.type]} #${sel.index + 1}`
})

function activeShotLabel(shotId: string): string {
  const idx = sceneData.value.shots.findIndex(s => s.id === shotId)
  return t('scene3d.shotN', { n: idx + 1 })
}

function onSelect(payload: { type: TreeType; index: number }) {
  selected.value = payload
}

// ---------- 场景列表 ----------
const scenes = ref<Scene3D[]>([])
const listLoading = ref(false)
const searchKeyword = ref('')

async function loadScenes() {
  listLoading.value = true
  try {
    const res = await getScenes({ page: 1, page_size: 50, search: searchKeyword.value || undefined })
    scenes.value = res.items || []
  } catch {
    // 错误已由 client 统一提示
  } finally {
    listLoading.value = false
  }
}

// ---------- prompt 预览（防抖；选中镜头时按镜头编译） ----------
const promptSuffix = ref('')
const promptDetails = ref<Record<string, unknown>>({})
let previewTimer: ReturnType<typeof setTimeout> | null = null

async function fetchPreview() {
  try {
    const shot = activeShot.value
    const res = await previewScenePrompt(sceneData.value, shot || undefined)
    promptSuffix.value = res.prompt_suffix || ''
    promptDetails.value = res.details || {}
  } catch {
    // 静默失败
  }
}

watch(
  () => [sceneData.value, sceneData.value.activeShotId] as const,
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(fetchPreview, 300)
  },
  { deep: true },
)

// ---------- 操作：新建/选择/保存/删除 ----------
function onNew() {
  currentId.value = null
  currentName.value = ''
  currentDesc.value = ''
  currentIsPublic.value = false
  sceneData.value = newSceneData({ subject: t('scene3d.subjectDefaultLabel'), environment: t('scene3d.envStudio') })
  selected.value = null
  savedAt.value = ''
}

async function onSelectScene(s: Scene3D) {
  currentId.value = s.id
  currentName.value = s.name
  currentDesc.value = s.description || ''
  currentIsPublic.value = s.is_public
  sceneData.value = normalizeSceneData(s.scene_data)
  selected.value = null
}

async function onSave() {
  if (!currentName.value.trim()) {
    ElMessage.warning(t('scene3d.nameRequired'))
    return
  }
  saving.value = true
  const data = normalizeSceneData(sceneData.value)
  sceneData.value = data
  try {
    if (currentId.value) {
      await updateScene(currentId.value, {
        name: currentName.value,
        description: currentDesc.value,
        scene_data: data,
        is_public: currentIsPublic.value,
      })
      ElMessage.success(t('scene3d.saveSuccess'))
    } else {
      const created = await createScene({
        name: currentName.value,
        description: currentDesc.value,
        scene_data: data,
        is_public: currentIsPublic.value,
      })
      currentId.value = created.id
      ElMessage.success(t('scene3d.createSuccess'))
    }
    savedAt.value = new Date().toLocaleTimeString()
    await loadScenes()
  } catch {
    // 错误已由 client 统一提示
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!currentId.value) return
  await confirm(t('scene3d.deleteConfirm'), t('common.confirm'))
  deleting.value = true
  try {
    await deleteScene(currentId.value)
    ElMessage.success(t('scene3d.deleteSuccess'))
    onNew()
    await loadScenes()
  } catch {
    // 错误已由 client 统一提示
  } finally {
    deleting.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

// ---------- 挂载生成（复用全局挂载范式） ----------
async function onMountScene(context: 'image' | 'video') {
  if (!currentId.value) return
  try {
    const scene = {
      id: currentId.value,
      name: currentName.value,
      scene_data: normalizeSceneData(sceneData.value),
    } as Scene3D
    const mounted = await scenesStore.mountScene(scene, context)
    ElMessage.success(t(mounted ? (context === 'image' ? 'scene3d.mountedImage' : 'scene3d.mountedVideo') : 'scene3d.unmounted'))
  } catch {
    ElMessage.error(t('scene3d.applyFailed'))
  }
}

// ---------- 视口拍照（下载 / 复制 / 设为封面） ----------
const captureVisible = ref(false)
const captureDataUrl = ref('')
const settingCover = ref(false)

function onCaptured(dataUrl: string) {
  captureDataUrl.value = dataUrl
  captureVisible.value = true
}

function downloadCapture() {
  if (!captureDataUrl.value) return
  const a = document.createElement('a')
  a.href = captureDataUrl.value
  a.download = `scene-${currentId.value || 'draft'}-${Date.now()}.png`
  a.click()
}

async function copyCapture() {
  try {
    const blob = await (await fetch(captureDataUrl.value)).blob()
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
    ElMessage.success(t('scene3d.copied'))
  } catch {
    ElMessage.error(t('scene3d.copyFailed'))
  }
}

async function setAsCover() {
  if (!currentId.value || !captureDataUrl.value) return
  settingCover.value = true
  try {
    const url = await uploadDataUrl(captureDataUrl.value, `scene-cover-${currentId.value}.png`)
    await updateScene(currentId.value, { cover_url: url })
    ElMessage.success(t('scene3d.setCoverOk'))
    captureVisible.value = false
    await loadScenes()
  } catch {
    ElMessage.error(t('scene3d.setCoverFailed'))
  } finally {
    settingCover.value = false
  }
}

async function uploadDataUrl(dataUrl: string, filename: string): Promise<string> {
  const blob = await (await fetch(dataUrl)).blob()
  const file = new File([blob], filename, { type: 'image/png' })
  const { url } = await uploadImage(file)
  return url
}

// ---------- 镜头序列：新增/选中/关键帧/聚焦 ----------
function addShot() {
  const cam = pickActiveCamera(sceneData.value) || sceneData.value.cameras[0]
  if (!cam) return
  const shot = defaultShot(cam)
  sceneData.value = {
    ...sceneData.value,
    shots: [...sceneData.value.shots, shot],
    activeShotId: shot.id,
  }
}

function onSelectShot(shotId: string) {
  sceneData.value = { ...sceneData.value, activeShotId: shotId }
}

function onFocusShot(shotId: string) {
  const shot = sceneData.value.shots.find(s => s.id === shotId)
  if (!shot) return
  const idx = sceneData.value.cameras.findIndex(c => c.id === shot.cameraId)
  if (idx >= 0) viewportRef.value?.focusCamera(idx)
}

/** 记录当前选中机位姿态为 activeShot 的关键帧（时间=上一帧+2s 起） */
function addKeyframeFromViewport() {
  const shot = activeShot.value
  if (!shot) return
  const pose = viewportRef.value?.activeCameraPose()
  if (!pose) return
  const lastTime = shot.keyframes.length ? shot.keyframes[shot.keyframes.length - 1].time : -2
  const frame = {
    time: Math.max(0, Math.round((lastTime + 2) * 10) / 10),
    position: pose.position,
    target: pose.target,
    fov: pose.fov,
    easing: 'smooth' as const,
  }
  sceneData.value = {
    ...sceneData.value,
    shots: sceneData.value.shots.map(s =>
      s.id === shot.id ? { ...s, keyframes: [...s.keyframes, frame].sort((a, b) => a.time - b.time) } : s,
    ),
  }
}

// ---------- 预演播放 ----------
const playingShotId = ref<string | null>(null)
const pendingCovers = new Map<string, string>()

function playAll(captureCovers: boolean) {
  const shots = sceneData.value.shots
  if (!shots.length) return
  playingShotId.value = null
  pendingCovers.clear()
  viewportRef.value?.playShots(shots, {
    captureCovers,
    onShotStart: (shot: ShotData) => {
      playingShotId.value = shot.id
    },
    onShotCover: (shotId: string, dataUrl: string) => {
      pendingCovers.set(shotId, dataUrl)
    },
    onDone: () => {
      playingShotId.value = null
      applyPendingCovers()
    },
  })
}

async function applyPendingCovers() {
  if (!pendingCovers.size) return
  const shots = [...sceneData.value.shots]
  for (let i = 0; i < shots.length; i++) {
    const dataUrl = pendingCovers.get(shots[i].id)
    if (!dataUrl) continue
    let cover: string = dataUrl
    try {
      cover = await uploadDataUrl(dataUrl, `shot-${shots[i].id}.png`)
    } catch {
      // 上传失败退回 dataURL（下次保存会被覆盖或重试）
    }
    shots[i] = { ...shots[i], coverUrl: cover }
  }
  pendingCovers.clear()
  sceneData.value = { ...sceneData.value, shots }
  if (currentId.value) {
    try {
      await updateScene(currentId.value, { scene_data: normalizeSceneData(sceneData.value) })
      savedAt.value = new Date().toLocaleTimeString()
    } catch {
      // 错误已由 client 统一提示
    }
  }
}

// ---------- 批量派生 ----------
const deriveVisible = ref(false)
const deriveKind = ref<'image' | 'video'>('image')
const deriveModel = ref('')
const derivePrompt = ref('')
const deriveUseCover = ref(true)
const deriving = ref(false)

watch(deriveVisible, (open) => {
  if (!open) return
  if (!modelsStore.loaded) modelsStore.fetchConfig()
  if (!deriveModel.value) deriveModel.value = modelsStore.getDefaultModel(deriveKind.value)
})

watch(deriveKind, () => {
  deriveModel.value = modelsStore.getDefaultModel(deriveKind.value)
})

async function runDerive() {
  const shots = sceneData.value.shots
  if (!shots.length || !deriveModel.value) return
  deriving.value = true
  const derivedPairs: { shotId: string; taskId: string }[] = []
  try {
    const scene = normalizeSceneData(sceneData.value)
    for (const shot of shots) {
      const cam = scene.cameras.find(c => c.id === shot.cameraId) || pickActiveCamera(scene)
      if (!cam) continue
      let suffix = ''
      try {
        const res = await previewScenePrompt(scene, shot)
        suffix = res.prompt_suffix || ''
      } catch {
        // 预览失败退化为纯用户提示词
      }
      const params = buildShotDeriveParams({
        shot,
        camera: cam,
        suffix,
        userPrompt: derivePrompt.value,
        model: deriveModel.value,
        kind: deriveKind.value,
        useCoverAsFirstFrame: deriveUseCover.value,
        aspectRatio: scene.stage.aspect_ratio || undefined,
      })
      const taskId =
        deriveKind.value === 'image' ? queue.submitImageTask(params) : queue.submitVideoTask(params)
      derivedPairs.push({ shotId: shot.id, taskId })
    }
    // 任务 id 回写留痕
    const idByShot = new Map(derivedPairs.map(p => [p.shotId, p.taskId]))
    sceneData.value = {
      ...sceneData.value,
      shots: sceneData.value.shots.map(s => {
        const taskId = idByShot.get(s.id)
        return taskId ? { ...s, derivedTaskIds: [...(s.derivedTaskIds || []), taskId] } : s
      }),
    }
    if (currentId.value) {
      await updateScene(currentId.value, { scene_data: normalizeSceneData(sceneData.value) })
    }
    deriveVisible.value = false
    ElMessage.success(t('scene3d.deriveDone', { n: derivedPairs.length }))
  } catch {
    // 错误已由 client 统一提示
  } finally {
    deriving.value = false
  }
}

// ---------- 工作台级快捷键：[ ] B F ----------
function onKeydown(e: KeyboardEvent) {
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  if (e.key === '[') togglePanel('left')
  else if (e.key === ']') togglePanel('right')
  else if (e.key.toLowerCase() === 'b') togglePanel('dock')
  else if (e.key.toLowerCase() === 'f') toggleFullscreenViewport()
  else if (e.key === 'Escape' && fullscreenViewport.value) fullscreenViewport.value = false
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  loadScenes()
  fetchPreview()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  onDragEnd()
})
</script>

<style scoped>
.scene-workbench {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  min-height: 480px;
  background: var(--agnes-bg-base);
  overflow: hidden;
  position: relative; /* 折叠把手的绝对定位基准 */
}

/* 顶栏 */
.wb-topbar {
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border-bottom: 1px solid var(--agnes-border-faint);
  background: var(--agnes-bg-elevated);
}

.back-btn { flex-shrink: 0; }

.topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--agnes-border);
}

.topbar-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
}

/* 主区 */
.wb-main {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

.wb-aside {
  position: relative;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  overflow: visible;
}

.wb-aside > :first-child {
  flex: 1;
  min-width: 0;
}

.wb-viewport {
  flex: 1;
  min-width: 0;
  display: flex;
}

/* 拖拽手柄 */
.v-grip {
  width: 5px;
  cursor: col-resize;
  flex-shrink: 0;
  background: transparent;
  transition: background 0.15s;
  z-index: 6;
}

.v-grip:hover,
.v-grip:active {
  background: var(--el-color-primary-light-7);
}

.h-grip {
  height: 5px;
  cursor: row-resize;
  flex-shrink: 0;
  transition: background 0.15s;
  z-index: 6;
}

.h-grip:hover,
.h-grip:active {
  background: var(--el-color-primary-light-7);
}

/* 折叠/展开把手 */
.aside-collapse {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--agnes-text-faint);
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  z-index: 7;
}

.aside-collapse:hover { color: var(--agnes-text-primary); }
.aside-collapse.left { right: -9px; border-radius: 0 6px 6px 0; }
.aside-collapse.right { left: -9px; border-radius: 6px 0 0 6px; }

.expand-tab {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--agnes-text-faint);
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  z-index: 7;
}

.expand-tab:hover { color: var(--agnes-text-primary); }
.expand-tab.left { left: 0; border-radius: 0 6px 6px 0; border-left: none; }
.expand-tab.right { right: 0; border-radius: 6px 0 0 6px; border-right: none; }

/* 底部 dock */
.wb-dock {
  position: relative;
  flex-shrink: 0;
  min-height: 0;
  border-top: 1px solid var(--agnes-border-faint);
  display: flex;
}

.dock-collapse {
  position: absolute;
  top: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 44px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--agnes-text-faint);
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-top: none;
  border-radius: 0 0 6px 6px;
  z-index: 7;
}

.dock-collapse:hover { color: var(--agnes-text-primary); }

.expand-tab.dock {
  top: auto;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  height: 18px;
  width: 44px;
  border-radius: 6px 6px 0 0;
  border-bottom: none;
}

/* 状态栏 */
.wb-statusbar {
  height: 24px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 12px;
  font-size: 11px;
  color: var(--agnes-text-faint);
  border-top: 1px solid var(--agnes-border-faint);
  background: var(--agnes-bg-elevated);
}

.status-hint { margin-left: auto; }

.status-saved { color: var(--el-color-success); }

.capture-preview {
  width: 100%;
  border-radius: 6px;
  border: 1px solid var(--agnes-border-light, rgba(255, 255, 255, 0.12));
}
</style>

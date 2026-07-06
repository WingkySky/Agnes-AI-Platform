<!-- =====================================================
     时间线 Tab 主容器 TimelineTab
     - 组合工具栏 + 编辑器 + 属性面板 + 三个对话框
     - 拖拽/裁剪实时维护本地 drafts，结束后批量保存到 store
     - 提供初始化、生成字幕、字幕样式、BGM、合成入口
     ===================================================== -->

<template>
  <div class="timeline-tab">
    <!-- 顶部工具栏 -->
    <TimelineToolbar
      :editable="projectStore.isEditable"
      :has-timeline="hasTimeline"
      :total-duration="totalDuration"
      :whisper-available="projectStore.whisperAvailable"
      :current-bgm="currentBgm"
      :loading="initLoading"
      :subtitle-loading="subtitleLoading"
      :whisper-loading="whisperLoading"
      :merge-loading="projectStore.mergeLoading"
      :merge-progress="projectStore.mergeProgress"
      @init="onInit"
      @generate-subtitles="onGenerateSubtitles"
      @open-subtitle-style="subtitleStyleVisible = true"
      @open-bgm-picker="bgmPickerVisible = true"
      @merge-advanced="onMergeAdvanced"
    />

    <!-- 主体：弹性三区布局（素材库左 + 预览右 + 时间线底部全宽） -->
    <div v-if="hasTimeline" class="timeline-body">
      <!-- 中间行：素材库（左） + 预览（右） -->
      <div class="mid-row" :style="{ height: `calc(100% - ${layout.timelineHeight}px - 10px)` }">
        <!-- 素材库收起时的展开按钮 -->
        <div v-if="layout.libraryHidden" class="library-expand-btn" @click="toggleLibrary">
          <el-icon><Folder /></el-icon>
          <span>展开素材库</span>
        </div>

        <!-- 素材库面板（左侧抽屉） -->
        <div
          v-if="!layout.libraryHidden"
          class="library-container"
          :style="{ width: layout.libraryWidth + 'px' }"
        >
          <MediaLibraryPanel
            :media-library="projectStore.mediaLibrary"
            @hide="toggleLibrary"
            @drag-item="onMediaDragItem"
          />
        </div>

        <!-- 垂直分隔条（拖拽调整素材库宽度） -->
        <TimelineSplitter
          v-if="!layout.libraryHidden"
          direction="vertical"
          :min="180"
          :max="400"
          :model-value="layout.libraryWidth"
          @update:model-value="setLibraryWidth"
        />

        <!-- 预览区：视频画面 + 字幕 overlay + 控件 -->
        <div class="preview-container">
          <TimelinePreview
            :clips="draftClips"
            :subtitle-style="projectStore.subtitleStyle"
            :total-duration="totalDuration"
            :is-playing="preview.isPlaying.value"
            :current-time="preview.currentTime.value"
            :active-video-clip-id="preview.activeVideoClipId.value"
            :active-audio-clip-id="preview.activeAudioClipId.value"
            :active-subtitle-clip-id="preview.activeSubtitleClipId.value"
            :active-subtitle-text="preview.activeSubtitleText.value"
            :subtitle-style-css="preview.subtitleStyleCss.value"
            @register-video="onRegisterVideo"
            @register-audio="onRegisterAudio"
            @toggle-play-pause="preview.togglePlayPause"
            @restart="onRestart"
          />
        </div>
      </div>

      <!-- 水平分隔条（拖拽调整时间线高度） -->
      <TimelineSplitter
        direction="horizontal"
        :min="120"
        :max="maxTimelineHeight"
        :model-value="layout.timelineHeight"
        @update:model-value="setTimelineHeight"
      />

      <!-- 时间线编辑器（底部全宽） -->
      <div class="editor-wrap" :style="{ height: layout.timelineHeight + 'px' }">
        <TimelineEditor
          :clips="draftClips"
          :total-duration="totalDuration"
          :selected-clip-id="selectedClipId"
          :editable="projectStore.isEditable"
          :playhead-time="preview.currentTime.value"
          :active-video-clip-id="preview.activeVideoClipId.value"
          :active-audio-clip-id="preview.activeAudioClipId.value"
          :active-subtitle-clip-id="preview.activeSubtitleClipId.value"
          :can-undo="canUndo"
          :can-redo="canRedo"
          @select-clip="onSelectClip"
          @deselect="onDeselectClip"
          @clip-drag="onClipDrag"
          @clip-trim="onClipTrim"
          @clip-updated="onClipUpdated"
          @play="preview.togglePlayPause"
          @seek="onSeek"
          @split-at-playhead="onSplitAtPlayhead"
          @ripple-delete="onRippleDelete"
          @seek-by-frames="onSeekByFrames"
          @context-menu="onContextMenu"
          @undo="undo"
          @redo="redo"
          @add-clip="addClipDialogVisible = true"
        />
      </div>
    </div>

    <!-- 无时间线时的空状态 -->
    <div v-else class="editor-wrap">
      <el-empty
        v-if="!projectStore.timelineLoading"
        description="暂无时间线数据，请先点击「初始化时间线」"
      >
        <el-button type="primary" :icon="Refresh" @click="onInit">初始化时间线</el-button>
      </el-empty>

      <el-skeleton
        v-else-if="projectStore.timelineLoading"
        :rows="6"
        animated
      />
    </div>

    <!-- 片段属性抽屉（右键菜单选「编辑属性」时弹出，关闭后时间线全宽） -->
    <ClipPropertyPanel
      v-model:visible="clipPanelVisible"
      :clip="selectedClip"
      :editable="projectStore.isEditable"
      @save="onSaveClip"
      @delete="onDeleteClip"
    />

    <!-- 添加片段对话框 -->
    <AddClipDialog
      v-model="addClipDialogVisible"
      :suggested-start-time="preview.currentTime.value"
      @create="onAddClip"
    />

    <!-- 右键上下文菜单 -->
    <ul
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <li class="context-menu-item" @click="onMenuEdit">
        <el-icon><Edit /></el-icon>
        <span>编辑属性</span>
      </li>
      <li class="context-menu-item" @click="onMenuSplit">
        <el-icon><Switch /></el-icon>
        <span>在播放头处分割</span>
        <kbd>Ctrl+K</kbd>
      </li>
      <li class="context-menu-item danger" @click="onMenuRippleDelete">
        <el-icon><Delete /></el-icon>
        <span>波纹删除</span>
        <kbd>Delete</kbd>
      </li>
    </ul>

    <!-- 三个对话框 -->
    <SubtitleStyleDialog
      v-model:visible="subtitleStyleVisible"
      :style="projectStore.subtitleStyle"
    />
    <BgmPickerDialog
      v-model:visible="bgmPickerVisible"
      :default-bgm-id="currentBgmId"
      @confirm="onBgmConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Edit, Switch, Delete, Folder } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useTimelinePreview } from '@/composables/useTimelinePreview'
// Phase 2 增强 — 弹性布局 / 剪贴板 / 标记 / 轨道状态
import { useTimelineLayout } from '@/composables/useTimelineLayout'
import { useClipClipboard } from '@/composables/useClipClipboard'
import { useMarkers } from '@/composables/useMarkers'
import { useTrackStates } from '@/composables/useTrackStates'
import type {
  TimelineClip,
  TimelineClipCreateRequest,
  TransitionType,
  BGMItem,
  MediaLibraryItem,
} from '@/types/project'
import TimelineToolbar from './TimelineToolbar.vue'
import TimelineEditor from './TimelineEditor.vue'
import TimelinePreview from './TimelinePreview.vue'
import ClipPropertyPanel from './ClipPropertyPanel.vue'
import AddClipDialog from './AddClipDialog.vue'
import SubtitleStyleDialog from './SubtitleStyleDialog.vue'
import BgmPickerDialog from './BgmPickerDialog.vue'
// Phase 2 增强 — 素材库面板 / 可拖拽分隔条
import MediaLibraryPanel from './MediaLibraryPanel.vue'
import TimelineSplitter from './TimelineSplitter.vue'

const projectStore = useProjectStore()

// ---------- 本地状态 ----------
const initLoading = ref(false)
const subtitleLoading = ref(false)
const whisperLoading = ref(false)
const subtitleStyleVisible = ref(false)
const bgmPickerVisible = ref(false)

const selectedClipId = ref<number | null>(null)

// 片段草稿（拖拽/裁剪过程实时修改，结束后通过 store 持久化）
const draftClips = ref<TimelineClip[]>([])

// 编辑中标记：拖拽/裁剪进行时为 true，避免 SSE 推送覆盖本地 draft
const isEditing = ref(false)

// ---------- 撤销/重做栈 ----------
// 纯前端快照式：每次结构性操作（create/update/delete/split/ripple）前 push 当前 clips 快照
// 拖拽/裁剪过程中实时产生的中间状态不入栈，只在 onClipUpdated 结束时入栈
const HISTORY_LIMIT = 50
const undoStack = ref<TimelineClip[][]>([])
const redoStack = ref<TimelineClip[][]>([])
const canUndo = computed(() => undoStack.value.length > 0)
const canRedo = computed(() => redoStack.value.length > 0)

// 深拷贝当前 draftClips 入栈（操作前调用，保存"操作前"状态）
function pushHistory() {
  const snapshot = JSON.parse(JSON.stringify(draftClips.value)) as TimelineClip[]
  undoStack.value.push(snapshot)
  if (undoStack.value.length > HISTORY_LIMIT) {
    undoStack.value.shift()
  }
  // 新操作产生后清空 redo 栈（标准撤销/重做语义）
  redoStack.value = []
}

// 撤销：把当前状态压入 redo 栈，恢复 undo 栈顶
async function undo() {
  if (!canUndo.value) return
  // 持久化当前状态到 redo
  const current = JSON.parse(JSON.stringify(draftClips.value)) as TimelineClip[]
  redoStack.value.push(current)
  const prev = undoStack.value.pop()!
  // 本地恢复
  draftClips.value = prev
  selectedClipId.value = null
  clipPanelVisible.value = false
  // 后端同步（保存整盘快照）
  await syncClipsToBackend()
}

// 重做：把当前状态压入 undo 栈，恢复 redo 栈顶
async function redo() {
  if (!canRedo.value) return
  const current = JSON.parse(JSON.stringify(draftClips.value)) as TimelineClip[]
  undoStack.value.push(current)
  const next = redoStack.value.pop()!
  draftClips.value = next
  selectedClipId.value = null
  clipPanelVisible.value = false
  await syncClipsToBackend()
}

// 把当前 draftClips 全量同步到后端（撤销/重做最终落盘）
// 后端 saveTimelineData 端点不支持 clips 字段，这里采用 diff 策略：
// - 删除：服务端存在但本地快照不存在的 clip
// - 更新：两端都存在的 clip 若字段有变则 update
// - 新增：本地快照中 id<0 的临时 clip 走 create
async function syncClipsToBackend() {
  if (!projectStore.currentProjectId) return
  try {
    isEditing.value = true
    const localIds = new Set(draftClips.value.map(c => c.id))
    const serverClips = projectStore.timelineData?.clips ?? []
    // 删除：服务端有但本地没有的
    for (const sc of serverClips) {
      if (!localIds.has(sc.id)) {
        await projectStore.deleteTimelineClip(sc.id)
      }
    }
    // 更新与新增
    for (const c of draftClips.value) {
      if (c.id < 0) {
        // 新增（撤销删除场景：临时 id 重新创建）
        await projectStore.createTimelineClip({
          track_type: c.track_type,
          track_index: c.track_index,
          source_type: c.source_type ?? undefined,
          source_id: c.source_id ?? undefined,
          shot_id: c.shot_id ?? undefined,
          start_time: c.start_time,
          duration: c.duration,
          trim_start: c.trim_start,
          trim_end: c.trim_end ?? undefined,
          transition_type: c.transition_type,
          transition_duration: c.transition_duration,
          subtitle_text: c.subtitle_text ?? undefined,
          sort_order: c.sort_order,
        })
      } else {
        // 更新（仅传可能变化的字段）
        await projectStore.updateTimelineClip(c.id, {
          start_time: c.start_time,
          duration: c.duration,
          trim_start: c.trim_start,
          trim_end: c.trim_end ?? undefined,
          transition_type: c.transition_type,
          transition_duration: c.transition_duration,
          subtitle_text: c.subtitle_text ?? undefined,
          sort_order: c.sort_order,
        })
      }
    }
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.message || '未知错误'))
  } finally {
    isEditing.value = false
  }
}

// BGM 选中状态
const currentBgmId = ref<string | null>(null)
const currentBgm = ref<BGMItem | null>(null)

// 片段属性抽屉显示状态
const clipPanelVisible = ref(false)

// 添加片段对话框显示状态
const addClipDialogVisible = ref(false)

// 右键上下文菜单状态
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  clipId: null as number | null,
})

// ---------- 计算 ----------
const hasTimeline = computed(() => (projectStore.timelineData?.clips?.length ?? 0) > 0)

const totalDuration = computed(() => projectStore.timelineData?.total_duration ?? 0)

const selectedClip = computed(() =>
  draftClips.value.find((c) => c.id === selectedClipId.value) ?? null,
)

// store.timelineData.clips 变化时同步到本地 drafts
// 编辑中（拖拽/裁剪）不同步，避免 SSE 推送覆盖正在修改的 draft
watch(
  () => projectStore.timelineData?.clips,
  (clips) => {
    if (isEditing.value) return
    draftClips.value = clips ? clips.map((c) => ({ ...c })) : []
  },
  { immediate: true },
)

// ---------- 预览调度 ----------
const preview = useTimelinePreview({
  clips: computed(() => draftClips.value),
  subtitleStyle: computed(() => projectStore.subtitleStyle),
  totalDuration,
})

// ---------- Phase 2 增强：弹性布局 / 剪贴板 / 标记 / 轨道状态 ----------
// 弹性布局（按 projectId 持久化到 localforage）
const projectIdRef = computed(() => projectStore.currentProjectId)
const {
  layout,
  toggleLibrary,
  setLibraryWidth,
  setTimelineHeight,
} = useTimelineLayout(projectIdRef)

// 剪贴板（内存级，复制/剪切/粘贴）
const clipboard = useClipClipboard()

// 标记（依赖 preview.currentTime，必须放在 preview 之后）
const {
  markers,
  addMarkerAtPlayhead,
  deleteNearestMarker,
  jumpToPrevMarker,
  jumpToNextMarker,
} = useMarkers(
  preview.currentTime,
  (t: number) => preview.seek(t),
)

// 轨道状态（Mute / Lock，按 projectId 持久化到 localforage）
const {
  toggleMuted: toggleTrackMuted,
  toggleLocked: toggleTrackLocked,
  loadTrackStates,
} = useTrackStates(projectIdRef)

// 时间线高度上限：视口高度的 60%（template 中绑定用）
const maxTimelineHeight = computed(() => Math.floor(window.innerHeight * 0.6))

// ---------- 预览元素注册转发 ----------
function onRegisterVideo(clipId: number, el: HTMLVideoElement | null) {
  preview.registerVideoEl(clipId, el)
}

function onRegisterAudio(clipId: number, el: HTMLAudioElement | null) {
  preview.registerAudioEl(clipId, el)
}

function onRestart() {
  preview.stop()
}

// ---------- 初始化 ----------
onMounted(async () => {
  if (!projectStore.currentProjectId) return
  // 首次进入时拉取时间线数据 + Whisper 可用性
  await Promise.all([
    projectStore.fetchTimelineData(),
    projectStore.fetchWhisperAvailable(),
  ])
  // Phase 2 增强：加载素材库 + 标记 + 轨道状态
  await Promise.all([
    projectStore.fetchMediaLibrary(),
    projectStore.fetchMarkers(),
  ])
  await loadTrackStates()
  // 注册全局键盘快捷键
  window.addEventListener('keydown', onKeyDown)
  // 点击页面其他位置关闭右键菜单
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('click', onDocumentClick)
})

// ---------- 键盘快捷键 ----------
// Space: 播放/暂停
// Ctrl+K / Cmd+K: 在播放头处分割选中片段
// Delete / Backspace: 波纹删除选中片段
// 左/右方向键: 帧步进 ±1
// Ctrl+C / Ctrl+X / Ctrl+V: 复制 / 剪切 / 粘贴片段
// Ctrl+M: 在播放头添加标记；Shift+Ctrl+M: 删除最近标记
// [ / ]: 跳到上一 / 下一标记
async function onKeyDown(e: KeyboardEvent) {
  // 输入控件聚焦时让浏览器处理
  const target = e.target as HTMLElement | null
  if (target && /INPUT|TEXTAREA|SELECT/.test(target.tagName)) return
  if (target?.isContentEditable) return

  const cmd = e.ctrlKey || e.metaKey

  // Ctrl+K 分割
  if (cmd && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    onSplitAtPlayhead()
    return
  }

  // Ctrl+Z 撤销 / Ctrl+Shift+Z 重做（Mac 用 Cmd+Shift+Z）
  if (cmd && (e.key === 'z' || e.key === 'Z')) {
    e.preventDefault()
    if (e.shiftKey) {
      redo()
    } else {
      undo()
    }
    return
  }

  // Ctrl+Y 重做（Windows 习惯）
  if (cmd && (e.key === 'y' || e.key === 'Y')) {
    e.preventDefault()
    redo()
    return
  }

  // Phase 2 增强：复制 / 剪切 / 粘贴
  if (cmd && (e.key === 'c' || e.key === 'C')) {
    if (selectedClipId.value != null) {
      const clip = draftClips.value.find((c) => c.id === selectedClipId.value)
      if (clip) {
        e.preventDefault()
        clipboard.copy(clip)
        ElMessage.success('已复制')
      }
    }
    return
  }
  if (cmd && (e.key === 'x' || e.key === 'X')) {
    if (selectedClipId.value != null) {
      const clip = draftClips.value.find((c) => c.id === selectedClipId.value)
      if (clip) {
        e.preventDefault()
        pushHistory()
        await clipboard.cut(clip)
        ElMessage.success('已剪切')
        if (selectedClipId.value === clip.id) {
          selectedClipId.value = null
          clipPanelVisible.value = false
        }
      }
    }
    return
  }
  if (cmd && (e.key === 'v' || e.key === 'V')) {
    if (clipboard.hasContent.value) {
      e.preventDefault()
      pushHistory()
      await clipboard.paste(preview.currentTime.value)
      ElMessage.success('已粘贴')
    }
    return
  }

  // Phase 2 增强：Ctrl+M 添加标记 / Shift+Ctrl+M 删除最近标记
  if (cmd && (e.key === 'm' || e.key === 'M')) {
    e.preventDefault()
    if (e.shiftKey) {
      await deleteNearestMarker()
    } else {
      await addMarkerAtPlayhead()
    }
    return
  }

  // Phase 2 增强：[ / ] 跳到上一 / 下一标记
  if (e.key === '[') {
    e.preventDefault()
    jumpToPrevMarker()
    return
  }
  if (e.key === ']') {
    e.preventDefault()
    jumpToNextMarker()
    return
  }

  switch (e.key) {
    case ' ': {
      e.preventDefault()
      preview.togglePlayPause()
      break
    }
    case 'Delete':
    case 'Backspace': {
      if (selectedClipId.value == null) return
      e.preventDefault()
      onRippleDelete()
      break
    }
    case 'ArrowLeft': {
      e.preventDefault()
      preview.seekBy(e.shiftKey ? -10 : -1)
      break
    }
    case 'ArrowRight': {
      e.preventDefault()
      preview.seekBy(e.shiftKey ? 10 : 1)
      break
    }
    case 'Escape': {
      if (contextMenu.visible) {
        e.preventDefault()
        closeContextMenu()
      }
      break
    }
  }
}

// ---------- 工具栏事件 ----------
async function onInit() {
  try {
    await ElMessageBox.confirm(
      '初始化将根据当前分镜的活跃视频/音频/字幕重新生成时间线，已有手动调整可能被覆盖，是否继续？',
      '初始化时间线',
      { type: 'warning', confirmButtonText: '初始化', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  initLoading.value = true
  try {
    await projectStore.initTimeline()
    ElMessage.success('时间线已初始化')
  } catch (e: any) {
    ElMessage.error(e?.message || '初始化失败')
  } finally {
    initLoading.value = false
  }
}

async function onGenerateSubtitles(mode: 'llm' | 'whisper') {
  const loading = mode === 'whisper' ? whisperLoading : subtitleLoading
  loading.value = true
  try {
    const result = mode === 'whisper'
      ? await projectStore.generateSubtitlesWithWhisper({})
      : await projectStore.generateSubtitles({})
    ElMessage.success(`已生成 ${result.count} 条字幕（${result.mode} 模式）`)
    // 重新拉取时间线以反映字幕片段
    await projectStore.fetchTimelineData()
  } catch (e: any) {
    ElMessage.error(e?.message || '生成字幕失败')
  } finally {
    loading.value = false
  }
}

async function onMergeAdvanced() {
  try {
    await ElMessageBox.confirm(
      '将基于当前时间线进行多轨合成（视频 + 音频 + 字幕 + BGM），是否继续？',
      '合成视频',
      { type: 'info', confirmButtonText: '开始合成', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.mergeProjectAdvanced({
      with_audio: true,
      with_subtitle: true,
      with_bgm: !!currentBgmId.value,
      bgm_id: currentBgmId.value || undefined,
      use_timeline: true,
    })
    ElMessage.success('合成任务已提交，请在合成状态中查看进度')
  } catch (e: any) {
    ElMessage.error(e?.message || '合成失败')
  }
}

function onBgmConfirm(bgmId: string | null, bgm: BGMItem | null) {
  currentBgmId.value = bgmId
  currentBgm.value = bgm
  if (bgmId) {
    ElMessage.success(`已选择 BGM：${bgm?.name || bgmId}`)
  } else {
    ElMessage.info('已清除 BGM 选择')
  }
}

// ---------- 编辑器事件 ----------
function onSelectClip(clipId: number) {
  // 左键单击只选中片段，不自动弹出属性抽屉
  // 属性抽屉通过右键菜单的「编辑属性」项触发
  selectedClipId.value = clipId
}

function onDeselectClip() {
  selectedClipId.value = null
  clipPanelVisible.value = false
  closeContextMenu()
}

function onSeekByFrames(deltaFrames: number) {
  preview.seekBy(deltaFrames)
}

// ---------- 右键上下文菜单 ----------
function onContextMenu(clipId: number, x: number, y: number) {
  // 右键即选中该片段（用于后续菜单操作作用对象明确）
  selectedClipId.value = clipId
  // 边界修正：菜单靠右/靠下溢出时往左/往上偏移
  const menuWidth = 200
  const menuHeight = 140
  const adjustedX = Math.min(x, window.innerWidth - menuWidth - 8)
  const adjustedY = Math.min(y, window.innerHeight - menuHeight - 8)
  contextMenu.visible = true
  contextMenu.x = adjustedX
  contextMenu.y = adjustedY
  contextMenu.clipId = clipId
}

function closeContextMenu() {
  contextMenu.visible = false
  contextMenu.clipId = null
}

// 菜单项：编辑属性 → 弹出抽屉
function onMenuEdit() {
  clipPanelVisible.value = true
  closeContextMenu()
}

// 菜单项：在播放头处分割
function onMenuSplit() {
  closeContextMenu()
  onSplitAtPlayhead()
}

// 菜单项：波纹删除
function onMenuRippleDelete() {
  closeContextMenu()
  onRippleDelete()
}

// 点击页面其他位置关闭右键菜单
function onDocumentClick() {
  if (contextMenu.visible) closeContextMenu()
}

function onClipDrag(clipId: number, deltaSeconds: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return
  isEditing.value = true
  clip.start_time = Math.max(0, clip.start_time + deltaSeconds)
}

function onClipTrim(clipId: number, side: 'left' | 'right', deltaSeconds: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return
  isEditing.value = true
  // 源素材总时长（秒），用于边界校验；缺失时视为无限制
  const sourceDur = clip.source_duration_ms ? clip.source_duration_ms / 1000 : Infinity
  if (side === 'left') {
    // 左侧裁剪：trim_start 增加，duration 减少，start_time 增加
    const newTrim = Math.max(0, clip.trim_start + deltaSeconds)
    // 边界：trim_start 不能超过源素材时长 - 最小保留 0.1s
    const maxTrim = Math.max(0, sourceDur - 0.1) - clip.duration
    const clampedTrim = Math.min(newTrim, Math.max(0, maxTrim))
    const actualDelta = clampedTrim - clip.trim_start
    clip.trim_start = clampedTrim
    clip.duration = Math.max(0.1, clip.duration - actualDelta)
    clip.start_time = Math.max(0, clip.start_time + actualDelta)
  } else {
    // 右侧裁剪：duration 调整，不能超过源素材剩余可用时长
    const remaining = sourceDur === Infinity ? Infinity : sourceDur - clip.trim_start
    const newDuration = Math.max(0.1, clip.duration + deltaSeconds)
    clip.duration = Math.min(newDuration, remaining)
  }
}

async function onClipUpdated(clipId: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) {
    isEditing.value = false
    return
  }
  // 拖拽/裁剪结束提交保存前入栈（保存操作前状态）
  pushHistory()
  try {
    await projectStore.updateTimelineClip(clipId, {
      start_time: clip.start_time,
      duration: clip.duration,
      trim_start: clip.trim_start,
      trim_end: clip.trim_end ?? undefined,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '保存片段失败')
    // 失败时撤销本地状态并回滚到 store 数据
    undoStack.value.pop()
    await projectStore.fetchTimelineData()
  } finally {
    isEditing.value = false
  }
}

async function onSaveClip(clipId: number, data: Partial<TimelineClip>) {
  pushHistory()
  try {
    // 构造符合 TimelineClipUpdateRequest 形状的 payload（trim_end 不允许 null）
    const payload = {
      start_time: data.start_time,
      duration: data.duration,
      trim_start: data.trim_start,
      trim_end: data.trim_end ?? undefined,
      transition_type: data.transition_type,
      transition_duration: data.transition_duration,
      subtitle_text: data.subtitle_text ?? undefined,
    }
    await projectStore.updateTimelineClip(clipId, payload)
    ElMessage.success('片段属性已保存')
    // 同步本地 draft
    const idx = draftClips.value.findIndex((c) => c.id === clipId)
    if (idx >= 0) {
      draftClips.value[idx] = { ...draftClips.value[idx], ...data } as TimelineClip
    }
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '保存失败')
  }
}

async function onDeleteClip(clipId: number) {
  try {
    await ElMessageBox.confirm('确定删除该片段？可通过撤销恢复（Ctrl+Z）。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch (_) { return }

  pushHistory()
  try {
    await projectStore.deleteTimelineClip(clipId)
    ElMessage.success('片段已删除')
    if (selectedClipId.value === clipId) {
      selectedClipId.value = null
      clipPanelVisible.value = false
    }
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '删除失败')
  }
}

// 在播放头处分割当前选中片段
// 播放头时间必须落在选中片段的 [start_time, start_time+duration) 范围内
async function onSplitAtPlayhead() {
  const clipId = selectedClipId.value
  if (clipId == null) {
    ElMessage.warning('请先选择一个片段')
    return
  }
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return

  const playhead = preview.currentTime.value
  const clipStart = clip.start_time
  const clipEnd = clip.start_time + clip.duration
  // 边界容差 0.05s，避免端点不可分割
  const tolerance = 0.05
  if (playhead < clipStart + tolerance || playhead > clipEnd - tolerance) {
    ElMessage.warning('播放头不在选中片段范围内，无法分割')
    return
  }

  pushHistory()
  try {
    await projectStore.splitTimelineClip(clipId, playhead)
    ElMessage.success('片段已分割')
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '分割失败')
  }
}

// 波纹删除当前选中片段
async function onRippleDelete() {
  const clipId = selectedClipId.value
  if (clipId == null) {
    ElMessage.warning('请先选择一个片段')
    return
  }
  pushHistory()
  try {
    await projectStore.rippleDeleteTimelineClip(clipId)
    ElMessage.success('片段已波纹删除')
    if (selectedClipId.value === clipId) {
      selectedClipId.value = null
      clipPanelVisible.value = false
    }
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '波纹删除失败')
  }
}

// 添加片段（从对话框创建）
async function onAddClip(data: TimelineClipCreateRequest) {
  pushHistory()
  try {
    await projectStore.createTimelineClip(data)
    ElMessage.success('片段已添加')
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '添加失败')
  }
}

function onPlay() {
  // 预览播放/暂停由 composable 处理（通过模板 @play="preview.togglePlayPause" 绑定）
  // 此函数保留为空，仅用于兼容旧 emit 调用
}

function onSeek(t: number) {
  // 拖拽播放头/点击标尺时跳转预览到指定时间
  preview.seek(t)
}

// ---------- Phase 2 增强：素材库拖拽 / 轨道状态 / 标记事件 ----------

// 素材库开始拖拽时回调（数据已写入 dataTransfer，此处仅做信息钩子）
function onMediaDragItem(_item: MediaLibraryItem) {
  // drop 由 TimelineTrack 接收并触发 onDropMedia（Task 14 接入）
}

// 拖拽素材到时间线轨道 → 创建新片段
// Task 14 将由 TimelineEditor 透传 drop-media 事件到此
async function onDropMedia(
  item: MediaLibraryItem,
  trackType: string,
  trackIndex: number,
  startTime: number,
) {
  pushHistory()
  try {
    const payload: TimelineClipCreateRequest = {
      track_type: trackType as TimelineClip['track_type'],
      track_index: trackIndex,
      start_time: startTime,
      duration: item.duration_ms / 1000,
      trim_start: 0,
      transition_type: 'none' as TransitionType,
      transition_duration: 0,
      sort_order: 0,
    }
    if (item.type === 'shot_video' || item.type === 'shot_frame_image') {
      payload.source_type = item.type
      payload.source_id = item.id
      payload.shot_id = item.shot_id ?? undefined
    } else if (item.type === 'shot_audio') {
      payload.source_type = 'shot_audio'
      payload.source_id = item.id
      payload.shot_id = item.shot_id ?? undefined
    } else if (item.type === 'bgm') {
      payload.source_type = 'bgm'
      payload.source_ref = item.meta?.bgm_id
    }
    await projectStore.createTimelineClip(payload)
    ElMessage.success('已添加片段到时间线')
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '添加失败')
  }
}

// 轨道静音切换（M 按钮）
function onToggleTrackMute(trackType: string, trackIndex: number) {
  toggleTrackMuted(trackType, trackIndex)
}

// 轨道锁定切换（L 按钮）
function onToggleTrackLock(trackType: string, trackIndex: number) {
  toggleTrackLocked(trackType, trackIndex)
}

// 标记删除（右键旗帜删除）
async function onMarkerDelete(markerId: number) {
  try {
    await projectStore.removeMarker(markerId)
    ElMessage.success('标记已删除')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除标记失败')
  }
}
</script>

<style scoped>
.timeline-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* Phase 2 增强：弹性三区布局 */
.timeline-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.mid-row {
  display: flex;
  min-height: 0;
}

/* 素材库收起时的展开按钮（左侧边缘竖条） */
.library-expand-btn {
  width: 24px;
  background: var(--el-fill-color-light, #2a2d34);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  font-size: 10px;
  padding: 8px 2px;
  border-right: 1px solid var(--el-border-color-light, #3a3d44);
  transition: background-color 0.15s;
}

.library-expand-btn:hover {
  background: var(--el-color-primary-light-9, #3a4eff20);
  color: var(--el-color-primary);
}

/* 素材库面板容器（左侧抽屉） */
.library-container {
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
}

/* 预览区容器（右侧） */
.preview-container {
  flex: 1;
  min-width: 0;
  height: 100%;
}

.editor-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

/* timeline-body 内的 editor-wrap：高度由 inline style 控制，不参与 flex 分配 */
.timeline-body > .editor-wrap {
  flex: none;
}

/* 右键上下文菜单 */
.context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 180px;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 6px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
  margin: 0;
  list-style: none;
  user-select: none;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
  cursor: pointer;
  transition: background-color 0.15s;
}

.context-menu-item:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}

.context-menu-item.danger {
  color: var(--el-color-danger, #f56c6c);
}

.context-menu-item.danger:hover {
  background: var(--el-color-danger-light-9, #fef0f0);
}

.context-menu-item .el-icon {
  font-size: 14px;
}

.context-menu-item span {
  flex: 1;
}

.context-menu-item kbd {
  font-size: 11px;
  color: var(--el-text-color-placeholder, #a8abb2);
  background: var(--el-fill-color, #f5f7fa);
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 3px;
  padding: 1px 5px;
  font-family: 'Menlo', monospace;
}
</style>

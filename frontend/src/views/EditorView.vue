<script setup lang="ts">
/* =====================================================
 * 剪辑器（/editor/:uid）— 宿主唯一入口
 * 布局：顶栏 / 上排=左素材+中预览+右属性 / 下排=时间线全宽通底
 * 所有区域直读 editor store，不层层传 props
 * ===================================================== */

import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, Download, Edit, Loading, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { Ref } from 'vue'

import EditorAssets from '@/views/editor/EditorAssets.vue'
import EditorPreview from '@/views/editor/EditorPreview.vue'
import EditorTimeline from '@/views/editor/EditorTimeline.vue'
import EditorInspector from '@/views/editor/EditorInspector.vue'
import EditorHistoryDialog from '@/views/editor/EditorHistoryDialog.vue'
import { useEditorStore } from '@/stores/editor'
import { useChatStore } from '@/stores/chat'
import { startBridgeClient, BRIDGE_EDITOR_TOOLS } from '@/lib/agent/bridge'
import type { BridgeClientHandle } from '@/lib/agent/bridge'
import { toolStepLabel } from '@/lib/agent/tool-labels'
import { EDITOR_TOOLS } from '@/lib/agent/editor-tools'
import { updateEditorProject, exportFinal, exportJianyingDraft } from '@/api/editor'
import { useRename } from '@/composables/useRename'
import { useUserStore } from '@/stores/user'
import { clipEnd, sourceSpan, type EditorClip } from '@/lib/editor-types'
import { ensureThumbs, thumbKey } from '@/lib/editor-strips'
import { registerEditorBridge, unregisterEditorBridge, editorRefTimecode } from '@/lib/agent/editor-bridge'
import { useI18n } from '@/i18n'

const route = useRoute()
const router = useRouter()
const store = useEditorStore()
const chatStore = useChatStore()

// 反向控制桥执行者句柄（onMounted 启动、onBeforeUnmount 停止）
let editorBridge: BridgeClientHandle | null = null
// Agent 跨页操作徽标状态：亮灭与内容由桥客户端 onActivity 驱动（并发计数在桥内）
const bridgeBadge = reactive({ on: false, label: '' })
const { rename } = useRename()
const { t } = useI18n()
const userStore = useUserStore()

const canRender = computed(() =>
  !!store.doc && store.doc.clips.some((c) => c.assetId != null),
)

const totalDuration = computed(() => {
  if (!store.doc) return 0
  return Math.max(1, ...store.doc.clips.map(clipEnd))
})

const saveLabel = computed(() => {
  if (store.saving) return t('editor.saving')
  if (store.dirty) return t('editor.unsaved')
  if (store.lastSavedAt) return t('editor.saved')
  return ''
})

// ---------- 渲染质检（报告由渲染收尾自动生成；徽标点击开详情，条目点击跳播放头） ----------
const qualityOpen = ref(false)
const suspectCount = computed(() => (store.qualityReport?.issues ?? []).filter((i) => i.suspect).length)

function seekToIssue(start: number): void {
  store.playhead = Math.max(0, start)
  qualityOpen.value = false
}

// ---------- 导出（下拉：设置/GIF/音频/剪映草稿；设置弹窗写入 setDocumentMeta op） ----------
const exportOpen = ref(false)
const historyOpen = ref(false)

const EXPORT_PRESETS = [
  { key: 'vertical', width: 1080, height: 1920 },
  { key: 'landscape720', width: 1280, height: 720 },
  { key: 'landscape1080', width: 1920, height: 1080 },
  { key: 'square', width: 1080, height: 1080 },
] as const

const expWidth = ref(1280)
const expHeight = ref(720)
const expFps = ref(30)

function openExportSettings(): void {
  expWidth.value = store.doc?.width ?? 1280
  expHeight.value = store.doc?.height ?? 720
  expFps.value = store.doc?.timebase ?? 30
  exportOpen.value = true
}

function applyExportSettings(): void {
  const ok = store.applyOrToast(
    { op: 'setDocumentMeta', payload: { width: expWidth.value, height: expHeight.value, timebase: expFps.value } },
    t('editor.ops.setDocumentMeta'),
  )
  if (ok) {
    exportOpen.value = false
    ElMessage.success(t('editor.exportApplied'))
  }
}

/** 导出下拉命令：GIF/音频走成片后处理（blob 下载带鉴权），剪映草稿同理 */
async function onExportCommand(command: string): Promise<void> {
  if (command === 'settings') return openExportSettings()
  if (command === 'history') return void (historyOpen.value = true)
  try {
    if (command === 'jianying') {
      ElMessage.info(t('editor.exportStarted'))
      const blob = await exportJianyingDraft(store.uid)
      downloadBlob(blob, `${store.title || 'draft'}.zip`)
    } else {
      if (!store.finalUrl) {
        ElMessage.warning(t('editor.exportNoFinal'))
        return
      }
      ElMessage.info(t('editor.exportStarted'))
      const blob = await exportFinal(store.uid, { format: command as 'gif' | 'audio' })
      downloadBlob(blob, `${store.title || 'export'}.${command === 'gif' ? 'gif' : 'm4a'}`)
    }
    ElMessage.success(t('editor.exportDone'))
  } catch (e) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('editor.exportFailed'))
  }
}

function downloadBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

function goBack(): void {
  if (store.workId) router.push(`/works/${store.workId}`)
  else if (window.history.length > 1) router.back()
  else router.push('/works')
}

async function renameProject(): Promise<void> {
  if (!store.uid) return
  const name = await rename(store.title || '')
  if (!name) return
  await updateEditorProject(store.uid, { title: name })
  store.title = name
  ElMessage.success(t('common.renameDone'))
}

// ---------- 选区引用桥（Agent 输入区「引用选中」/ Ctrl+Shift+L 取此处上下文） ----------

/** 片段缩略图（时间线帧缓存取中点帧，未就绪短等一次；失败静默降级无图） */
async function clipThumbDataUrl(url: string, clip: EditorClip): Promise<string | undefined> {
  let handle = ensureThumbs(url, clip, () => {})
  if (!handle) {
    await new Promise((r) => setTimeout(r, 200))
    handle = ensureThumbs(url, clip, () => {})
  }
  if (!handle) return undefined
  const key = thumbKey(Math.max(0, clip.trimStart) + sourceSpan(clip) / 2)
  let bmp = handle.frames.get(key)
  if (!bmp) {
    await new Promise((r) => setTimeout(r, 500))
    bmp = handle.frames.get(key)
  }
  if (!bmp) return undefined
  const canvas = document.createElement('canvas')
  canvas.width = 160
  canvas.height = 90
  const ctx = canvas.getContext('2d')
  if (!ctx) return undefined
  const scale = Math.max(160 / bmp.width, 90 / bmp.height)
  const sw = 160 / scale
  const sh = 90 / scale
  ctx.drawImage(bmp, (bmp.width - sw) / 2, (bmp.height - sh) / 2, sw, sh, 0, 0, 160, 90)
  return canvas.toDataURL('image/jpeg', 0.7)
}

async function buildClipRef(clipId: string) {
  const clip = store.doc?.clips.find((c) => c.id === clipId)
  if (!clip || !store.uid) return null
  let assetName: string | undefined
  let thumb: string | undefined
  if (clip.assetId != null) {
    const asset = await store.fetchAsset(clip.assetId)
    if (asset) {
      assetName = asset.name
      if (asset.media_type === 'video') thumb = await clipThumbDataUrl(asset.asset_url, clip)
    }
  }
  const track = store.doc?.tracks.find((tr) => tr.id === clip.trackId)
  const name = clip.text?.trim() || assetName || clipId
  const start = Math.round(clip.start * 1000) / 1000
  const end = Math.round((clip.start + clip.duration) * 1000) / 1000
  return {
    kind: 'clip' as const,
    projectId: store.uid,
    clipId: clip.id,
    trackId: clip.trackId,
    assetId: clip.assetId,
    assetName,
    trackKind: track?.kind,
    start,
    end,
    label: `${name} ${editorRefTimecode(start)}-${editorRefTimecode(end)}`,
    ...(thumb ? { thumb } : {}),
  }
}

function buildTrackRef(trackId: string) {
  const track = store.doc?.tracks.find((tr) => tr.id === trackId)
  if (!track || !store.uid) return Promise.resolve(null)
  return Promise.resolve({
    kind: 'track' as const,
    projectId: store.uid,
    trackId: track.id,
    trackKind: track.kind,
    label: `${trackId}（${t(`editor.trackKinds.${track.kind}`)}）`,
  })
}

// ---------- 可拖拽分隔条（面板尺寸本地持久化，刷新恢复） ----------

const LAYOUT_KEY = 'agnes_editor_layout'

interface PanelLayout { assetsW: number; inspectorW: number; topH: number }

function readLayout(): PanelLayout | null {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY)
    if (!raw) return null
    const l: PanelLayout = JSON.parse(raw)
    if (![l.assetsW, l.inspectorW, l.topH].every((v) => Number.isFinite(v))) return null
    return l
  } catch {
    return null
  }
}

const bodyEl = ref<HTMLElement | null>(null)
const saved = readLayout()
const assetsW = ref(Math.min(480, Math.max(160, saved?.assetsW ?? 208)))
const inspectorW = ref(Math.min(480, Math.max(160, saved?.inspectorW ?? 240)))
/** 上排高度（px）；0 = 未定制，回退 CSS 44%（哨兵 0 不能被最小值钳掉，否则新会话永远是最小高度） */
const topH = ref(saved?.topH ? Math.max(240, saved.topH) : 0)

function persistLayout(): void {
  if (!topH.value) return
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ assetsW: assetsW.value, inspectorW: inspectorW.value, topH: topH.value }))
  } catch { /* 存储不可用时忽略 */ }
}

function startDrag(e: PointerEvent, move: (dx: number, dy: number) => void): void {
  e.preventDefault()
  const startX = e.clientX
  const startY = e.clientY
  const onMove = (ev: PointerEvent): void => move(ev.clientX - startX, ev.clientY - startY)
  const up = (): void => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', up)
    persistLayout()
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', up)
}

/** 纵向分隔条：dir=1 拖右变宽（素材），dir=-1 拖左变宽（属性） */
function dragPanelW(e: PointerEvent, target: Ref<number>, dir: 1 | -1): void {
  const start = target.value
  startDrag(e, (dx) => { target.value = Math.min(480, Math.max(160, start + dir * dx)) })
}

function dragAssetsW(e: PointerEvent): void {
  dragPanelW(e, assetsW, 1)
}

function dragInspectorW(e: PointerEvent): void {
  dragPanelW(e, inspectorW, -1)
}

function dragTopH(e: PointerEvent): void {
  const bodyH = bodyEl.value?.clientHeight ?? 720
  const start = topH.value || Math.round(bodyH * 0.44)
  startDrag(e, (_dx, dy) => {
    topH.value = Math.min(Math.max(start + dy, 240), Math.max(bodyH - 260, 240))
  })
}

async function ensureLoaded(): Promise<void> {
  const uid = String(route.params.uid || '')
  if (!uid) return
  if (store.uid !== uid) {
    store.reset()
    try {
      await store.load(uid)
    } catch {
      ElMessage.error(t('editor.loadFailed'))
      goBack()
    }
  }
}

function onKeydown(e: KeyboardEvent): void {  const target = e.target as HTMLElement
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  const mod = e.ctrlKey || e.metaKey
  if (e.code === 'Space') {
    e.preventDefault()
    store.isPlaying = !store.isPlaying
  } else if (e.key === 'Escape' && store.previewingAsset) {
    e.preventDefault()
    store.endAssetPreview()
  } else if (e.key === 'Escape') {
    if (store.selectedClipId || store.selectedTrackId) {
      e.preventDefault()
      store.select(null)
      store.selectTrack(null)
    }
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    if (store.selectedClipId) {
      e.preventDefault()
      store.applyOrToast({ op: 'removeClip', payload: { clipId: store.selectedClipId } }, t('editor.ops.removeClip'))
    } else if (store.selectedTrackId) {
      // 轨非空时命令层拒绝并 toast（track_not_empty）
      e.preventDefault()
      store.applyOrToast({ op: 'removeTrack', payload: { trackId: store.selectedTrackId } }, t('editor.ops.removeTrack'))
    }
  } else if ((e.key === 'b' || e.key === 'B') && mod) {
    e.preventDefault()  // 分割（剪映 Ctrl+B / Premiere Ctrl+K 惯例）
    store.splitSelectedAtPlayhead()
  } else if ((e.key === 'c' || e.key === 'C') && mod && store.selectedClipId) {
    e.preventDefault()  // 复制片段到尾部
    void store.duplicateClip(store.selectedClipId)
  } else if (e.key === 'Home') {
    e.preventDefault()
    store.playhead = 0
  } else if (e.key === 'End') {
    e.preventDefault()
    store.playhead = store.doc ? Math.max(0, ...store.doc.clips.map(clipEnd)) : 0
  } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !mod) {
    e.preventDefault()
    const step = e.shiftKey ? 1 : 1 / (store.doc?.timebase || 30)
    store.playhead = Math.max(0, store.playhead + (e.key === 'ArrowRight' ? step : -step))
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault()
    if (e.shiftKey) store.redo()
    else store.undo()
  }
}

onMounted(() => {
  if (!userStore.isAuthenticated) {
    router.push('/login')
    return
  }
  void ensureLoaded()
  store.startRemotePoll()
  // Agent scope 注册（批次 2 反向控制桥路由元数据；editor_* 工具本身常驻）
  chatStore.registerAgentScope({ host: 'editor', projectId: String(route.params.uid || '') })
  // 选区引用桥：Agent 输入区「引用选中」/ Ctrl+Shift+L 取当前选中与播放头
  registerEditorBridge({
    uid: String(route.params.uid || ''),
    getRefContext: () => (store.loaded && store.uid ? {
      projectId: store.uid,
      selectedClipId: store.selectedClipId,
      selectedTrackId: store.selectedTrackId,
      playhead: store.playhead,
      buildClipRef,
      buildTrackRef,
    } : null),
  })
  // 反向控制桥：本页注册为剪辑工程执行者（跨页 Agent 排时间线实时可见）
  editorBridge = startBridgeClient({
    host: 'editor',
    getTargetId: () => store.uid || '',
    executors: Object.fromEntries(
      EDITOR_TOOLS
        .filter((t) => (BRIDGE_EDITOR_TOOLS as readonly string[]).includes(t.name))
        .map((t) => [t.name, (args: Record<string, unknown>) => t.execute(args)]),
    ),
    onActivity: (active, tool, args) => {
      if (active) {
        bridgeBadge.label = toolStepLabel(tool, args)
        bridgeBadge.on = true
      } else {
        bridgeBadge.on = false
      }
    },
  })
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  chatStore.unregisterAgentScope('editor')
  unregisterEditorBridge()
  editorBridge?.stop()
  editorBridge = null
  store.stopRemotePoll()
  void store.saveNow()
  store.reset()
})
</script>

<template>
  <div class="editor-page">
    <header class="editor-topbar">
      <el-button :icon="ArrowLeft" text @click="goBack">{{ t('common.back') }}</el-button>
      <span class="editor-title" :title="store.title" @click="renameProject">{{ store.title || t('editor.title') }}</span>
      <el-button :icon="Edit" text size="small" :title="t('common.rename')" @click="renameProject" />
      <div class="topbar-actions">
        <span class="save-state">{{ saveLabel }}</span>
        <el-tag v-if="store.renderStatus === 'rendering'" type="warning" size="small">
          {{ t('editor.rendering') }} {{ store.renderProgress || '' }}
        </el-tag>
        <el-tag v-else-if="store.renderStatus === 'failed'" type="danger" size="small">
          {{ t('editor.renderFailed') }}
        </el-tag>
        <a v-if="store.finalUrl" :href="store.finalUrl" target="_blank" class="final-link">
          <el-button :icon="Download" text size="small">{{ t('editor.finalOutput') }}</el-button>
        </a>
        <el-dropdown class="export-dd" @command="onExportCommand">
          <el-button text size="small">{{ t('editor.exportMenu') }}<el-icon class="export-dd-arrow"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings">{{ t('editor.exportSettings') }}</el-dropdown-item>
              <el-dropdown-item command="history">{{ t('editor.historyTitle') }}</el-dropdown-item>
              <el-dropdown-item command="gif" divided :disabled="!store.finalUrl">{{ t('editor.exportGif') }}</el-dropdown-item>
              <el-dropdown-item command="audio" :disabled="!store.finalUrl">{{ t('editor.exportAudio') }}</el-dropdown-item>
              <el-dropdown-item command="jianying" :disabled="!store.doc?.clips.length">{{ t('editor.exportJianying') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tag
          v-if="store.qualityReport?.available && suspectCount > 0"
          type="warning"
          size="small"
          class="quality-tag"
          @click="qualityOpen = true"
        >
          {{ t('editor.qualityIssues', { n: suspectCount }) }}
        </el-tag>
        <el-tag
          v-else-if="store.qualityReport?.available"
          type="success"
          size="small"
          class="quality-tag"
          @click="qualityOpen = true"
        >
          {{ t('editor.qualityOk') }}
        </el-tag>
        <el-button type="primary" :icon="VideoPlay" :disabled="!canRender || store.renderStatus === 'rendering'" @click="store.submitRender()">
          {{ t('editor.render') }}
        </el-button>
      </div>
    </header>

    <div ref="bodyEl" class="editor-body">
      <div class="editor-top" :style="topH ? { height: `${topH}px` } : undefined">
        <EditorAssets class="editor-assets" :style="{ width: `${assetsW}px` }" />
        <span class="splitter splitter-v" @pointerdown="dragAssetsW" />
        <EditorPreview class="editor-preview" />
        <span class="splitter splitter-v" @pointerdown="dragInspectorW" />
        <EditorInspector class="editor-inspector" :style="{ width: `${inspectorW}px` }" />
      </div>
      <span class="splitter splitter-h" @pointerdown="dragTopH" />
      <div class="editor-bottom">
        <EditorTimeline :total-duration="totalDuration" />
      </div>
    </div>

    <!-- 导出设置（分辨率/帧率 → setDocumentMeta op，入撤销栈；字幕字号自动随宽度缩放） -->
    <el-dialog v-model="exportOpen" :title="t('editor.exportSettings')" width="460px" append-to-body>
      <div class="exp-presets">
        <button
          v-for="p in EXPORT_PRESETS"
          :key="p.key"
          type="button"
          class="exp-preset"
          :class="{ active: expWidth === p.width && expHeight === p.height }"
          @click="expWidth = p.width; expHeight = p.height"
        >
          <span class="exp-preset-name">{{ t(`editor.exportPreset.${p.key}`) }}</span>
          <span class="exp-preset-dim">{{ p.width }}×{{ p.height }}</span>
        </button>
      </div>
      <div class="exp-row">
        <span>{{ t('editor.exportSize') }}</span>
        <el-input-number v-model="expWidth" :min="16" :max="7680" :step="2" controls-position="right" />
        <span>×</span>
        <el-input-number v-model="expHeight" :min="16" :max="7680" :step="2" controls-position="right" />
      </div>
      <div class="exp-row">
        <span>{{ t('editor.exportFps') }}</span>
        <el-radio-group v-model="expFps">
          <el-radio-button :value="24">24</el-radio-button>
          <el-radio-button :value="25">25</el-radio-button>
          <el-radio-button :value="30">30</el-radio-button>
          <el-radio-button :value="60">60</el-radio-button>
        </el-radio-group>
      </div>
      <p class="exp-note">{{ t('editor.exportScaleNote') }}</p>
      <template #footer>
        <el-button @click="exportOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="applyExportSettings">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史还原 -->
    <EditorHistoryDialog :open="historyOpen" @close="historyOpen = false" />

    <!-- 渲染质检详情：类型/时间码/刻意标注，条目点击跳时间线播放头 -->
    <el-dialog v-model="qualityOpen" :title="t('editor.qualityTitle')" width="480px" append-to-body>
      <p v-if="!store.qualityReport?.issues?.length" class="quality-empty">{{ t('editor.qualityEmpty') }}</p>
      <ul v-else class="quality-list">
        <li v-for="(issue, i) in store.qualityReport.issues" :key="i">
          <button type="button" class="quality-row" @click="seekToIssue(issue.start)">
            <el-tag :type="issue.suspect ? 'danger' : 'info'" size="small">
              {{ t(`editor.qualityType.${issue.type}`) }}
            </el-tag>
            <span class="quality-time">{{ editorRefTimecode(issue.start) }} - {{ editorRefTimecode(issue.end) }}</span>
            <span class="quality-note">{{ issue.suspect ? t('editor.qualitySuspect') : t('editor.qualityIntentional') }}</span>
          </button>
        </li>
      </ul>
    </el-dialog>

    <!-- Agent 跨页操作徽标（批次 3 过程可视化）：桥执行期间亮起、回执后熄灭 -->
    <Transition name="agent-badge">
      <div v-if="bridgeBadge.on" class="agent-activity-badge">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ t('agent.pageBadge') }}{{ bridgeBadge.label }}</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.editor-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
}
.editor-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.editor-title {
  cursor: pointer;
  font-weight: 600;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.save-state {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 64px;
}
.final-link { text-decoration: none; }
/* 导出下拉 + 设置弹窗 */
.export-dd { margin-left: 2px; }
.export-dd-arrow { margin-left: 2px; }
.exp-presets { display: flex; gap: 8px; margin-bottom: 14px; }
.exp-preset {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 10px 4px; border: 1px solid var(--el-border-color); border-radius: 8px;
  background: transparent; cursor: pointer; color: inherit;
}
.exp-preset.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.exp-preset-name { font-size: 12px; }
.exp-preset-dim { font-size: 11px; color: var(--el-text-color-secondary); font-family: ui-monospace, monospace; }
.exp-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 13px; }
.exp-note { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
/* 质检徽标可点击 + 详情列表 */
.quality-tag { cursor: pointer; }
.quality-empty { margin: 0; font-size: 13px; color: var(--el-text-color-secondary); }
.quality-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.quality-row {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 6px 8px; border: none; border-radius: 6px; background: transparent;
  cursor: pointer; text-align: left; color: inherit; font-size: 13px;
}
.quality-row:hover { background: var(--el-fill-color-light); }
.quality-time { font-family: ui-monospace, monospace; }
.quality-note { margin-left: auto; font-size: 12px; color: var(--el-text-color-secondary); }
.editor-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* 上排：素材 | 预览 | 属性（宽度由分隔条拖拽调节）；下排全留给时间线 */
.editor-top {
  display: flex;
  flex: 0 0 auto;
  height: 44%;
  min-height: 0;
}
.editor-assets {
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
}
.editor-preview {
  flex: 1;
  min-width: 0;
}
.editor-inspector {
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color-lighter);
  overflow-y: auto;
}
.editor-bottom {
  flex: 1;
  min-height: 260px;
}
/* 分隔条：悬停高亮，负 margin 少占布局空间 */
.splitter {
  flex-shrink: 0;
  touch-action: none;
  z-index: 10;
}
.splitter-v {
  width: 5px;
  margin: 0 -2px;
  cursor: col-resize;
}
.splitter-h {
  display: block;
  height: 5px;
  margin: -2px 0;
  cursor: row-resize;
}
.splitter:hover {
  background: var(--el-color-primary-light-5);
}

/* ==================== Agent 跨页操作徽标（批次 3） ==================== */
.agent-activity-badge {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1200;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 999px;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color, #dcdfe6);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16);
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
  max-width: min(72vw, 520px);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-activity-badge .el-icon {
  color: var(--el-color-primary, #409eff);
  flex-shrink: 0;
}

.agent-badge-enter-active,
.agent-badge-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.agent-badge-enter-from,
.agent-badge-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>

<script setup lang="ts">
/* =====================================================
 * 剪辑器（/editor/:uid）— 宿主唯一入口
 * 布局：顶栏 / 上排=左素材+中预览+右属性 / 下排=时间线全宽通底
 * 所有区域直读 editor store，不层层传 props
 * ===================================================== */

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Edit, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { Ref } from 'vue'

import EditorAssets from '@/views/editor/EditorAssets.vue'
import EditorPreview from '@/views/editor/EditorPreview.vue'
import EditorTimeline from '@/views/editor/EditorTimeline.vue'
import EditorInspector from '@/views/editor/EditorInspector.vue'
import { useEditorStore } from '@/stores/editor'
import { updateEditorProject } from '@/api/editor'
import { useRename } from '@/composables/useRename'
import { useUserStore } from '@/stores/user'
import { clipEnd } from '@/lib/editor-types'
import { useI18n } from '@/i18n'

const route = useRoute()
const router = useRouter()
const store = useEditorStore()
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
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
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
</style>

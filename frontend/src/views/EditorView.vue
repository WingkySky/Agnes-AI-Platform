<script setup lang="ts">
/* =====================================================
 * 剪辑器（/editor/:uid）— 宿主唯一入口
 * 布局：顶栏 / 左素材面板 / 中预览 / 下时间线 / 右属性面板
 * 所有区域直读 editor store，不层层传 props
 * ===================================================== */

import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import EditorAssets from '@/views/editor/EditorAssets.vue'
import EditorPreview from '@/views/editor/EditorPreview.vue'
import EditorTimeline from '@/views/editor/EditorTimeline.vue'
import EditorInspector from '@/views/editor/EditorInspector.vue'
import { useEditorStore } from '@/stores/editor'
import { useUserStore } from '@/stores/user'
import { clipEnd } from '@/lib/editor-types'
import { useI18n } from '@/i18n'

const route = useRoute()
const router = useRouter()
const store = useEditorStore()
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

function onKeydown(e: KeyboardEvent): void {
  const target = e.target as HTMLElement
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  const mod = e.ctrlKey || e.metaKey
  if (e.code === 'Space') {
    e.preventDefault()
    store.isPlaying = !store.isPlaying
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    if (store.selectedClipId) {
      e.preventDefault()
      store.applyOrToast({ op: 'removeClip', payload: { clipId: store.selectedClipId } }, t('editor.ops.removeClip'))
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
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  void store.saveNow()
  store.reset()
})
</script>

<template>
  <div class="editor-page">
    <header class="editor-topbar">
      <el-button :icon="ArrowLeft" text @click="goBack">{{ t('common.back') }}</el-button>
      <span class="editor-title" :title="store.title">{{ store.title || t('editor.title') }}</span>
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

    <div class="editor-body">
      <EditorAssets class="editor-assets" />
      <div class="editor-main">
        <EditorPreview />
        <EditorTimeline :total-duration="totalDuration" />
      </div>
      <EditorInspector class="editor-inspector" />
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
  min-height: 0;
}
.editor-assets {
  width: 224px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
}
.editor-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.editor-inspector {
  width: 248px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color-lighter);
  overflow-y: auto;
}
</style>

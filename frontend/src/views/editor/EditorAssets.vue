<script setup lang="ts">
/* =====================================================
 * 素材面板：/api/assets 同源筛选（媒体类型/关键词/分页）
 * 拖入时间线建片段；上传走 POST /api/assets 入库后引用
 * ===================================================== */

import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Film, Headset, Upload } from '@element-plus/icons-vue'

import { ArrowLeftRight, Clapperboard, Wand2 } from 'lucide-vue-next'

import { createAsset, listAssets, type UnifiedAsset } from '@/api/assets'
import { uploadCanvasAsset } from '@/api/canvasWorkspace'
import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { EFFECT_DEFS, TRANSITION_DEFS } from '@/lib/editor-fx-registry'
import type { EffectType, TransitionType } from '@/lib/editor-types'

const store = useEditorStore()
const { t } = useI18n()

const PAGE_SIZE = 30
/** 主 tab：素材 / 转场 / 效果器（剪映式左侧垂直图标栏 + 右侧内容区） */
const activeTab = ref<'media' | 'transition' | 'effect'>('media')
const SIDE_TABS: Array<{ key: 'media' | 'transition' | 'effect'; labelKey: string; icon: unknown }> = [
  { key: 'media', labelKey: 'editor.tabMedia', icon: Clapperboard },
  { key: 'transition', labelKey: 'editor.tabTransition', icon: ArrowLeftRight },
  { key: 'effect', labelKey: 'editor.tabEffect', icon: Wand2 },
]
const mediaType = ref<'video' | 'image' | 'audio'>('video')
const keyword = ref('')
const items = ref<UnifiedAsset[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const typeOptions = computed(() =>
  (['video', 'image', 'audio'] as const).map((kind) => ({ label: t(`editor.mediaTypes.${kind}`), value: kind })),
)

async function reload(): Promise<void> {
  loading.value = true
  try {
    const resp = await listAssets({
      media_type: mediaType.value,
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: PAGE_SIZE,
    })
    items.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

/** el-segmented 的 change 值是宽类型，进来的值必须是合法媒体类型才生效 */
function switchType(kind: string | number | boolean | undefined): void {
  if (kind !== 'video' && kind !== 'image' && kind !== 'audio') return
  mediaType.value = kind
  page.value = 1
  void reload()
}

function search(): void {
  page.value = 1
  void reload()
}

function onPage(next: number): void {
  page.value = next
  void reload()
}

/** 单击临时预览到预览窗（再点同一素材关闭）；拖拽入轨/双击加轨行为不变 */
/** 转场库：应用到选中片段的衔接点（保留已有转场时长） */
function applyTransition(type: TransitionType): void {
  const clip = store.doc?.clips.find((c) => c.id === store.selectedClipId) ?? null
  if (!clip) {
    ElMessage.warning(t('editor.fxNeedSelect'))
    return
  }
  const doc = store.doc!
  const track = doc.tracks.find((tr) => tr.id === clip.trackId)
  if (!track || track.kind !== 'video') {
    ElMessage.warning(t('editor.fxNeedVideoClip'))
    return
  }
  const hasFollow = doc.clips.some((c) => c.trackId === clip.trackId && c.start > clip.start)
  if (!hasFollow) {
    ElMessage.warning(t('editor.fxNeedFollow'))
    return
  }
  const existing = track.transitions?.find((tr) => tr.afterClipId === clip.id)
  store.applyOrToast({
    op: 'setTransition',
    payload: { trackId: track.id, afterClipId: clip.id, transitionId: existing?.id ?? `tr_${Date.now().toString(36)}`, type, duration: existing?.duration ?? 0.5 },
  }, t('editor.propTransition'))
}

/** 效果器库：追加到选中片段（同类型去重） */
function applyEffect(type: EffectType): void {
  const clip = store.doc?.clips.find((c) => c.id === store.selectedClipId) ?? null
  if (!clip) {
    ElMessage.warning(t('editor.fxNeedSelect'))
    return
  }
  const track = store.doc!.tracks.find((tr) => tr.id === clip.trackId)
  if (!track || track.kind !== 'video') {
    ElMessage.warning(t('editor.fxNeedVideoClip'))
    return
  }
  const effects = clip.props.effects ?? []
  if (effects.some((e) => e.type === type)) {
    ElMessage.info(t('editor.fxDuplicate'))
    return
  }
  store.applyOrToast({
    op: 'setClipEffects',
    payload: { clipId: clip.id, effects: [...effects, { id: `fx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`, type, strength: type === 'blur' ? 0.4 : 1 }] },
  }, t('editor.propEffects'))
}

function onAssetClick(asset: UnifiedAsset): void {
  if (store.previewingAsset?.id === asset.id) store.endAssetPreview()
  else store.startAssetPreview(asset)
}

function onDragStart(e: DragEvent, asset: UnifiedAsset): void {
  e.dataTransfer?.setData('text/asset-id', String(asset.id))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

/** 双击兜底：不经拖拽，直接加到播放头处（视频/图片→首条视频轨，音频→首条音频轨） */
async function onAssetActivate(asset: UnifiedAsset): Promise<void> {
  await store.appendAssetToTrack(asset)
}

async function onPickFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  try {
    // 两步链路：先传 /api/uploads/canvas 得 url，再 POST /api/assets 入库（全资产引用语义）
    const { url } = await uploadCanvasAsset(file, file.name)
    const mediaTypeFromFile = file.type.startsWith('audio') ? 'audio' : file.type.startsWith('video') ? 'video' : 'image'
    const asset = await createAsset({ url, media_type: mediaTypeFromFile, name: file.name, work_id: store.workId ?? undefined })
    ElMessage.success(t('editor.uploadDone'))
    if (asset.media_type !== mediaType.value) switchType(asset.media_type)
    else await reload()
  } catch {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

onMounted(() => void reload())
</script>

<template>
  <div class="asset-panel">
    <nav class="side-tabs">
      <button
        v-for="tab in SIDE_TABS"
        :key="tab.key"
        type="button"
        class="side-tab"
        :class="{ active: activeTab === tab.key }"
        :title="t(tab.labelKey)"
        @click="activeTab = tab.key"
      >
        <el-icon :size="16"><component :is="tab.icon" /></el-icon>
        <span class="side-tab-label">{{ t(tab.labelKey) }}</span>
      </button>
    </nav>

    <div class="panel-body">
    <template v-if="activeTab === 'media'">
    <div class="type-row">
      <el-input v-model="keyword" size="small" clearable :placeholder="t('editor.searchPlaceholder')" @keyup.enter="search" @clear="search" />
      <el-button size="small" :icon="Upload" :title="t('editor.upload')" :aria-label="t('editor.upload')" :loading="uploading" @click="fileInput?.click()" />
      <input ref="fileInput" type="file" hidden :accept="mediaType === 'audio' ? 'audio/*' : mediaType === 'video' ? 'video/*' : 'image/*'" @change="onPickFile">
    </div>
    <el-segmented class="type-tabs" :model-value="mediaType" size="small" :options="typeOptions" @change="switchType" />

    <div v-loading="loading" class="asset-list">
      <div
        v-for="asset in items"
        :key="asset.id"
        class="asset-card"
        :class="{ active: store.previewingAsset?.id === asset.id }"
        draggable="true"
        :title="t('editor.assetCardHint')"
        @dragstart="onDragStart($event, asset)"
        @click="onAssetClick(asset)"
        @dblclick="onAssetActivate(asset)"
      >
        <div class="asset-thumb">
          <img v-if="asset.media_type === 'image'" :src="asset.thumb_url || asset.asset_url" loading="lazy">
          <!-- #t=0.1 让浏览器在 preload=metadata 阶段就绘制首帧，避免视频卡全黑 -->
          <video v-else-if="asset.media_type === 'video'" :src="`${asset.asset_url}#t=0.1`" preload="metadata" muted />
          <div v-else class="audio-mark"><el-icon><Headset /></el-icon></div>
        </div>
        <span class="asset-name" :title="asset.name">{{ asset.name }}</span>
      </div>
      <div v-if="!loading && !items.length" class="empty">
        <el-icon :size="26"><Film /></el-icon>
        <p>{{ t('editor.assetEmpty') }}</p>
      </div>
    </div>

    <div v-if="total > PAGE_SIZE" class="list-footer">
      <el-pagination
        layout="prev, pager, next"
        small
        :total="total"
        :page-size="PAGE_SIZE"
        :current-page="page"
        @current-change="onPage"
      />
      <span class="total">{{ t('editor.assetTotal', { n: total }) }}</span>
    </div>
    </template>

    <!-- 转场库：卡片点击应用到选中片段的衔接点 -->
    <template v-else-if="activeTab === 'transition'">
      <p class="fx-hint">{{ t('editor.fxTransitionHint') }}</p>
      <div class="asset-list fx-grid">
        <button
          v-for="def in TRANSITION_DEFS"
          :key="def.type"
          type="button"
          class="fx-card"
          @click="applyTransition(def.type)"
        >
          <span class="fx-sample" :class="`fx-transition-${def.preview}`" />
          <span class="asset-name">{{ t(def.labelKey) }}</span>
        </button>
      </div>
    </template>

    <!-- 效果器库：卡片点击追加到选中片段 -->
    <template v-else>
      <p class="fx-hint">{{ t('editor.fxEffectHint') }}</p>
      <div class="asset-list fx-grid">
        <button
          v-for="def in EFFECT_DEFS"
          :key="def.type"
          type="button"
          class="fx-card"
          @click="applyEffect(def.type)"
        >
          <span class="fx-sample">
            <span class="fx-scene" :style="{ filter: def.previewCss(def.type === 'blur' ? 0.4 : 1) || undefined }" />
          </span>
          <span class="asset-name">{{ t(def.labelKey) }}</span>
        </button>
      </div>
    </template>
    </div>
  </div>
</template>

<style scoped>
.asset-panel {
  display: flex;
  gap: 0;
  height: 100%;
  overflow: hidden;
}
/* 左侧垂直图标栏（剪映式）：图标+小字，选中高亮 */
.side-tabs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 4px;
  border-right: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.side-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 7px 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.side-tab:hover {
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
}
.side-tab.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.side-tab-label {
  font-size: 10px;
  line-height: 1.2;
  white-space: nowrap;
}
.panel-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  overflow: hidden;
}
.type-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.type-row .el-input {
  flex: 1;
}
.type-tabs {
  width: 100%;
}
.main-tabs {
  width: 100%;
}
.fx-hint {
  margin: 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.fx-grid {
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
}
.fx-card {
  position: relative;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  padding: 0;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.fx-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: var(--el-box-shadow-light);
}
.fx-sample {
  display: block;
  aspect-ratio: 16 / 9;
  background: var(--el-fill-color-dark);
}
/* 转场示意：两色块关系随类型不同（平滑/黑场/硬分界） */
.fx-transition-crossfade {
  background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-success));
}
.fx-transition-fade {
  background: linear-gradient(90deg, var(--el-color-primary), #000 50%, var(--el-color-success));
}
.fx-transition-wipe {
  background: linear-gradient(90deg, var(--el-color-primary) 50%, var(--el-color-success) 50%);
}
/* 效果器示意：内嵌 CSS 风景（天空渐变+山形），套效果 filter */
.fx-scene {
  display: block;
  width: 100%;
  height: 100%;
  background:
    linear-gradient(135deg, transparent 58%, #4a7a5a 58%, #3c6b4c 74%, transparent 74%),
    linear-gradient(115deg, transparent 70%, #5d8a6a 70%, #4a7a5a 100%),
    linear-gradient(180deg, #7db3e8 0%, #cfe6f7 62%, #e8dcc0 63%, #d9c9a3 100%);
}
.asset-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  /* 容器高度确定时 Chrome 会把裸 auto 行按剩余高度均分塌缩成细条，必须锁内容高度 */
  grid-auto-rows: minmax(max-content, auto);
  gap: 8px;
  align-content: start;
}
.asset-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  cursor: grab;
  background: var(--el-fill-color-lighter);
  position: relative;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.asset-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: var(--el-box-shadow-light);
}
/* 预览中的素材卡：与悬停同色系但常显，配合预览窗角标形成“正在看哪个”的对应关系 */
.asset-card.active {
  border-color: var(--el-color-primary);
  box-shadow: var(--el-box-shadow-light);
  background: var(--el-color-primary-light-9);
}
.asset-thumb {
  aspect-ratio: 16 / 9;
  background: var(--el-fill-color-dark);
}
.asset-thumb img, .asset-thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}
.audio-mark {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: var(--el-color-success);
}
.asset-name {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 14px 6px 4px;
  font-size: 11px;
  color: #fff;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  padding: 32px 0;
}
.empty p {
  margin: 0;
  font-size: 12px;
}
.list-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.total {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>

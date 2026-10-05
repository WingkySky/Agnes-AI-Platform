<script setup lang="ts">
/* =====================================================
 * 素材面板：/api/assets 同源筛选（媒体类型/关键词/分页）
 * 拖入时间线建片段；上传走 POST /api/assets 入库后引用
 * ===================================================== */

import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'

import { createAsset, listAssets, type UnifiedAsset } from '@/api/assets'
import { uploadCanvasAsset } from '@/api/canvasWorkspace'
import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'

const store = useEditorStore()
const { t } = useI18n()

const PAGE_SIZE = 30
const mediaType = ref<'video' | 'image' | 'audio'>('video')
const keyword = ref('')
const items = ref<UnifiedAsset[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

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

function switchType(kind: 'video' | 'image' | 'audio'): void {
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

function onDragStart(e: DragEvent, asset: UnifiedAsset): void {
  e.dataTransfer?.setData('text/asset-id', String(asset.id))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

/** 双击兜底：不经拖拽，直接加到播放头处（视频/图片→首条视频轨，音频→首条音频轨） */
async function onAssetActivate(asset: UnifiedAsset): Promise<void> {
  await store.addAssetAtPlayhead(asset)
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
    if (asset.media_type !== mediaType.value) switchType(asset.media_type as 'video' | 'image' | 'audio')
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
    <el-input v-model="keyword" size="small" clearable :placeholder="t('editor.searchPlaceholder')" @keyup.enter="search" @clear="search" />
    <div class="type-tabs">
      <el-button v-for="kind in (['video', 'image', 'audio'] as const)" :key="kind" size="small" :type="mediaType === kind ? 'primary' : ''" @click="switchType(kind)">
        {{ t(`editor.mediaTypes.${kind}`) }}
      </el-button>
      <el-button size="small" :icon="Upload" :loading="uploading" @click="fileInput?.click()">
        {{ t('editor.upload') }}
      </el-button>
      <input ref="fileInput" type="file" hidden :accept="mediaType === 'audio' ? 'audio/*' : mediaType === 'video' ? 'video/*' : 'image/*'" @change="onPickFile">
    </div>

    <div v-loading="loading" class="asset-list">
      <div
        v-for="asset in items"
        :key="asset.id"
        class="asset-card"
        draggable="true"
        :title="t('editor.assetDblClickHint')"
        @dragstart="onDragStart($event, asset)"
        @dblclick="onAssetActivate(asset)"
      >
        <img v-if="asset.media_type === 'image'" :src="asset.thumb_url || asset.asset_url" loading="lazy">
        <video v-else-if="asset.media_type === 'video'" :src="asset.asset_url" preload="metadata" muted />
        <div v-else class="audio-mark">♪</div>
        <span class="asset-name" :title="asset.name">{{ asset.name }}</span>
      </div>
      <div v-if="!loading && !items.length" class="empty">{{ t('editor.assetEmpty') }}</div>
    </div>

    <el-pagination
      v-if="total > PAGE_SIZE"
      layout="prev, pager, next"
      small
      :total="total"
      :page-size="PAGE_SIZE"
      :current-page="page"
      @current-change="onPage"
    />
    <p class="drag-hint">{{ t('editor.dragHint') }}</p>
  </div>
</template>

<style scoped>
.asset-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  height: 100%;
  overflow: hidden;
}
.type-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.asset-list {
  flex: 1;
  overflow-y: auto;
  display: grid;
  /* 自适应网格：卡片最小 150px 保证缩略图可读，面板变窄减列（最窄 1 列）、变宽加大卡片 */
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  align-content: start;
  min-height: 0;
}
.asset-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
  cursor: grab;
  background: var(--el-fill-color-lighter);
  position: relative;
}
.asset-card img, .asset-card video {
  width: 100%;
  /* 缩略图固定高度（≈16:9）：不随面板高度伸缩，尺寸始终可读 */
  height: 84px;
  object-fit: cover;
  display: block;
  pointer-events: none;
}
.audio-mark {
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: var(--el-color-success);
}
.asset-name {
  display: block;
  font-size: 11px;
  padding: 2px 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 24px 0;
}
.drag-hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 0;
  text-align: center;
}
</style>

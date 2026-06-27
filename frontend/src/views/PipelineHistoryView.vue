<!-- =====================================================
     创作历史 - PipelineHistoryView
     - 网格展示所有流水线产物（视频/图片等）
     - 点击可预览/下载
     ===================================================== -->

<template>
  <div class="pipeline-history">
    <div class="history-header">
      <el-page-header @back="goBack">
        <template #content>
          <span class="header-title">{{ t('pipelineHistory.title') }}</span>
        </template>
      </el-page-header>
    </div>

    <div v-loading="loading" class="history-body">
      <!-- 空状态 -->
      <div v-if="!loading && outputs.length === 0" class="empty-state">
        <el-icon :size="48"><PictureFilled /></el-icon>
        <p class="empty-text">{{ t('pipelineHistory.noOutputs') }}</p>
      </div>

      <!-- 产物网格 -->
      <div v-else class="output-grid">
        <div
          v-for="item in outputs"
          :key="item.filename"
          class="output-card"
          @click="previewItem(item)"
        >
          <div class="output-thumb">
            <video
              v-if="isVideo(item.filename)"
              :src="item.url"
              muted
              preload="metadata"
              class="output-video-thumb"
            />
            <img
              v-else-if="isImage(item.filename)"
              :src="item.url"
              :alt="item.filename"
              class="output-image-thumb"
            />
            <div v-else class="thumb-placeholder">
              <el-icon :size="36"><Document /></el-icon>
            </div>
          </div>
          <div class="output-info">
            <div class="output-name" :title="item.filename">{{ item.filename }}</div>
            <div class="output-meta">
              <span class="output-date">{{ formatDate(item.modified_at) }}</span>
              <span class="output-size">{{ formatSize(item.size) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewItemData?.filename"
      width="70%"
      destroy-on-close
    >
      <div v-if="previewItemData" class="preview-content">
        <video
          v-if="isVideo(previewItemData.filename)"
          :src="previewItemData.url"
          controls
          class="preview-video"
        />
        <img
          v-else-if="isImage(previewItemData.filename)"
          :src="previewItemData.url"
          class="preview-image"
        />
        <div v-else class="preview-unknown">
          <el-icon :size="64"><Document /></el-icon>
          <p>{{ previewItemData.filename }}</p>
          <el-button type="primary" @click="downloadItem(previewItemData)">
            <el-icon><Download /></el-icon>
            {{ t('common.download') }}
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { PictureFilled, Document, Download } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { getPipelineOutputs, type PipelineOutput } from '@/api/pipeline'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const outputs = ref<PipelineOutput[]>([])
const previewVisible = ref(false)
const previewItemData = ref<PipelineOutput | null>(null)

// 文件类型判断
const videoExts = new Set(['mp4', 'mov', 'webm', 'avi', 'mkv'])
const imageExts = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'])

function getExt(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot >= 0 ? filename.substring(dot + 1).toLowerCase() : ''
}

function isVideo(filename: string): boolean {
  return videoExts.has(getExt(filename))
}

function isImage(filename: string): boolean {
  return imageExts.has(getExt(filename))
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function goBack() {
  router.push('/workshop')
}

function previewItem(item: PipelineOutput) {
  previewItemData.value = item
  previewVisible.value = true
}

function downloadItem(item: PipelineOutput) {
  const a = document.createElement('a')
  a.href = item.url
  a.download = item.filename
  a.click()
}

onMounted(async () => {
  loading.value = true
  try {
    const res = await getPipelineOutputs()
    outputs.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineHistory.loadFailed'))
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.pipeline-history {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;

  .history-header {
    margin-bottom: 24px;
    .header-title {
      font-size: 18px;
      font-weight: 600;
    }
  }

  .empty-state {
    text-align: center;
    padding: 80px 0;
    color: var(--el-text-color-secondary);
    .empty-text {
      margin-top: 12px;
      font-size: 14px;
    }
  }

  .output-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .output-card {
    background: var(--el-bg-color);
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    transition: box-shadow 0.2s, transform 0.2s;
    border: 1px solid var(--el-border-color-light);

    &:hover {
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
      transform: translateY(-2px);
    }
  }

  .output-thumb {
    width: 100%;
    height: 160px;
    background: #1a1a2e;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;

    .output-video-thumb,
    .output-image-thumb {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .thumb-placeholder {
      color: var(--el-text-color-disabled);
    }
  }

  .output-info {
    padding: 12px;

    .output-name {
      font-size: 13px;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 6px;
    }

    .output-meta {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      display: flex;
      gap: 8px;
    }
  }
}

.preview-content {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;

  .preview-video {
    max-width: 100%;
    max-height: 70vh;
    outline: none;
  }

  .preview-image {
    max-width: 100%;
    max-height: 70vh;
    object-fit: contain;
  }

  .preview-unknown {
    text-align: center;
    color: var(--el-text-color-secondary);
  }
}
</style>

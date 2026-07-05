<!-- =====================================================
     BGM 选择对话框 BgmPickerDialog
     - 展示内置 BGM 库（5 种情绪分类）
     - 按情绪过滤
     - 试听 + 选中
     - 支持清除已选 BGM
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    title="选择背景音乐"
    width="640px"
    :close-on-click-modal="false"
    append-to-body
  >
    <!-- 情绪过滤 -->
    <div class="mood-filter">
      <el-radio-group v-model="activeMood" size="small">
        <el-radio-button :value="''">全部</el-radio-button>
        <el-radio-button
          v-for="mood in moods"
          :key="mood"
          :value="mood"
        >{{ moodLabel(mood) }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- BGM 列表 -->
    <div class="bgm-list">
      <div
        v-for="bgm in filteredBgms"
        :key="bgm.id"
        class="bgm-item"
        :class="{ selected: selectedBgmId === bgm.id }"
        @click="selectedBgmId = bgm.id"
      >
        <div class="bgm-info">
          <div class="bgm-name">
            <el-icon><Headset /></el-icon>
            <span>{{ bgm.name }}</span>
            <el-tag size="small" type="info" effect="plain">{{ moodLabel(bgm.mood) }}</el-tag>
            <el-tag
              v-if="!bgm.available"
              size="small"
              type="danger"
              effect="plain"
            >文件缺失</el-tag>
          </div>
          <div class="bgm-meta">
            <span>时长：{{ formatDuration(bgm.duration) }}</span>
          </div>
        </div>
        <div class="bgm-actions" @click.stop>
          <el-button
            link
            size="small"
            :icon="VideoPlay"
            :disabled="!bgm.available"
            @click="togglePreview(bgm)"
          >{{ previewingId === bgm.id ? '停止' : '试听' }}</el-button>
        </div>
      </div>

      <div v-if="filteredBgms.length === 0" class="empty-tip">
        <el-icon :size="32"><Headset /></el-icon>
        <span>BGM 列表加载中...</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button @click="handleClear">清除 BGM</el-button>
      <el-button
        type="primary"
        :disabled="!selectedBgmId"
        @click="handleConfirm"
      >确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Headset, VideoPlay } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { BGMItem, BGMMood } from '@/types/project'

const props = defineProps<{
  /** 默认选中的 BGM ID */
  defaultBgmId?: string | null
}>()

const emit = defineEmits<{
  (e: 'confirm', bgmId: string | null, bgm: BGMItem | null): void
}>()

const visible = defineModel<boolean>('visible', { default: false })

const projectStore = useProjectStore()

const selectedBgmId = ref<string | null>(props.defaultBgmId || null)
const activeMood = ref<'' | BGMMood>('')
const previewingId = ref<string | null>(null)

const bgms = computed<BGMItem[]>(() => projectStore.bgmList)
const moods = computed<string[]>(() => projectStore.bgmMoods)

const filteredBgms = computed(() => {
  if (!activeMood.value) return bgms.value
  return bgms.value.filter((b) => b.mood === activeMood.value)
})

// 对话框打开时加载 BGM 列表
watch(visible, async (open) => {
  if (open) {
    selectedBgmId.value = props.defaultBgmId || null
    if (bgms.value.length === 0) {
      await projectStore.fetchBgms()
    }
    if (moods.value.length === 0) {
      await projectStore.fetchBgmMoods()
    }
  } else {
    stopPreview()
  }
})

function moodLabel(mood: string): string {
  const labels: Record<string, string> = {
    calm: '治愈',
    corporate: '商务',
    dramatic: '戏剧',
    uplifting: '激昂',
    sad: '忧伤',
  }
  return labels[mood] || mood
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

// 试听（简单的 HTML5 audio 切换）
let audioEl: HTMLAudioElement | null = null

async function togglePreview(bgm: BGMItem) {
  if (previewingId.value === bgm.id) {
    stopPreview()
    return
  }
  stopPreview()
  // 试听依赖后端提供 BGM 文件 URL（/api/projects/{pid}/bgm/{bgm_id}/file）
  // 此处仅占位，实际试听需要后端支持
  previewingId.value = bgm.id
  ElMessage.info(`试听「${bgm.name}」需要后端 BGM 文件接口支持`)
}

function stopPreview() {
  if (audioEl) {
    audioEl.pause()
    audioEl = null
  }
  previewingId.value = null
}

function handleConfirm() {
  if (!selectedBgmId.value) return
  const bgm = bgms.value.find((b) => b.id === selectedBgmId.value) || null
  emit('confirm', selectedBgmId.value, bgm)
  visible.value = false
}

function handleClear() {
  selectedBgmId.value = null
  emit('confirm', null, null)
  visible.value = false
}
</script>

<style scoped>
.mood-filter {
  margin-bottom: 12px;
}

.bgm-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.bgm-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s;
}

.bgm-item:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.bgm-item.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.bgm-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bgm-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}

.bgm-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-tip {
  padding: 32px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>

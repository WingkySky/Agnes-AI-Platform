<!-- =====================================================
     历史图片选择器 HistoryImagePicker
     - 从本地任务队列（localforage 持久化）读取已生成的图片历史
     - 网格展示缩略图 + 按 prompt 关键字过滤 + 简单分页
     - 选中后 emit 选中图片的 URL
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="t('templateEditor.historyImage')"
    width="780px"
    destroy-on-close
    @closed="onClosed"
  >
    <!-- 搜索框 -->
    <div class="picker-toolbar">
      <el-input
        v-model="searchKeyword"
        :placeholder="t('templateEditor.historySearchPlaceholder')"
        clearable
        class="search-input">
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <span class="picker-count">
        {{ t('templateEditor.historyCount', { total: filteredItems.length }) }}
      </span>
    </div>

    <!-- 网格 -->
    <div class="picker-grid">
      <div v-if="pagedItems.length === 0" class="picker-empty">
        <el-icon :size="40"><Picture /></el-icon>
        <p>{{ t('templateEditor.historyEmpty') }}</p>
      </div>
      <div
        v-for="(item, idx) in pagedItems"
        :key="idx"
        class="picker-item"
        :title="item.prompt"
        @click="onSelect(item)">
        <img :src="item.url" :alt="item.prompt" @error="onImgError" />
        <div v-if="item.prompt" class="item-prompt">{{ truncate(item.prompt, 30) }}</div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="filteredItems.length > pageSize" class="picker-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredItems.length"
        layout="prev, pager, next"
        small
        background />
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Search, Picture } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useTaskQueueStore } from '@/stores/taskQueue'

const { t } = useI18n()

// ---------- Props / Emits ----------
const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'select', url: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ---------- 数据加载 ----------
const taskQueue = useTaskQueueStore()
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = 24

// 从 taskQueue 中提取已成功完成的图片任务（resultUrl + prompt）
interface HistoryItem { url: string; prompt: string; createdAt: number }

const allItems = computed<HistoryItem[]>(() => {
  return taskQueue.taskList
    .filter((task) => task.type === 'image' && task.status === 'success' && !!task.resultUrl)
    .map((task) => ({
      url: task.resultUrl as string,
      prompt: task.prompt || '',
      createdAt: task.createdAt || 0,
    }))
    .sort((a, b) => b.createdAt - a.createdAt)
})

// 按 prompt 关键字过滤
const filteredItems = computed<HistoryItem[]>(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return allItems.value
  return allItems.value.filter((it) => it.prompt.toLowerCase().includes(kw))
})

// 当前页数据
const pagedItems = computed<HistoryItem[]>(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredItems.value.slice(start, start + pageSize)
})

// 弹窗打开时触发一次加载
watch(visible, (v) => {
  if (v) {
    // taskQueue 已在应用启动时 hydrate，直接读取本地任务列表
    currentPage.value = 1
    searchKeyword.value = ''
  }
})

// ---------- 事件处理 ----------
function onSelect(item: HistoryItem) {
  emit('select', item.url)
  visible.value = false
}

function onClosed() {
  searchKeyword.value = ''
  currentPage.value = 1
}

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

function truncate(text: string, n: number): string {
  return text.length > n ? text.slice(0, n) + '...' : text
}
</script>

<style scoped>
.picker-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.search-input {
  width: 320px;
}
.picker-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  min-height: 280px;
  max-height: 460px;
  overflow-y: auto;
  padding: 4px;
}

.picker-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--el-text-color-placeholder);
  gap: 12px;
}
.picker-empty p {
  margin: 0;
  font-size: 14px;
}

.picker-item {
  position: relative;
  aspect-ratio: 1 / 1;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-light);
  transition: all 0.15s;
}
.picker-item:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.picker-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.item-prompt {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 4px 6px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  color: #fff;
  font-size: 11px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-pagination {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>

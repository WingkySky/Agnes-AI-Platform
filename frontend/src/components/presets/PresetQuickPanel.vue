<!-- =====================================================
     PresetQuickPanel — 预设快捷面板
     - 最近使用 5 条预设
     - 搜索框
     - "前往预设中心"链接
     - 支持点击预设回传 prompt_text / camera_params
     ===================================================== -->

<template>
  <div class="quick-panel">
    <!-- 搜索框 -->
    <div class="panel-search">
      <el-input
        v-model="searchText"
        :placeholder="t('presets.quickPanel.searchPlaceholder')"
        size="small"
        clearable
        :prefix-icon="Search"
        @input="onSearch"
      />
    </div>

    <!-- 最近使用 -->
    <div class="panel-section" v-if="!searchText">
      <h5 class="panel-title">{{ t('presets.quickPanel.recentTitle') }}</h5>
      <div class="preset-list" v-if="recentPresets.length > 0">
        <button
          v-for="preset in recentPresets"
          :key="preset.id"
          type="button"
          class="preset-item"
          @click="selectPreset(preset)"
        >
          <div class="preset-item-info">
            <span class="preset-item-name">{{ preset.name }}</span>
            <span class="preset-item-type">{{ typeLabel(preset.type) }}</span>
          </div>
          <ChevronRight :size="14" class="preset-item-arrow" />
        </button>
      </div>
      <p v-else class="panel-empty">{{ t('presets.quickPanel.recentEmpty') }}</p>
    </div>

    <!-- 搜索结果 -->
    <div class="panel-section" v-if="searchText">
      <h5 class="panel-title">{{ t('presets.quickPanel.searchResultTitle') }}</h5>
      <div class="preset-list" v-if="searchResults.length > 0" v-loading="searchLoading">
        <button
          v-for="preset in searchResults"
          :key="preset.id"
          type="button"
          class="preset-item"
          @click="selectPreset(preset)"
        >
          <div class="preset-item-info">
            <span class="preset-item-name">{{ preset.name }}</span>
            <el-tag size="small" effect="plain">{{ preset.category }}</el-tag>
          </div>
          <ChevronRight :size="14" class="preset-item-arrow" />
        </button>
      </div>
      <p v-else-if="!searchLoading" class="panel-empty">
        {{ t('presets.quickPanel.searchResultEmpty') }}
      </p>
    </div>

    <!-- 底部链接 -->
    <el-divider />
    <div class="panel-footer">
      <router-link to="/presets" class="footer-link" @click="$emit('navigate')">
        {{ t('presets.quickPanel.goToCenter') }}
        <ArrowRight :size="14" />
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PresetQuickPanel — 画布/聊天/工作台等场景调用的预设快捷选择面板
 * 通过 emit('select') 把选中的预设回传父组件。
 */
import { ref, onMounted } from 'vue'
// Search / ArrowRight 来自 Element Plus 图标库；ChevronRight 在 Element Plus 中不存在，改用 lucide-vue-next（与项目其他组件保持一致）
import { Search, ArrowRight } from '@element-plus/icons-vue'
import { ChevronRight } from 'lucide-vue-next'
import { getPresets } from '@/api/presets'
import { useI18n } from '@/i18n'
import type { PromptPreset } from '@/types/preset'

const { t } = useI18n()

const emit = defineEmits<{
  select: [preset: PromptPreset]
  navigate: []
}>()

const searchText = ref('')
const searchLoading = ref(false)
const searchResults = ref<PromptPreset[]>([])
const recentPresets = ref<PromptPreset[]>([])

// 类型显示名（走 i18n）
function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.quickPanel.typeCamera',
    prompt: 'presets.quickPanel.typePrompt',
    style: 'presets.quickPanel.typeStyle',
    script: 'presets.quickPanel.typeScript',
    pipeline: 'presets.quickPanel.typePipeline',
  }
  return keyMap[type] ? t(keyMap[type]) : type
}

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  const query = searchText.value.trim()
  if (!query) {
    searchResults.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searchLoading.value = true
    try {
      const result = await getPresets({ search: query, limit: 10, sort: 'usage' })
      searchResults.value = result.items
    } catch {
      searchResults.value = []
    } finally {
      searchLoading.value = false
    }
  }, 300)
}

async function loadRecentPresets() {
  try {
    const result = await getPresets({ sort: 'usage', limit: 5 })
    recentPresets.value = result.items
  } catch {
    recentPresets.value = []
  }
}

function selectPreset(preset: PromptPreset) {
  emit('select', preset)
}

onMounted(() => {
  loadRecentPresets()
})
</script>

<style scoped>
.quick-panel {
  padding: 4px 0;
  min-width: 280px;
  max-width: 360px;
}

.panel-search {
  margin-bottom: 12px;
}

.panel-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--agnes-text-tertiary);
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preset-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.preset-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

/* 修复：原 --agnes-fill-secondary 不存在，改用 --agnes-bg-hover */
.preset-item:hover {
  background: var(--agnes-bg-hover);
}

.preset-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.preset-item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preset-item-type {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
}

.preset-item-arrow {
  flex-shrink: 0;
  color: var(--agnes-text-tertiary);
  margin-left: 8px;
}

.panel-empty {
  font-size: 12px;
  color: var(--agnes-text-tertiary);
  text-align: center;
  padding: 16px 0;
  margin: 0;
}

.panel-footer {
  text-align: center;
}

.footer-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--agnes-text-link);
  text-decoration: none;
}

.footer-link:hover {
  text-decoration: underline;
}
</style>

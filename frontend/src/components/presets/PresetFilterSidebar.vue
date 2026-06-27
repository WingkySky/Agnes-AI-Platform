<!-- =====================================================
     PresetFilterSidebar — 分类筛选侧边栏
     - category 枚举下拉（人像/场景/构图/动作/光影/风格/通用）
     - tags 模糊匹配搜索
     - 全选/取消按钮
     ===================================================== -->

<template>
  <div class="filter-sidebar">
    <div class="filter-section">
      <h4 class="filter-heading">{{ t('presets.sidebar.categoryTitle') }}</h4>
      <div class="filter-actions">
        <el-button type="primary" link size="small" @click="selectAll">
          {{ t('presets.sidebar.selectAll') }}
        </el-button>
        <el-button type="primary" link size="small" @click="deselectAll">
          {{ t('presets.sidebar.clearAll') }}
        </el-button>
      </div>
      <el-checkbox-group v-model="selectedCategories" class="checkbox-group" @change="onChange">
        <el-checkbox
          v-for="cat in categories"
          :key="cat.value"
          :label="cat.value"
          :value="cat.value"
          class="filter-checkbox"
        >
          {{ cat.label }}
        </el-checkbox>
      </el-checkbox-group>
    </div>

    <el-divider />

    <div class="filter-section">
      <h4 class="filter-heading">{{ t('presets.sidebar.tagsTitle') }}</h4>
      <el-select
        v-model="selectedTags"
        multiple
        filterable
        allow-create
        default-first-option
        :placeholder="t('presets.sidebar.tagsPlaceholder')"
        style="width: 100%"
        @change="onChange"
      />
    </div>

    <el-divider />

    <div class="filter-section">
      <h4 class="filter-heading">{{ t('presets.sidebar.scopeTitle') }}</h4>
      <el-radio-group
        v-model="scopeFilter"
        class="scope-group"
        size="small"
        @change="onChange"
      >
        <el-radio-button value="all">{{ t('presets.sidebar.scopeAll') }}</el-radio-button>
        <el-radio-button value="mine">{{ t('presets.sidebar.scopeMine') }}</el-radio-button>
        <el-radio-button value="public">{{ t('presets.sidebar.scopePublic') }}</el-radio-button>
      </el-radio-group>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PresetFilterSidebar — 分类/标签/范围筛选侧边栏
 * 通过 emit('filter') 把筛选条件回传父组件。
 */
import { ref, computed } from 'vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const emit = defineEmits<{
  filter: [params: { categories: string[]; tags: string[]; scope: string }]
}>()

// 分类枚举：value 提交后端，label 走 i18n 展示
const categories = computed(() => [
  { value: '通用', label: t('presets.sidebar.catGeneral') },
  { value: '人像', label: t('presets.sidebar.catPortrait') },
  { value: '场景', label: t('presets.sidebar.catScene') },
  { value: '构图', label: t('presets.sidebar.catComposition') },
  { value: '动作', label: t('presets.sidebar.catAction') },
  { value: '光影', label: t('presets.sidebar.catLighting') },
  { value: '风格', label: t('presets.sidebar.catStyle') },
])

const selectedCategories = ref<string[]>([])
const selectedTags = ref<string[]>([])
const scopeFilter = ref('all')

function selectAll() {
  selectedCategories.value = categories.value.map((c) => c.value)
  onChange()
}

function deselectAll() {
  selectedCategories.value = []
  selectedTags.value = []
  scopeFilter.value = 'all'
  onChange()
}

function onChange() {
  emit('filter', {
    categories: [...selectedCategories.value],
    tags: [...selectedTags.value],
    scope: scopeFilter.value,
  })
}
</script>

<style scoped>
.filter-sidebar {
  padding: 4px 0;
}

.filter-heading {
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0 0 8px;
}

.filter-actions {
  margin-bottom: 8px;
  display: flex;
  gap: 4px;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-checkbox {
  margin-right: 0;
}

.scope-group {
  width: 100%;
}

:deep(.scope-group .el-radio-button__inner) {
  width: 100%;
  text-align: center;
}
</style>

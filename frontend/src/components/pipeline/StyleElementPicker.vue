<!-- =====================================================
     StyleElementPicker 分层风格选择器
     - 按 6 个层级（画风/光影/配色/镜头/氛围/品质）展示风格元素
     - 支持多选并调节每个元素的权重
     - 实时预览拼接后的 final prompt
     - 通过 @change 事件向父组件暴露已选元素列表
     ===================================================== -->

<template>
  <div class="style-element-picker">
    <!-- 顶部操作栏：已选计数 + 清空 -->
    <div class="picker-header">
      <span class="selected-count">{{ t('styleElement.selectedCount', { count: selectedItems.length }) }}</span>
      <el-button
        v-if="selectedItems.length > 0"
        type="danger"
        text
        size="small"
        @click="clearAll">
        {{ t('styleElement.clearAll') }}
      </el-button>
    </div>

    <!-- 层级 Tab -->
    <el-tabs v-model="activeLayer" class="layer-tabs" @tab-change="onLayerChange">
      <el-tab-pane
        v-for="layer in layers"
        :key="layer.key"
        :label="layer.name"
        :name="layer.key" />
    </el-tabs>

    <!-- 当前层的元素列表 -->
    <div v-loading="loading" class="element-grid">
      <el-empty v-if="!loading && currentLayerElements.length === 0" :description="t('styleElement.noElements')" />

      <div
        v-for="el in currentLayerElements"
        :key="el.id"
        class="element-card"
        :class="{ active: isSelected(el.id) }"
        @click="toggleSelect(el)">
        <!-- 缩略图 -->
        <div class="element-thumb">
          <el-image
            v-if="el.preview_image"
            :src="el.preview_image"
            fit="cover"
            class="thumb-img" />
          <div v-else class="thumb-placeholder">
            <el-icon :size="20"><Picture /></el-icon>
          </div>
          <!-- 选中标记 -->
          <div v-if="isSelected(el.id)" class="active-badge">
            <el-icon><Check /></el-icon>
          </div>
        </div>
        <!-- 名称与描述 -->
        <div class="element-info">
          <div class="element-name">{{ el.name }}</div>
          <div v-if="el.description" class="element-desc">{{ el.description }}</div>
        </div>
        <!-- 选中后显示权重滑块 -->
        <div v-if="isSelected(el.id)" class="weight-row" @click.stop>
          <span class="weight-label">{{ t('styleElement.weightDefault') }}</span>
          <el-slider
            :model-value="getWeight(el.id)"
            :min="0"
            :max="1"
            :step="0.1"
            class="weight-slider"
            @update:model-value="(v: number) => setWeight(el.id, v)" />
          <span class="weight-value">{{ getWeight(el.id).toFixed(1) }}</span>
        </div>
      </div>
    </div>

    <!-- Prompt 预览折叠区 -->
    <el-collapse v-if="selectedItems.length > 0" v-model="previewCollapsed" class="preview-collapse">
      <el-collapse-item name="preview">
        <template #title>
          <span class="preview-title">{{ t('styleElement.promptPreview') }}</span>
        </template>
        <div v-loading="previewing" class="preview-body">
          <div v-if="previewResult" class="prompt-block">
            <div class="prompt-label">{{ t('styleElement.finalPrompt') }}</div>
            <pre class="prompt-text">{{ previewResult.final_prompt }}</pre>
          </div>
          <el-empty v-else :description="t('styleElement.loadFailed')" />
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { Picture, Check } from '@element-plus/icons-vue'
import {
  listStyleElements,
  listLayers,
  previewPrompt,
  type StyleElement,
  type StyleLayer,
  type LayerInfo,
  type ResolvedElementItem,
  type PromptPreviewResponse,
} from '@/api/styleElement'

const props = defineProps<{
  /** 基础 prompt，用于实时预览拼接结果 */
  basePrompt?: string
}>()

const emit = defineEmits<{
  /** 已选元素列表变化（含权重） */
  change: [items: ResolvedElementItem[]]
}>()

const { t } = useI18n()

// ---------- 状态 ----------
const layers = ref<LayerInfo[]>([])
const activeLayer = ref<StyleLayer>('visual_style')
const allElements = ref<StyleElement[]>([])
const loading = ref(false)

// 已选元素：element_id -> weight
const selectedMap = ref<Record<number, number>>({})

// 预览状态
const previewResult = ref<PromptPreviewResponse | null>(null)
const previewing = ref(false)
const previewCollapsed = ref<string[]>([])

// 当前层的元素列表
const currentLayerElements = computed(() =>
  allElements.value.filter(e => e.layer === activeLayer.value)
)

// 已选元素列表（数组形式）
const selectedItems = computed<ResolvedElementItem[]>(() =>
  Object.entries(selectedMap.value).map(([id, weight]) => ({
    element_id: Number(id),
    weight,
  }))
)

// ---------- 方法 ----------
function isSelected(id: number): boolean {
  return selectedMap.value[id] !== undefined
}

function getWeight(id: number): number {
  return selectedMap.value[id] ?? 1.0
}

function setWeight(id: number, weight: number) {
  selectedMap.value = { ...selectedMap.value, [id]: weight }
  emitChange()
}

function toggleSelect(el: StyleElement) {
  if (isSelected(el.id)) {
    const next = { ...selectedMap.value }
    delete next[el.id]
    selectedMap.value = next
  } else {
    selectedMap.value = { ...selectedMap.value, [el.id]: el.weight_default ?? 1.0 }
  }
  emitChange()
}

function clearAll() {
  selectedMap.value = {}
  emitChange()
}

function emitChange() {
  emit('change', selectedItems.value)
}

async function loadLayers() {
  try {
    const res = await listLayers()
    layers.value = res.layers
    if (layers.value.length > 0) {
      activeLayer.value = layers.value[0].key as StyleLayer
    }
  } catch (e: any) {
    ElMessage.error(e?.message || t('styleElement.loadFailed'))
  }
}

async function loadElements() {
  loading.value = true
  try {
    const res = await listStyleElements({ limit: 500 })
    allElements.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || t('styleElement.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function refreshPreview() {
  if (selectedItems.value.length === 0) {
    previewResult.value = null
    return
  }
  previewing.value = true
  try {
    previewResult.value = await previewPrompt({
      base_prompt: props.basePrompt || '',
      elements: selectedItems.value,
    })
  } catch (e: any) {
    // 预览失败不弹错误 toast，只在折叠区显示空状态
    previewResult.value = null
  } finally {
    previewing.value = false
  }
}

function onLayerChange() {
  // 切层时不需要重载数据（已一次加载全部），只是切换过滤
}

// 监听已选元素和 basePrompt 变化，自动刷新预览
watch(
  () => selectedItems.value,
  () => refreshPreview(),
  { deep: true }
)
watch(
  () => props.basePrompt,
  () => refreshPreview()
)

// ---------- 生命周期 ----------
onMounted(async () => {
  await loadLayers()
  await loadElements()
})
</script>

<style scoped>
.style-element-picker {
  width: 100%;
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.selected-count {
  font-size: 13px;
  color: var(--agnes-text-secondary);
}

.layer-tabs {
  margin-bottom: 12px;
}

.element-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  min-height: 80px;
}

.element-card {
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  background: var(--agnes-bg-surface, #fff);
}

.element-card:hover {
  border-color: var(--agnes-primary);
}

.element-card.active {
  border-color: var(--agnes-primary);
  box-shadow: 0 0 0 2px var(--agnes-primary-border-faint);
}

.element-thumb {
  position: relative;
  width: 100%;
  height: 100px;
  background: var(--agnes-bg-dark-surface, #f5f5f5);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 8px;
}

.thumb-img {
  width: 100%;
  height: 100%;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-faint, #999);
}

.active-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--agnes-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.element-info {
  font-size: 13px;
}

.element-name {
  font-weight: 500;
  color: var(--agnes-text-primary);
  margin-bottom: 2px;
}

.element-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.weight-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--agnes-border);
}

.weight-label {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  flex-shrink: 0;
}

.weight-slider {
  flex: 1;
  min-width: 0;
}

.weight-value {
  font-size: 12px;
  color: var(--agnes-text-primary);
  font-weight: 500;
  flex-shrink: 0;
  width: 24px;
  text-align: right;
}

.preview-collapse {
  margin-top: 16px;
}

.preview-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}

.preview-body {
  min-height: 60px;
}

.prompt-block {
  background: var(--agnes-bg-dark-surface, #f5f5f5);
  border-radius: 6px;
  padding: 10px;
}

.prompt-label {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-bottom: 6px;
}

.prompt-text {
  font-size: 12px;
  color: var(--agnes-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  line-height: 1.5;
}
</style>

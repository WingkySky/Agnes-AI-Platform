<!-- =====================================================
     实体卡片 CharacterCard
     - 通用展示角色/场景/道具（结构相似）
     - 预览图 + 生成中遮罩
     - 操作：AI 生成 / 编辑 / 上传 / 删除 / 多选 / 版本切换器
     - 通过 entityType 区分字段差异
     ===================================================== -->

<template>
  <div
    class="entity-card"
    :class="{ selected: selected, generating: generating }"
    @click="$emit('toggle-select', entity.id)"
  >
    <!-- 预览图区域 -->
    <div class="card-preview">
      <img
        v-if="activeImage?.file_url"
        :src="activeImage.file_url"
        :alt="entity.name"
        class="preview-image"
      />
      <img
        v-else-if="activeImage?.thumbnail_url"
        :src="activeImage.thumbnail_url"
        :alt="entity.name"
        class="preview-image"
      />
      <div v-else class="preview-placeholder">
        <el-icon :size="36"><Picture /></el-icon>
        <span class="placeholder-text">暂无图像</span>
      </div>

      <!-- 选中标记 -->
      <div v-if="selected" class="select-mark">
        <el-icon><Check /></el-icon>
      </div>

      <!-- 生成中遮罩 -->
      <div v-if="generating" class="generating-mask">
        <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
        <span>生成中...</span>
      </div>

      <!-- 操作按钮浮层 -->
      <div v-if="!generating" class="card-overlay">
        <el-button
          v-if="projectStore.isEditable"
          type="primary"
          size="small"
          :icon="MagicStick"
          @click.stop="onGenerate"
        >AI 生成</el-button>
        <el-upload
          v-if="projectStore.isEditable"
          :show-file-list="false"
          :before-upload="onUpload"
          accept="image/*"
        >
          <el-button size="small" :icon="Upload" @click.stop>上传</el-button>
        </el-upload>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="card-body">
      <div class="card-title-row">
        <div class="card-title" :title="entity.name">{{ entity.name }}</div>
        <EntityVersionSwitcher
          v-if="activeImage"
          :entity-type="entityType"
          :entity-id="entity.id"
          :active-version="activeImage"
          @change="$emit('refresh')"
        />
      </div>

      <!-- 角色专属字段 -->
      <div v-if="entityType === 'character' && entity.role_type" class="card-tag">
        <el-tag size="small" type="info">{{ roleTypeLabel }}</el-tag>
      </div>

      <!-- 场景专属字段 -->
      <div v-if="entityType === 'scene'" class="card-tags-row">
        <el-tag v-if="entity.location" size="small" type="info">{{ entity.location }}</el-tag>
        <el-tag v-if="entity.time_of_day" size="small" type="info">{{ timeOfDayLabel }}</el-tag>
      </div>

      <!-- 描述（含视觉关键词） -->
      <div class="card-desc">
        {{ descriptionText }}
      </div>

      <!-- 底部操作 -->
      <div class="card-actions" @click.stop>
        <el-button
          v-if="projectStore.isEditable"
          link
          size="small"
          :icon="Edit"
          @click="onEdit"
        >编辑</el-button>
        <el-button
          v-if="projectStore.isEditable"
          link
          size="small"
          :icon="Delete"
          @click="onDelete"
        >删除</el-button>
        <el-button
          v-if="projectStore.isEditable"
          link
          size="small"
          :icon="Share"
          @click="onPromote"
        >入库</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Picture, Check, Loading, MagicStick, Upload, Edit, Delete, Share,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import EntityVersionSwitcher from './EntityVersionSwitcher.vue'
import type { EntityType, ProjectEntityAsset } from '@/types/project'

const props = defineProps<{
  entityType: EntityType
  entity: any
  /** 当前采用图像 */
  activeImage?: ProjectEntityAsset | null
  /** 是否选中（用于批量操作） */
  selected?: boolean
  /** 是否生成中 */
  generating?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-select', id: number): void
  (e: 'edit', entity: any): void
  (e: 'refresh'): void
}>()

const projectStore = useProjectStore()

// ---------- 计算属性 ----------
const roleTypeLabel = computed(() => {
  const map: Record<string, string> = {
    protagonist: '主角',
    supporting: '配角',
    antagonist: '反派',
    extra: '群演',
  }
  return map[props.entity.role_type] || props.entity.role_type
})

const timeOfDayLabel = computed(() => {
  const map: Record<string, string> = {
    dawn: '清晨', day: '白天', dusk: '黄昏', night: '夜晚',
  }
  return map[props.entity.time_of_day] || props.entity.time_of_day
})

const descriptionText = computed(() => {
  if (props.entityType === 'character') {
    return props.entity.appearance_desc || props.entity.description || '暂无描述'
  }
  if (props.entityType === 'scene') {
    return props.entity.atmosphere || props.entity.description || '暂无描述'
  }
  return props.entity.visual_desc || props.entity.description || '暂无描述'
})

// ---------- 操作 ----------
function onEdit() {
  emit('edit', props.entity)
}

async function onGenerate() {
  if (!props.entity?.id) return
  try {
    await ElMessageBox.confirm(
      `将调用 AI 为「${props.entity.name}」生成图像，是否继续？`,
      'AI 生成',
      { type: 'info', confirmButtonText: '开始生成', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.generateEntityImage(props.entityType, props.entity.id, {})
    ElMessage.success('生成任务已启动，请稍候')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  }
}

async function onUpload(file: File): Promise<boolean> {
  if (!props.entity?.id) return false
  try {
    await projectStore.uploadEntityImage(props.entityType, props.entity.id, file)
    ElMessage.success('图像已上传')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  }
  return false // 阻止 el-upload 默认上传行为
}

async function onDelete() {
  if (!props.entity?.id) return
  try {
    await ElMessageBox.confirm(
      `确定删除「${props.entity.name}」及其所有版本？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.deleteEntity(props.entityType, props.entity.id)
    ElMessage.success('已删除')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

async function onPromote() {
  if (!props.entity?.id) return
  try {
    await projectStore.promoteAsset({
      entity_type: props.entityType,
      entity_id: props.entity.id,
    })
    ElMessage.success('已推送到公共资产库')
  } catch (e: any) {
    ElMessage.error(e?.message || '入库失败')
  }
}
</script>

<style scoped>
.entity-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  position: relative;
}
.entity-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.entity-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}

.card-preview {
  position: relative;
  aspect-ratio: 4 / 3;
  background: var(--el-fill-color);
  overflow: hidden;
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
}
.placeholder-text { font-size: 12px; }

.select-mark {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.generating-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 13px;
}

.loading-icon {
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.card-overlay {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.entity-card:hover .card-overlay {
  opacity: 1;
}

.card-body {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-tag { display: flex; gap: 4px; }

.card-tags-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.card-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-actions {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding-top: 6px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
</style>

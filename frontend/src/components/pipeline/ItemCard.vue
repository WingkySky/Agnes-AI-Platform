<!--
  =====================================================
  ItemCard —— 流水线步骤产物元素卡片
  - 展示单个生成元素（角色/道具/场景/分镜图）的缩略图、名称、状态
  - 成功状态：图片预览 + 编辑下拉菜单（修改 prompt 重生 / 上传替换 / 删除）
  - 失败状态：红色占位 + 错误信息 + 醒目的「重试此张」按钮
  - 通过 props 接收 StepItem 数据，emits 通知父组件执行具体操作
  - 卡片网格底部「新增」按钮不在此组件内实现，由父组件 StepPanel 控制
  =====================================================
-->

<template>
  <div
    class="item-card"
    :class="[`status-${itemStatus}`, { 'is-failed': isFailed }]"
  >
    <!-- ===== 图片区：成功显示缩略图，失败显示红色占位 ===== -->
    <div class="card-cover">
      <!-- 成功且有图：el-image 支持点击预览大图 -->
      <el-image
        v-if="!isFailed && item.image_url"
        :src="item.image_url"
        :alt="item.name"
        fit="cover"
        :preview-src-list="previewList"
        :initial-index="0"
        :preview-teleported="true"
        class="cover-img"
      />
      <!-- 失败：红色占位区 -->
      <div v-else-if="isFailed" class="cover-failed">
        <el-icon :size="28" class="failed-icon"><WarningFilled /></el-icon>
        <span class="failed-cover-text">{{ t('pipelineResult.itemCard.failed') }}</span>
      </div>
      <!-- 无图占位（pending / running / 缺图） -->
      <div v-else class="cover-placeholder">
        <el-icon :size="28"><PictureFilled /></el-icon>
      </div>

      <!-- 状态徽章（左上角，所有状态都显示） -->
      <span class="status-badge" :class="itemStatus">
        {{ statusText }}
      </span>

      <!-- 编辑下拉菜单（仅成功状态显示，右上角） -->
      <el-dropdown
        v-if="itemStatus === 'success'"
        trigger="click"
        class="card-menu"
        @click.stop
      >
        <button type="button" class="menu-btn" @click.stop>
          <el-icon><MoreFilled /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <!-- 修改 prompt 重生 -->
            <el-dropdown-item @click="emit('regenerate', item.id)">
              <el-icon><EditPen /></el-icon>
              {{ t('pipelineResult.itemCard.regenerate') }}
            </el-dropdown-item>
            <!-- 上传替换 -->
            <el-dropdown-item @click="emit('upload', item.id)">
              <el-icon><Upload /></el-icon>
              {{ t('pipelineResult.itemCard.upload') }}
            </el-dropdown-item>
            <!-- 删除（危险项，分隔线区分） -->
            <el-dropdown-item divided class="danger-item" @click="emit('delete', item.id)">
              <el-icon><Delete /></el-icon>
              {{ t('pipelineResult.itemCard.delete') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- ===== 卡片正文：名称 + 状态相关内容 ===== -->
    <div class="card-body">
      <!-- 元素名称 -->
      <div class="card-name" :title="displayName">{{ displayName }}</div>

      <!-- 失败状态：错误信息 + 醒目的重试按钮 -->
      <template v-if="isFailed">
        <div class="card-error" :title="item.error || ''">
          {{ item.error || t('pipelineResult.itemCard.errorUnknown') }}
        </div>
        <el-button
          type="danger"
          size="small"
          class="retry-btn"
          @click="emit('retry', item.id)"
        >
          <el-icon><RefreshRight /></el-icon>
          {{ t('pipelineResult.itemCard.retryItem') }}
        </el-button>
      </template>

      <!-- 成功状态：展示 seed 元信息（可选，用于复现） -->
      <div v-else-if="item.seed != null" class="card-meta">
        <span class="meta-label">{{ t('pipelineResult.itemCard.seed') }}:</span>
        <span class="meta-value">{{ item.seed }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// ------ 引入依赖 ------
import { computed } from 'vue'
import { ElImage, ElDropdown, ElDropdownMenu, ElDropdownItem, ElButton, ElIcon } from 'element-plus'
import {
  MoreFilled,
  EditPen,
  Upload,
  Delete,
  RefreshRight,
  PictureFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { StepItem } from '@/api/pipeline'

// ------ Props：元素数据 / 所属步骤 key / 步骤类型 ------
const props = defineProps<{
  /** 元素数据（id, name, setting_text/description, image_url, status, seed, error） */
  item: StepItem
  /** 所属步骤 key */
  stepKey: string
  /** 步骤类型（用于决定展示方式，预留扩展） */
  stepType?: string
}>()

// ------ Emits：通知父组件执行具体操作 ------
// edit 当前未绑定到可见 UI，预留供父组件触发（如点击卡片名称进入编辑）
const emit = defineEmits<{
  (e: 'retry', itemId: string): void
  (e: 'edit', itemId: string): void
  (e: 'delete', itemId: string): void
  (e: 'regenerate', itemId: string): void
  (e: 'upload', itemId: string): void
}>()

const { t } = useI18n()

// ------ 元素状态（兼容老数据无 status 字段，默认按 success 处理） ------
const itemStatus = computed<'success' | 'failed' | 'pending' | 'running'>(
  () => props.item.status || 'success'
)
const isFailed = computed(() => itemStatus.value === 'failed')

// ------ 显示名称（无 name 时兜底） ------
const displayName = computed(() => props.item.name || t('pipelineResult.itemCard.untitled'))

// ------ 图片预览列表（el-image preview-src-list 需要数组形式） ------
const previewList = computed(() => (props.item.image_url ? [props.item.image_url] : []))

// ------ 状态徽章文案 ------
const statusText = computed(() => {
  switch (itemStatus.value) {
    case 'success': return t('pipelineResult.itemCard.success')
    case 'failed': return t('pipelineResult.itemCard.failed')
    case 'running': return t('pipelineResult.itemCard.running')
    case 'pending': return t('pipelineResult.itemCard.pending')
    default: return itemStatus.value
  }
})
</script>

<style scoped>
/* ===== 卡片容器：固定宽度 200px，高度自适应 ===== */
.item-card {
  width: 200px;
  background: var(--agnes-bg-hover);
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
  position: relative;
}
.item-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  border-color: var(--agnes-primary-border);
  transform: translateY(-2px);
}
/* 失败状态：红色边框高亮 */
.item-card.is-failed {
  border-color: var(--agnes-error-border);
}
.item-card.is-failed:hover {
  border-color: var(--agnes-error);
  box-shadow: 0 4px 16px var(--agnes-error-bg);
}

/* ===== 图片区：3:4 比例（角色/场景/分镜图常用竖图） ===== */
.card-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  background: var(--agnes-bg-page);
  overflow: hidden;
}
.cover-img {
  width: 100%;
  height: 100%;
  display: block;
}
/* 失败红色占位 */
.cover-failed {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--agnes-error-bg);
  color: var(--agnes-error);
}
.cover-failed .failed-icon {
  color: var(--agnes-error);
}
.failed-cover-text {
  font-size: 12px;
  color: var(--agnes-error);
}
/* 无图占位（pending / running / 缺图） */
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-placeholder);
  background: var(--agnes-bg-page);
}

/* ===== 状态徽章（左上角） ===== */
.status-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  backdrop-filter: blur(4px);
  pointer-events: none;
}
.status-badge.success {
  background: var(--agnes-success-bg);
  color: var(--agnes-success);
}
.status-badge.failed {
  background: var(--agnes-error-bg);
  color: var(--agnes-error);
}
.status-badge.pending,
.status-badge.running {
  background: var(--agnes-info-bg);
  color: var(--agnes-primary-soft);
}

/* ===== 编辑下拉菜单触发按钮（右上角） ===== */
.card-menu {
  position: absolute;
  top: 4px;
  right: 4px;
}
.menu-btn {
  background: rgba(0, 0, 0, 0.45);
  border: none;
  color: #fff;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  backdrop-filter: blur(4px);
  transition: background 0.2s ease;
}
.menu-btn:hover {
  background: rgba(0, 0, 0, 0.7);
}

/* ===== 卡片正文 ===== */
.card-body {
  padding: 8px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.card-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 失败：错误信息 + 重试按钮 ===== */
.card-error {
  font-size: 11px;
  color: var(--agnes-error);
  background: var(--agnes-error-bg);
  padding: 4px 6px;
  border-radius: 4px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.retry-btn {
  width: 100%;
}

/* ===== 成功：seed 元信息 ===== */
.card-meta {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
}
.meta-label {
  color: var(--agnes-text-placeholder);
}
.meta-value {
  color: var(--agnes-text-secondary);
}

/* ===== 下拉菜单中危险项（删除） ===== */
:deep(.danger-item) {
  color: var(--el-color-danger);
}
</style>

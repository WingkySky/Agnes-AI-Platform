<!--
  CanvasStepGroup.vue
  画布步骤分组可视化组件
  - 在流程模式下显示步骤分组框
  - 类似 Figma Frame，用半透明背景 + 彩色边框包裹节点
  - 显示步骤名称、执行顺序、状态
  - 增强视觉样式，让分组更明显
-->

<template>
  <div
    v-if="visible"
    class="step-group"
    :class="{ 'is-active': isActive }"
    :style="groupStyle"
    :data-step-id="step.id"
    @click="handleClick"
  >
    <!-- 步骤标题栏 -->
    <div class="step-header" :style="headerStyle">
      <span class="step-order">{{ step.order + 1 }}</span>
      <span class="step-name">{{ step.name }}</span>
      <span class="step-count">{{ step.panel_ids.length }} 个节点</span>
      <span class="step-status">
        <el-icon v-if="effectiveStatus === 'pending'" :size="14"><Clock /></el-icon>
        <el-icon v-else-if="effectiveStatus === 'running'" :size="14"><Loader2 /></el-icon>
        <el-icon v-else-if="effectiveStatus === 'success'" :size="14"><Check /></el-icon>
        <el-icon v-else-if="effectiveStatus === 'failed'" :size="14"><X /></el-icon>
      </span>
    </div>
    
    <!-- 步骤操作按钮（hover 时显示） -->
    <div v-if="isActive" class="step-actions">
      <button
        class="step-action-btn"
        :title="t('canvas.step.edit')"
        @click.stop="handleEdit"
      >
        <Edit :size="14" />
      </button>
      <button
        class="step-action-btn"
        :title="t('canvas.step.delete')"
        @click.stop="handleDelete"
      >
        <Trash2 :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { CanvasStep } from '@/stores/canvas'
import { calculateStepBounds } from '@/lib/canvas-flow-analyzer'
import { Clock, Loader2, Check, X, Edit, Trash2 } from 'lucide-vue-next'

const { t } = useI18n()

const props = defineProps({
  step: {
    type: Object as () => CanvasStep,
    required: true,
  },
  panels: {
    type: Array as () => any[],
    required: true,
  },
  isActive: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['click', 'edit', 'delete'])

// 计算分组框是否可见（至少有一个节点在画布上）
const visible = computed(() => {
  return props.step.panel_ids.length > 0
})

// 计算分组框的样式（根据包含的节点位置自动调整）
const groupStyle = computed(() => {
  const bounds = calculateStepBounds(props.step, props.panels)
  if (!bounds) return { display: 'none' }
  
  return {
    left: `${bounds.left}px`,
    top: `${bounds.top}px`,
    width: `${bounds.width}px`,
    height: `${bounds.height}px`,
  }
})

// 计算标题栏样式（不同步骤用不同颜色）
const headerStyle = computed(() => {
  // 预设几种颜色，按步骤顺序循环使用
  const colors = [
    '#409eff', // 蓝
    '#67c23a', // 绿
    '#e6a23c', // 橙
    '#f56c6c', // 红
    '#9b59b6', // 紫
    '#1abc9c', // 青
  ]
  const color = colors[props.step.order % colors.length]
  return {
    background: color,
    color: '#fff',
    borderBottom: `2px solid ${color}`,
  }
})

// 计算有效步骤状态（根据节点 content.status 动态计算）
const effectiveStatus = computed(() => {
  const panelStatuses = props.panels
    .filter(p => props.step.panel_ids.includes(p.id))
    .map(p => (p.content as any)?.status || 'idle')

  if (panelStatuses.some(s => s === 'loading')) return 'running'
  if (panelStatuses.some(s => s === 'error')) return 'failed'
  if (panelStatuses.length > 0 && panelStatuses.every(s => s === 'success')) return 'success'
  return 'pending'
})

// 处理点击
function handleClick(event: MouseEvent) {
  emit('click', props.step.id)
}

// 处理编辑
function handleEdit() {
  emit('edit', props.step.id)
}

// 处理删除
function handleDelete() {
  emit('delete', props.step.id)
}
</script>

<style scoped>
.step-group {
  position: absolute;
  background: rgba(64, 158, 255, 0.06);
  border: 3px solid;
  border-radius: 14px;
  pointer-events: auto;
  z-index: 0;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 0 20px rgba(64, 158, 255, 0.08);
  animation: step-appear 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes step-appear {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.step-group:hover {
  background: rgba(64, 158, 255, 0.12);
  box-shadow: 0 0 30px rgba(64, 158, 255, 0.2);
}

.step-group.is-active {
  background: rgba(64, 158, 255, 0.15);
  box-shadow: 0 0 40px rgba(64, 158, 255, 0.3);
  border-width: 4px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 10px 10px 0 0;
  font-size: 12px;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.step-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  background: rgba(255, 255, 255, 0.3);
  color: #fff;
  border-radius: 50%;
  font-weight: bold;
  font-size: 11px;
  flex-shrink: 0;
}

.step-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.step-count {
  font-size: 10px;
  opacity: 0.8;
  background: rgba(255, 255, 255, 0.2);
  padding: 2px 6px;
  border-radius: 8px;
  flex-shrink: 0;
}

.step-status {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.step-actions {
  position: absolute;
  top: 6px;
  right: 6px;
  display: flex;
  gap: 4px;
  z-index: 2;
}

.step-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: rgba(255, 255, 255, 0.25);
  border: none;
  border-radius: 6px;
  color: #fff;
  cursor: pointer;
  transition: all 0.15s ease;
  backdrop-filter: blur(4px);
}

.step-action-btn:hover {
  background: rgba(255, 255, 255, 0.4);
  transform: scale(1.1);
}
</style>

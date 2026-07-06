<!-- =====================================================
     可拖拽分隔条组件 TimelineSplitter
     - 支持 horizontal（水平分隔，调整高度）/ vertical（垂直分隔，调整宽度）
     - 通过 v-model 绑定值，拖拽时实时 emit
     ===================================================== -->

<template>
  <div
    class="timeline-splitter"
    :class="direction"
    @mousedown="onMouseDown"
  >
    <div class="splitter-handle">
      <span v-if="direction === 'vertical'">⋮</span>
      <span v-else>⋯</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: number
  direction?: 'horizontal' | 'vertical'
  min?: number
  max?: number
}>(), {
  direction: 'vertical',
  min: 120,
  max: 600,
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: number): void
  (e: 'drag-start'): void
  (e: 'drag-end'): void
}>()

const dragging = ref(false)

function onMouseDown(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  dragging.value = true
  emit('drag-start')

  const startPos = props.direction === 'vertical' ? e.clientX : e.clientY
  const startValue = props.modelValue

  function onMove(ev: MouseEvent) {
    if (!dragging.value) return
    const currentPos = props.direction === 'vertical' ? ev.clientX : ev.clientY
    // vertical：拖右→值增；horizontal：拖下→值增
    const delta = currentPos - startPos
    const newVal = startValue + delta
    const clamped = Math.min(props.max, Math.max(props.min, newVal))
    emit('update:modelValue', clamped)
  }

  function onUp() {
    dragging.value = false
    emit('drag-end')
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.body.style.cursor = props.direction === 'vertical' ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'
}
</script>

<style scoped>
.timeline-splitter {
  background: var(--el-border-color, #3a3d44);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.15s;
  user-select: none;
}

.timeline-splitter.vertical {
  width: 6px;
  cursor: col-resize;
  height: 100%;
}

.timeline-splitter.horizontal {
  height: 6px;
  cursor: row-resize;
  width: 100%;
  margin: 4px 0;
}

.timeline-splitter:hover,
.timeline-splitter.dragging {
  background: var(--el-color-primary, #4a9eff);
}

.splitter-handle {
  color: var(--el-text-color-placeholder, #666);
  font-size: 10px;
  line-height: 1;
}
</style>

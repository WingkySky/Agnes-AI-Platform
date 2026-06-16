<!-- =====================================================
     面板薄壳
     - 任务 1 重构：把通用节点能力（定位/拖拽/缩放/选中/锚点/工具栏/右键）
       抽到 item-types/BaseNode.vue
     - 本组件只负责把 panel prop 透传给 BaseNode，并转发事件
     ===================================================== -->
<template>
  <BaseNode
    :panel="panel"
    @update="(c) => emit('update', c)"
    @contextmenu="(e) => emit('contextmenu', e)"
    @panel-edit="(p) => emit('panel-edit', p)"
  />
</template>

<script setup>
import BaseNode from './item-types/BaseNode.vue'

defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update', 'contextmenu', 'panel-edit'])
</script>

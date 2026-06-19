<!-- =====================================================
     ConfigNode —— 配置/批量生成节点内容组件
     - 配置模型 / 尺寸 / 数量
     - 此节点通常作为上游节点的参数源，不直接调用 taskQueue
     ===================================================== -->

<template>
  <div class="config-node">
    <!-- 模型 -->
    <div class="node-row">
      <label class="node-field-label">模型</label>
      <select
        class="node-field-select"
        :value="panel.content?.model || 'sdxl'"
        @change="(e) => $emit('update-content', { model: e.target.value })"
      >
        <option value="sdxl">SDXL</option>
        <option value="flux">Flux</option>
        <option value="sd3">SD 3</option>
      </select>
    </div>

    <!-- 尺寸 -->
    <div class="node-row">
      <label class="node-field-label">尺寸</label>
      <select
        class="node-field-select"
        :value="panel.content?.size || '1:1'"
        @change="(e) => $emit('update-content', { size: e.target.value })"
      >
        <option value="1:1">1:1</option>
        <option value="16:9">16:9</option>
        <option value="9:16">9:16</option>
        <option value="4:3">4:3</option>
      </select>
    </div>

    <!-- 数量 -->
    <div class="node-row">
      <label class="node-field-label">数量</label>
      <input
        type="number"
        min="1"
        max="20"
        class="node-field-input"
        :value="panel.content?.count || 1"
        @input="(e) => $emit('update-content', { count: Number(e.target.value) || 1 })"
      />
    </div>

    <!-- 提示信息 -->
    <div class="config-node-hint">
      <el-icon :size="12" style="margin-right:4px"><InfoFilled /></el-icon>
      <span>将此节点连接到上游的 text / image 节点，组合生成内容</span>
    </div>
  </div>
</template>

<script setup>
/* ConfigNode 组件：
 * - 通过 props.panel 接收节点数据
 * - 所有用户操作通过 emit('update-content', patch) 转发到父组件
 * - 父组件负责将 patch 写入 panel.content */

import { InfoFilled } from '@element-plus/icons-vue'

defineProps({ panel: { type: Object, required: true } })
defineEmits(['update-content', 'update-status'])
</script>

<style scoped>
.config-node {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.node-field-label {
  width: 44px;
  flex-shrink: 0;
  font-size: 11px;
  color: #8ba3c9;
}

.node-field-input,
.node-field-select {
  flex: 1;
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 230, 0.2);
  border-radius: 6px;
  color: #e8eef7;
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}

.config-node-hint {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  font-size: 11px;
  color: #8ba3c9;
  background: rgba(120, 170, 230, 0.08);
  border-radius: 6px;
  line-height: 1.5;
}
</style>

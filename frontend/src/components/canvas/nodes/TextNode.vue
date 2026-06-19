<!-- =====================================================
     TextNode —— 文本节点内容组件
     - 主要职责：展示并编辑文本节点的「文本 / 提示词」
     - 从 props.panel 读取当前状态；通过 emit('update-content') 更新
     ===================================================== -->

<template>
  <div class="text-node">
    <!-- 文本内容（主体） -->
    <div class="node-field">
      <label class="node-field-label">文本内容</label>
      <textarea
        class="node-field-textarea"
        :value="panel.content?.text || ''"
        placeholder="在此输入文本内容..."
        rows="4"
        @input="(e) => $emit('update-content', { text: e.target.value })"
      />
    </div>

    <!-- 提示词（可选，作为生成的输入） -->
    <div class="node-field">
      <label class="node-field-label">提示词（可选）</label>
      <input
        class="node-field-input"
        type="text"
        :value="panel.content?.prompt || ''"
        placeholder="可填写对应的生成提示词"
        @input="(e) => $emit('update-content', { prompt: e.target.value })"
      />
    </div>
  </div>
</template>

<script setup>
/* =====================================================
 * 文本节点 —— 轻量组件，无状态管理，仅做表单双向绑定
 * props.panel.content.text / content.prompt
 ===================================================== */

/* 只通过 props.panel 传入节点状态；
 * 所有用户操作通过 emit('update-content', patch) 通知父组件写入 store */
defineProps({
  panel: {
    type: Object,
    required: true,
  },
})

defineEmits(['update-content'])
</script>

<style scoped>
.text-node {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-field {
  display: flex;
  flex-direction: column;
}

.node-field-label {
  display: block;
  font-size: 11px;
  color: #8ba3c9;
  margin-bottom: 4px;
}

.node-field-input,
.node-field-textarea {
  width: 100%;
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 230, 0.2);
  border-radius: 6px;
  color: #e8eef7;
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
}

.node-field-textarea {
  resize: vertical;
  min-height: 64px;
}
</style>

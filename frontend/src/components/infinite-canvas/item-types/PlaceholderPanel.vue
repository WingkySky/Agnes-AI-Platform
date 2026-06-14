/* =====================================================
 * 占位面板
 * - 空白面板，用户自定义内容
 * ===================================================== */

<template>
  <div class="placeholder-panel" @dblclick="$emit('update', { content: { custom: '' } })">
    <p class="placeholder-hint">{{ t('canvas.customPlaceholder') }}</p>
  </div>
</template>

<script setup>
import { useI18n } from '@/i18n'

const { t } = useI18n()
defineEmits(['update'])
</script>

<style scoped>
.placeholder-panel {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgba(15, 22, 38, 0.3);
  cursor: pointer;
}

.placeholder-hint {
  color: #4a6080;
  font-size: 12px;
  text-align: center;
}
</style>

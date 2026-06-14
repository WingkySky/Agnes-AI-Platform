/* =====================================================
 * URL 链接面板
 * - iframe 嵌入网页
 * - 可输入 URL 和标题
 * ===================================================== */

<template>
  <div class="url-panel">
    <div v-if="!url" class="url-input-area">
      <el-input
        v-model="inputUrl"
        :placeholder="t('canvas.enterUrl')"
        size="small"
        @keydown.enter="loadUrl"
      >
        <template #append>
          <el-button @click="loadUrl">加载</el-button>
        </template>
      </el-input>
    </div>
    <template v-else>
      <iframe :src="url" class="url-iframe" sandbox="allow-scripts allow-same-origin" />
      <div class="url-close">
        <el-icon @click="url = ''"><Close /></el-icon>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update'])

const url = ref(props.panel.content?.url ?? '')
const inputUrl = ref(url.value)

function loadUrl() {
  let u = inputUrl.value.trim()
  if (!u) return
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u
  url.value = u
  emit('update', { content: { url: u } })
}
</script>

<style scoped>
.url-panel {
  width: 100%;
  height: 100%;
  position: relative;
}

.url-input-area {
  padding: 8px;
}

.url-iframe {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 6px;
}

.url-close {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 10;
}

.url-close .el-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 22, 38, 0.8);
  border-radius: 50%;
  color: #ff6b6b;
  cursor: pointer;
  font-size: 14px;
}
</style>

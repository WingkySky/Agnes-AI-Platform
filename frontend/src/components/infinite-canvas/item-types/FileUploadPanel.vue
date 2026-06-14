/* =====================================================
 * 文件上传面板
 * - 拖拽上传区域
 * - 支持图片/视频文件
 * - 上传后预览
 * ===================================================== */

<template>
  <div
    class="file-upload-panel"
    :class="{ 'is-dragover': isDragover }"
    @dragover.prevent="isDragover = true"
    @dragleave="isDragover = false"
    @drop.prevent="handleDrop"
  >
    <input
      ref="fileInput"
      type="file"
      accept="image/*,video/*"
      multiple
      class="file-input"
      @change="handleFileSelect"
    />

    <div v-if="files.length === 0" class="upload-placeholder" @click="$refs.fileInput?.click()">
      <el-icon :size="32"><Upload /></el-icon>
      <p>{{ t('canvas.dragOrClick') }}</p>
      <span class="upload-hint">{{ t('canvas.uploadHint') }}</span>
    </div>

    <div v-else class="file-preview">
      <div
        v-for="(file, idx) in files"
        :key="idx"
        class="file-item"
      >
        <img
          v-if="file.type.startsWith('image/')"
          :src="file.url"
          class="preview-thumb"
        />
        <video
          v-else-if="file.type.startsWith('video/')"
          :src="file.url"
          class="preview-thumb"
        />
        <span class="file-name">{{ file.name }}</span>
        <el-icon class="file-remove" @click="removeFile(idx)"><Close /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Upload, Close } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update'])

const isDragover = ref(false)
const fileInput = ref(null)
const files = ref([])

// 监听面板内容变化（从外部恢复）
watch(
  () => props.panel.content?.files,
  (val) => {
    if (val) files.value = val
  },
  { immediate: true, deep: true },
)

function handleFileSelect(e) {
  processFiles(e.target.files)
}

function handleDrop(e) {
  isDragover.value = false
  processFiles(e.dataTransfer.files)
}

function processFiles(fileList) {
  const newFiles = Array.from(fileList).map((file) => ({
    name: file.name,
    type: file.type,
    url: URL.createObjectURL(file),
  }))
  files.value = [...files.value, ...newFiles]
  emit('update', { content: { files: files.value } })
}

function removeFile(idx) {
  files.value.splice(idx, 1)
  emit('update', { content: { files: files.value } })
}
</script>

<style scoped>
.file-upload-panel {
  width: 100%;
  height: 100%;
  border: 2px dashed rgba(100, 150, 220, 0.2);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s, background 0.2s;
  overflow: hidden;
}

.file-upload-panel.is-dragover {
  border-color: #508cff;
  background: rgba(80, 140, 255, 0.06);
}

.file-input {
  display: none;
}

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #6b84aa;
  cursor: pointer;
}

.upload-hint {
  font-size: 11px;
  color: #4a6080;
}

.file-preview {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: flex-start;
}

.file-item {
  position: relative;
  width: calc(50% - 3px);
  aspect-ratio: 16/9;
  background: rgba(15, 22, 38, 0.5);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-thumb {
  max-width: 100%;
  max-height: 100%;
  object-fit: cover;
  border-radius: 4px;
}

.file-name {
  font-size: 10px;
  color: #8ba3c9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 90%;
}

.file-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 12px;
  color: #ff6b6b;
  cursor: pointer;
  background: rgba(15, 22, 38, 0.8);
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>

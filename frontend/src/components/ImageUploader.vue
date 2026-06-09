<!-- =====================================================
     ImageUploader 图片上传组件
     - 支持拖拽上传 / 选择文件 / 粘贴图片 URL
     - 将本地文件转换为 base64（不含 data:image/... 前缀）
     - 事件：@change(fileInfo)  @clear
     fileInfo 格式:
       {
         name: 'xxx.png',
         base64: '...',    // 不带前缀的纯 base64 字符串
         previewUrl: 'data:image/...;base64,...',
         size: 1024000,
         source: 'file' | 'url'
       }
     ===================================================== -->

<template>
  <div class="image-uploader">
    <!-- 标题国际化 -->
    <div class="section-title">
      {{ t('params.refImage') }}{{ optional ? '（' + t('common.optional') + '）' : '' }}
    </div>

    <!-- 模式切换 -->
    <div class="mode-switch">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="file">{{ t('params.uploadLocal') }}</el-radio-button>
        <el-radio-button value="url">{{ t('params.pasteUrl') }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 已上传预览 -->
    <div v-if="currentFile" class="preview-wrap">
      <img :src="currentFile.previewUrl" class="preview-img" :alt="t('common.preview')" />
      <div class="preview-info">
        <div class="preview-name">{{ currentFile.name }}</div>
        <div class="preview-size">{{ formatSize(currentFile.size) }}</div>
        <el-button size="small" type="danger" plain @click="clearFile">
          <el-icon><Delete /></el-icon>
          {{ t('params.remove') }}
        </el-button>
      </div>
    </div>

    <!-- 上传区（文件模式） -->
    <div v-else-if="mode === 'file'" class="upload-zone"
         @dragover.prevent="isDragOver = true"
         @dragleave.prevent="isDragOver = false"
         @drop.prevent="handleDrop"
         @click="$refs.fileInput.click()"
         :class="{ 'drag-over': isDragOver }">
      <el-icon :size="36" class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-hint">{{ t('params.uploadHint') }}</div>
      <div class="upload-desc">{{ t('params.uploadDesc').replace('{n}', maxSizeMB) }}</div>
      <input ref="fileInput" type="file" accept="image/*" class="hidden-input" @change="handleFileChange" />
    </div>

    <!-- URL 模式 -->
    <div v-else class="url-zone">
      <el-input
        v-model="urlInput"
        :placeholder="t('params.urlPlaceholder')"
        @keydown.enter="handleUrlConfirm"
      >
        <template #append>
          <el-button @click="handleUrlConfirm">{{ t('common.confirm') }}</el-button>
        </template>
      </el-input>
      <div class="url-hint">{{ t('params.urlHint') }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, UploadFilled } from '@element-plus/icons-vue'
// ------ 引入 i18n ------
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  maxSizeMB: { type: Number, default: 10 },
  optional: { type: Boolean, default: false }
})

const emit = defineEmits(['change', 'clear'])

const mode = ref('file')
const urlInput = ref('')
const currentFile = ref(null)
const isDragOver = ref(false)
const fileInput = ref(null)

// 每次模式切换清空
watch(mode, () => {
  if (currentFile.value) {
    clearFile()
  }
})

// 格式化文件大小
function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

// 校验文件
function validateFile(file) {
  const maxBytes = props.maxSizeMB * 1024 * 1024
  if (file.size > maxBytes) {
    ElMessage.error(t('params.imageTooLarge').replace('{n}', props.maxSizeMB))
    return false
  }
  if (!file.type || !file.type.startsWith('image/')) {
    ElMessage.error(t('params.imageInvalid'))
    return false
  }
  return true
}

// 文件 → base64（不含前缀）
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const fullBase64 = reader.result // data:image/png;base64,...
      const pureBase64 = fullBase64.split(';base64,')[1]
      resolve({
        name: file.name,
        base64: pureBase64,
        previewUrl: fullBase64,
        size: file.size,
        source: 'file'
      })
    }
    reader.onerror = () => reject(new Error('read_failed'))
    reader.readAsDataURL(file)
  })
}

async function handleFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  if (!validateFile(file)) return
  try {
    currentFile.value = await fileToBase64(file)
    emit('change', currentFile.value)
  } catch (err) {
    ElMessage.error(t('params.imageParseFailed'))
  }
  e.target.value = ''
}

function handleDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    if (!validateFile(file)) return
    fileToBase64(file).then((info) => {
      currentFile.value = info
      emit('change', info)
    }).catch(() => ElMessage.error(t('params.imageParseFailed')))
  }
}

function handleUrlConfirm() {
  const url = urlInput.value.trim()
  if (!url) return
  if (!/^https?:\/\//i.test(url)) {
    ElMessage.error(t('params.urlInvalid'))
    return
  }
  currentFile.value = {
    name: url.split('/').pop() || 'image',
    base64: null, // URL 模式不转 base64，直接提交 URL
    previewUrl: url,
    size: null,
    source: 'url',
    url
  }
  emit('change', currentFile.value)
}

function clearFile() {
  currentFile.value = null
  urlInput.value = ''
  emit('clear')
}
</script>

<style scoped>
.image-uploader {
  margin-bottom: 16px;
}
.section-title {
  font-size: 13px;
  color: #a0b4d6;
  margin-bottom: 10px;
  font-weight: 500;
}
.mode-switch {
  margin-bottom: 12px;
}
.hidden-input { display: none; }

.upload-zone {
  border: 2px dashed rgba(120, 170, 255, 0.3);
  border-radius: 12px;
  padding: 32px;
  text-align: center;
  background: rgba(15, 24, 42, 0.4);
  cursor: pointer;
  transition: all 0.2s ease;
}
.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #6b9cff;
  background: rgba(90, 134, 255, 0.08);
}
.upload-icon { color: #6b9cff; margin-bottom: 8px; }
.upload-hint { color: #d5e3f7; font-weight: 500; margin-bottom: 4px; }
.upload-desc { color: #6b84aa; font-size: 12px; }

.preview-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: rgba(15, 24, 42, 0.5);
  border: 1px solid rgba(120, 170, 255, 0.2);
  border-radius: 12px;
}
.preview-img {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
}
.preview-info { flex: 1; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.preview-name { font-weight: 500; color: #e8eef7; word-break: break-all; }
.preview-size { color: #6b84aa; font-size: 12px; }

.url-zone {
  background: rgba(15, 24, 42, 0.4);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(120, 170, 255, 0.2);
}
.url-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #6b84aa;
}
</style>

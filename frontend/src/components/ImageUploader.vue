<!-- =====================================================
     ImageUploader 图片上传组件（统一输入区）
     - 单一上传区域，统一支持：
       1) 点击 / 拖拽 上传本地图片
       2) 全局粘贴图片（截图直接 Ctrl+V）
       3) 全局粘贴图片 URL（自动识别 http(s) 链接）
       4) 下方 URL 输入框作为辅助手动输入
     - 已上传的图片预览始终显示在顶部
     - 支持 maxCount 限制上传数量（默认不限）
     - 事件：@change(fileInfoList)
             @clear
     fileInfo 格式:
       {
         name: 'xxx.png',
         base64: '...',    // 不带前缀的纯 base64（本地文件）或 null（URL）
         previewUrl: 'data:image/png;base64,...' 或 'https://...',
         mimeType: 'image/png',
         size: 1024000,     // 本地文件有值，URL 为 null
         source: 'file' | 'url',
         url: 'https://...' // URL 模式下的原始地址
       }
     ===================================================== -->

<template>
  <div class="image-uploader" ref="uploaderRef">
    <!-- 标题 -->
    <div class="uploader-header">
      <span class="uploader-title">{{ title || t('params.refImage') }}{{ optional ? '（' + t('common.optional') + '）' : '' }}</span>
      <span class="uploader-hint">
        已上传 <b>{{ fileList.length }}</b> 张
        <template v-if="maxCount"> / 最多 {{ maxCount }} 张</template>
      </span>
    </div>

    <!-- 已上传预览：网格 -->
    <div v-if="fileList.length > 0" class="file-grid">
      <div
        v-for="(file, idx) in fileList"
        :key="idx"
        class="file-card"
      >
        <img
          :src="file.previewUrl"
          class="file-preview-img"
          :alt="file.name"
          @click="openPreview(file.previewUrl)"
        />
        <div class="file-meta">
          <div class="file-name" :title="file.name">{{ truncateName(file.name, 22) }}</div>
          <div v-if="file.size" class="file-size">{{ formatSize(file.size) }}</div>
          <div class="file-source">{{ file.source === 'url' ? 'URL' : t('common.local') }}</div>
        </div>
        <el-button
          size="small"
          type="danger"
          plain
          @click="removeFile(idx)"
          class="del-btn"
        >
          <el-icon><Delete /></el-icon>
          {{ t('params.remove') }}
        </el-button>
      </div>
    </div>

    <!-- 添加图片区域（未达上限时显示） -->
    <div v-if="!maxCount || fileList.length < maxCount" class="add-area">
      <!-- 统一上传区域：点击 / 拖拽 / 粘贴 -->
      <div
        class="upload-zone"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="handleDrop"
        @click="$refs.fileInput.click()"
        :class="{ 'drag-over': isDragOver, 'paste-active': pasteHighlight }"
      >
        <el-icon :size="32" class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-hint">{{ t('params.uploadHintUnified') }}</div>
        <div class="upload-desc">{{ t('params.uploadDescUnified').replace('{n}', maxSizeMB) }}</div>
        <div class="paste-hint">
          <el-icon><Document /></el-icon>
          <span>{{ t('params.pasteHint') }}</span>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          :multiple="!maxCount || maxCount > 1"
          class="hidden-input"
          @change="handleFilesChange"
        />
      </div>

    </div>

    <!-- 已达上限提示 -->
    <div v-else class="limit-hint">
      已达上传上限（{{ maxCount }} 张）
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, UploadFilled, Document } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  maxSizeMB: { type: Number, default: 10 },
  optional: { type: Boolean, default: false },
  maxCount: { type: Number, default: 0 },      // 0 表示不限制
  title: { type: String, default: '' },         // 自定义标题
  disableGlobalPaste: { type: Boolean, default: false }, // 多实例场景（如首尾帧）禁用全局粘贴，避免冲突
})

const emit = defineEmits(['change', 'clear'])

const fileList = ref([])
const isDragOver = ref(false)
const fileInput = ref(null)
const uploaderRef = ref(null)
const pasteHighlight = ref(false)  // 粘贴时的高亮反馈

// =====================================================
// 对外暴露（父组件调用）
// =====================================================
defineExpose({
  getFiles: () => fileList.value,
  clearFiles: () => {
    fileList.value = []
    emit('clear')
    emit('change', null)
  },
})

// =====================================================
// 全局粘贴事件监听
// 智能识别剪贴板内容：
//   - 图片类型（截图）→ 直接添加为本地文件
//   - 文本类型 → 检查是否为 URL，是则添加为 URL 模式
//   - 焦点在 input/textarea/contenteditable 中时不拦截文本粘贴
// =====================================================
let pasteTimer = null

function handleGlobalPaste(e) {
  // 多实例场景（如首尾帧）禁用全局粘贴，避免一次粘贴同时进入多个实例
  if (props.disableGlobalPaste) return

  const clipboard = e.clipboardData || window.clipboardData
  if (!clipboard) return

  // 1) 优先检查剪贴板中是否有图片
  const items = clipboard.items || []
  let hasImage = false
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      hasImage = true
      const file = item.getAsFile()
      if (file) {
        // 拦截事件，避免图片被插入到其他输入框
        e.preventDefault()
        addPastedImageFile(file)
      }
    }
  }
  if (hasImage) return

  // 2) 检查剪贴板文本是否为图片 URL
  //    仅当焦点不在输入框中时拦截，避免影响用户在 prompt 等输入框中粘贴文本
  const activeEl = document.activeElement
  const isEditingText =
    activeEl &&
    (activeEl.tagName === 'INPUT' ||
      activeEl.tagName === 'TEXTAREA' ||
      activeEl.isContentEditable === true)

  if (isEditingText) return

  const text = (clipboard.getData('text') || '').trim()
  if (!text) return

  // 简单识别 http(s) URL
  if (/^https?:\/\//i.test(text)) {
    e.preventDefault()
    addPastedUrl(text)
  }
}

// 触发粘贴高亮反馈
function triggerPasteHighlight() {
  pasteHighlight.value = true
  if (pasteTimer) clearTimeout(pasteTimer)
  pasteTimer = setTimeout(() => {
    pasteHighlight.value = false
  }, 600)
}

// =====================================================
// 工具函数
// =====================================================
function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

function truncateName(name, max) {
  if (!name) return ''
  if (name.length <= max) return name
  return name.slice(0, max - 3) + '...'
}

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

// File -> base64（清理 padding + 提取 MIME）
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const fullBase64 = reader.result
      const marker = ';base64,'
      const markerIndex = fullBase64.indexOf(marker)
      let mimeType = 'image/png'
      if (markerIndex >= 0) {
        const prefixPart = fullBase64.slice(0, markerIndex)
        const mimeMatch = prefixPart.match(/^data:(image\/[a-zA-Z0-9.+-]+)/)
        if (mimeMatch) mimeType = mimeMatch[1]
      }
      let pureBase64 = markerIndex >= 0
        ? fullBase64.slice(markerIndex + marker.length)
        : fullBase64
      pureBase64 = pureBase64.replace(/\s/g, '')
      const padNeeded = pureBase64.length % 4
      if (padNeeded) {
        pureBase64 += '='.repeat(4 - padNeeded)
      }
      resolve({
        name: file.name,
        base64: pureBase64,
        previewUrl: fullBase64,
        mimeType,
        size: file.size,
        source: 'file',
      })
    }
    reader.onerror = () => reject(new Error('read_failed'))
    reader.readAsDataURL(file)
  })
}

function emitChange() {
  emit('change', fileList.value.length ? fileList.value : null)
}

// 检查是否已达上限
function checkLimit() {
  if (props.maxCount && fileList.value.length >= props.maxCount) {
    ElMessage.warning(`已达上传上限（${props.maxCount} 张）`)
    return false
  }
  return true
}

// =====================================================
// 添加图片（统一入口）
// =====================================================
async function addPastedImageFile(file) {
  if (!checkLimit()) return
  if (!validateFile(file)) return
  try {
    const info = await fileToBase64(file)
    fileList.value.push(info)
    ElMessage.success(`已粘贴图片（共 ${fileList.value.length} 张）`)
    triggerPasteHighlight()
    emitChange()
  } catch {
    ElMessage.error(t('params.imageParseFailed'))
  }
}

function addPastedUrl(url) {
  if (!checkLimit()) return
  fileList.value.push({
    name: url.split('/').pop() || 'image',
    base64: null,
    previewUrl: url,
    size: null,
    source: 'url',
    url,
    mimeType: 'image/png',
  })
  ElMessage.success(`已粘贴 URL 图片（共 ${fileList.value.length} 张）`)
  triggerPasteHighlight()
  emitChange()
}

// =====================================================
// 文件选择
// =====================================================
async function handleFilesChange(e) {
  const input = e.target
  const files = Array.from(input.files || [])
  if (files.length === 0) return

  const remaining = props.maxCount ? props.maxCount - fileList.value.length : files.length
  if (remaining <= 0) {
    ElMessage.warning(`已达上传上限（${props.maxCount} 张）`)
    return
  }

  const filesToAdd = files.slice(0, remaining)
  if (files.length > remaining) {
    ElMessage.warning(`仅添加前 ${remaining} 张，已达上限（${props.maxCount} 张）`)
  }

  let added = 0
  for (const file of filesToAdd) {
    if (!validateFile(file)) continue
    try {
      const info = await fileToBase64(file)
      fileList.value.push(info)
      added++
    } catch {
      ElMessage.error(t('params.imageParseFailed'))
    }
  }
  if (added > 0) {
    ElMessage.success(`已添加 ${added} 张图片（共 ${fileList.value.length} 张）`)
  }
  emitChange()
  if (input) input.value = ''
}

// =====================================================
// 拖拽
// =====================================================
async function handleDrop(e) {
  isDragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length === 0) return

  const remaining = props.maxCount ? props.maxCount - fileList.value.length : files.length
  if (remaining <= 0) {
    ElMessage.warning(`已达上传上限（${props.maxCount} 张）`)
    return
  }

  const filesToAdd = files.slice(0, remaining)
  const results = []
  for (const file of filesToAdd) {
    if (!validateFile(file)) continue
    try {
      const info = await fileToBase64(file)
      results.push(info)
    } catch {
      ElMessage.error(t('params.imageParseFailed'))
    }
  }
  if (results.length > 0) {
    fileList.value.push(...results)
    ElMessage.success(`已添加 ${results.length} 张图片（共 ${fileList.value.length} 张）`)
    emitChange()
  }
}

// =====================================================
// 单张删除
// =====================================================
function removeFile(index) {
  const name = fileList.value[index]?.name
  fileList.value.splice(index, 1)
  if (name) ElMessage.info(`已移除: ${name}`)
  emitChange()
}

// =====================================================
// 预览大图
// =====================================================
function openPreview(url) {
  if (!url) return
  try {
    const w = window.open()
    if (w) {
      w.document.write(
        `<img src="${url}" style="max-width:100%;display:block;margin:auto;">`
      )
    }
  } catch (e) {
    console.warn('[ImageUploader] 预览打开失败', e)
  }
}

// =====================================================
// 生命周期：挂载/卸载全局 paste 监听
// =====================================================
onMounted(() => {
  window.addEventListener('paste', handleGlobalPaste)
})

onBeforeUnmount(() => {
  window.removeEventListener('paste', handleGlobalPaste)
  if (pasteTimer) clearTimeout(pasteTimer)
})
</script>

<style scoped>
.image-uploader {
  margin-bottom: 12px;
}

/* 标题区 */
.uploader-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding: 0 2px;
}
.uploader-title {
  font-size: 14px;
  font-weight: 500;
  color: #d5e3f7;
}
.uploader-hint {
  font-size: 12px;
  color: #6b84aa;
}
.uploader-hint b {
  color: #6b9cff;
  font-weight: 600;
}

/* 网格预览 */
.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.file-card {
  border: 1px solid rgba(120, 170, 255, 0.2);
  border-radius: 10px;
  padding: 8px;
  background: rgba(15, 24, 42, 0.4);
  display: flex;
  flex-direction: column;
  align-items: stretch;
}
.file-preview-img {
  width: 100%;
  height: 110px;
  object-fit: cover;
  border-radius: 6px;
  cursor: zoom-in;
}
.file-meta {
  margin-top: 6px;
  font-size: 12px;
  text-align: center;
  color: #a0b4d6;
}
.file-name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #d5e3f7;
}
.file-size {
  color: #6b84aa;
}
.file-source {
  color: #6b9cff;
  font-size: 11px;
}
.del-btn {
  margin-top: 6px;
}

/* 添加区外层 */
.add-area {
  background: rgba(15, 24, 42, 0.35);
  border: 1px solid rgba(120, 170, 255, 0.15);
  border-radius: 12px;
  padding: 14px;
}

/* 统一上传区域 */
.upload-zone {
  width: 100%;
  min-height: 140px;
  border: 2px dashed rgba(120, 170, 255, 0.35);
  border-radius: 10px;
  padding: 20px 20px 14px;
  text-align: center;
  background: rgba(10, 18, 34, 0.4);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #6b9cff;
  background: rgba(90, 134, 255, 0.1);
}
/* 粘贴高亮反馈 */
.upload-zone.paste-active {
  border-color: #2ee58c;
  background: rgba(46, 229, 140, 0.12);
  box-shadow: 0 0 0 3px rgba(46, 229, 140, 0.15);
}
.upload-icon {
  color: #6b9cff;
  margin-bottom: 8px;
}
.upload-hint {
  color: #d5e3f7;
  font-weight: 500;
  font-size: 14px;
  margin-bottom: 4px;
}
.upload-desc {
  color: #6b84aa;
  font-size: 12px;
}
.paste-hint {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(107, 156, 255, 0.1);
  border: 1px solid rgba(107, 156, 255, 0.25);
  border-radius: 12px;
  color: #8bb0ff;
  font-size: 12px;
}
.paste-hint .el-icon {
  font-size: 13px;
}

/* 隐藏的 file input */
.hidden-input {
  display: none;
}

/* 已达上限提示 */
.limit-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #ffb86b;
  text-align: center;
  padding: 10px;
  background: rgba(255, 184, 107, 0.08);
  border-radius: 8px;
  border: 1px dashed rgba(255, 184, 107, 0.3);
}
</style>

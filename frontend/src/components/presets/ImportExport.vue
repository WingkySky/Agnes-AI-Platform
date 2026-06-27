<!-- =====================================================
     ImportExport 组件
     - 导出按钮 → 触发下载 JSON
     - 导入按钮 → 文件上传 → 调用 API
     ===================================================== -->

<template>
  <div class="import-export">
    <el-button size="small" :loading="exporting" @click="handleExport">
      <el-icon><Download /></el-icon>
      {{ t('presets.export') }}
    </el-button>
    <el-button size="small" :loading="importing" @click="handleImportClick">
      <el-icon><Upload /></el-icon>
      {{ t('presets.import') }}
    </el-button>

    <!-- 隐藏文件输入 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".json"
      style="display: none"
      @change="onFileSelect" />

    <!-- 导入结果弹窗 -->
    <el-dialog
      v-model="resultVisible"
      :title="t('presets.importResult')"
      width="420px"
      destroy-on-close>
      <div class="import-result">
        <div class="result-stat">
          <el-tag type="success" size="small">{{ importResult.imported }} {{ t('presets.imported') }}</el-tag>
          <el-tag v-if="importResult.renamed > 0" type="warning" size="small">
            {{ importResult.renamed }} {{ t('presets.renamed') }}
          </el-tag>
          <el-tag v-if="importResult.skipped > 0" type="danger" size="small">
            {{ importResult.skipped }} {{ t('presets.skipped') }}
          </el-tag>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import client from '@/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  presetType?: string
}>(), {
  presetType: '',
})

const exporting = ref(false)
const importing = ref(false)
const resultVisible = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const importResult = reactive({
  imported: 0,
  renamed: 0,
  skipped: 0,
})

/* ---- 导出 ---- */
async function handleExport() {
  exporting.value = true
  try {
    const params: any = {}
    if (props.presetType) params.type = props.presetType

    const res = await client.get('/api/presets/export', { params })

    const jsonStr = JSON.stringify(res.data, null, 2)
    const blob = new Blob([jsonStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = url
    link.download = `agnes-presets-${Date.now()}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    ElMessage.success(t('presets.exportSuccess'))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.exportFailed'))
  } finally {
    exporting.value = false
  }
}

/* ---- 导入 ---- */
function handleImportClick() {
  fileInputRef.value?.click()
}

async function onFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  // 重置 input 以便重复选择同一文件
  target.value = ''

  // 校验文件类型
  if (!file.name.endsWith('.json')) {
    ElMessage.warning(t('presets.invalidJsonFile'))
    return
  }

  importing.value = true
  try {
    const text = await file.text()
    let payload: any[]
    try {
      payload = JSON.parse(text)
    } catch {
      ElMessage.error(t('presets.invalidJson'))
      return
    }

    if (!Array.isArray(payload)) {
      ElMessage.error(t('presets.invalidJsonArray'))
      return
    }

    const res = await client.post('/api/presets/import', payload)

    importResult.imported = res.data.imported || 0
    importResult.renamed = res.data.renamed || 0
    importResult.skipped = res.data.skipped || 0
    resultVisible.value = true

    if (res.data.imported > 0) {
      ElMessage.success(`${t('presets.imported')} ${res.data.imported}`)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.importFailed'))
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.import-export {
  display: inline-flex;
  gap: 8px;
}

.import-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-stat {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>

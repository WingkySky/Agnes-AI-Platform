<!-- =====================================================
     PresetCenter — 预设中心（管理视图）
     - 上半区：统一预设广场画廊（浏览广场/收藏/最近使用）
     - 管理区：我的预设列表（编辑/删除/投稿）+ 新建 + 导入导出
     ===================================================== -->

<template>
  <div class="preset-center">
    <!-- ====== 页面头部 ====== -->
    <header class="page-head">
      <div>
        <h2>{{ t('presets.center.title') }}</h2>
        <p class="muted">{{ t('presets.center.desc') }}</p>
      </div>
      <div class="head-actions">
        <ImportExport @imported="fetchMine" />
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">
          {{ t('presets.center.createBtn') }}
        </el-button>
      </div>
    </header>

    <!-- ====== 统一预设广场 ====== -->
    <PresetGallery context="admin" :show-apply="false" />

    <!-- ====== 我的预设 ====== -->
    <section class="mine-section">
      <h3 class="section-title">{{ t('presets.center.mineTitle') }}</h3>
      <el-table :data="minePresets" v-loading="mineLoading" size="small">
        <el-table-column prop="name" :label="t('presets.name')" min-width="160" show-overflow-tooltip />
        <el-table-column :label="t('presets.type')" width="90">
          <template #default="{ row }">{{ typeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column prop="category" :label="t('presets.category')" width="100" />
        <el-table-column prop="usage_count" :label="t('presets.plaza.uses')" width="80" />
        <el-table-column :label="t('presets.center.statusLabel')" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusOf(row).tagType">{{ statusOf(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('presets.center.actionsLabel')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openEditDialog(row)">{{ t('presets.center.edit') }}</el-button>
            <el-button
              v-if="!row.is_public"
              link
              size="small"
              type="warning"
              @click="handleSubmitReview(row)"
            >
              {{ t('presets.center.submitReview') }}
            </el-button>
            <el-button link size="small" type="danger" @click="handleDelete(row)">
              {{ t('presets.center.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ====== 编辑弹窗 ====== -->
    <PresetEditorDialog
      v-model="editorVisible"
      :preset="editingPreset"
      @submit="handleEditorSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import PresetGallery from '@/components/presets/PresetGallery.vue'
import PresetEditorDialog from '@/components/presets/PresetEditorDialog.vue'
import ImportExport from '@/components/presets/ImportExport.vue'
import { getPresets, submitPreset } from '@/api/presets'
import { usePresetStore } from '@/stores/presets'
import type { PromptPreset, PresetCreate } from '@/types/preset'

const { t } = useI18n()
const store = usePresetStore()

/* ====== 我的预设列表（独立请求，与画廊 store 互不干扰） ====== */
const minePresets = ref<PromptPreset[]>([])
const mineLoading = ref(false)

async function fetchMine() {
  mineLoading.value = true
  try {
    const result = await getPresets({ tab: 'mine', page_size: 100 })
    minePresets.value = result.items
  } catch {
    minePresets.value = []
  } finally {
    mineLoading.value = false
  }
}

function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.plaza.typeCamera',
    prompt: 'presets.plaza.typePrompt',
    style: 'presets.plaza.typeStyle',
    effect: 'presets.plaza.typeEffect',
    script: 'presets.plaza.typeScript',
    pipeline: 'presets.editor.typePipeline',
  }
  return keyMap[type] ? t(keyMap[type]) : type
}

function statusOf(row: PromptPreset): { label: string; tagType: 'success' | 'warning' | 'info' } {
  if (row.is_public && row.is_approved) return { label: t('presets.center.statusPublic'), tagType: 'success' }
  if (row.is_public) return { label: t('presets.center.statusPending'), tagType: 'warning' }
  return { label: t('presets.center.statusPrivate'), tagType: 'info' }
}

/* ====== 编辑 / 新建 ====== */
const editorVisible = ref(false)
const editingPreset = ref<PromptPreset | null>(null)

function openCreateDialog() {
  editingPreset.value = null
  editorVisible.value = true
}

function openEditDialog(preset: PromptPreset) {
  editingPreset.value = preset
  editorVisible.value = true
}

async function handleEditorSubmit(data: PresetCreate) {
  try {
    if (editingPreset.value) {
      await store.updatePreset(editingPreset.value.id, data)
      ElMessage.success(t('presets.center.updateSuccess'))
    } else {
      await store.createPreset(data)
      ElMessage.success(t('presets.center.createSuccess'))
    }
    await fetchMine()
  } catch {
    /* 错误已由拦截器提示 */
  }
}

/* ====== 投稿 / 删除 ====== */

async function handleSubmitReview(preset: PromptPreset) {
  try {
    await ElMessageBox.confirm(t('presets.center.submitConfirmMsg'), t('common.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await submitPreset(preset.id)
    ElMessage.success(t('presets.center.submitSuccess'))
    await fetchMine()
  } catch {
    /* 错误已由拦截器提示 */
  }
}

async function handleDelete(preset: PromptPreset) {
  try {
    await ElMessageBox.confirm(
      t('presets.center.deleteConfirmMsg').replace('{name}', preset.name),
      t('presets.center.deleteConfirmTitle'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await store.deletePreset(preset.id)
    ElMessage.success(t('presets.center.deleteSuccess'))
    await fetchMine()
  } catch {
    /* 错误已由拦截器提示 */
  }
}

onMounted(fetchMine)
</script>

<style scoped>
.preset-center {
  padding: 16px 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-head h2 {
  margin: 0 0 4px;
  font-size: 20px;
}

.muted {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mine-section {
  margin-top: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 12px;
}
</style>

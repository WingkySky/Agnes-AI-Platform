<!-- =====================================================
     敏感词管理页
     - 管理内容审核的敏感词库
     - 支持增删改查、按分类筛选
     ===================================================== -->

<template>
  <div class="sensitive-words-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.sensitiveWords.title') }}</h2>
        <p class="muted">{{ t('admin.sensitiveWords.desc') }}</p>
      </div>
      <div class="head-actions">
        <el-button :icon="Upload" @click="openImportDialog">{{ t('admin.sensitiveWords.importWords') }}</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">{{ t('admin.sensitiveWords.addWord') }}</el-button>
      </div>
    </header>

    <el-card class="filter-card" shadow="never">
      <div class="filter-row">
        <el-select v-model="filterCategory" :placeholder="t('admin.sensitiveWords.filterCategory')" style="width: 160px" @change="onFilterChange">
          <el-option :label="t('common.all')" value="" />
          <el-option
            v-for="(name, key) in categories"
            :key="key"
            :label="name"
            :value="key"
          />
        </el-select>

        <el-select v-model="filterStatus" :placeholder="t('admin.sensitiveWords.filterStatus')" style="width: 140px" @change="onFilterChange">
          <el-option :label="t('common.all')" value="" />
          <el-option :label="t('admin.sensitiveWords.statusActive')" value="active" />
          <el-option :label="t('admin.sensitiveWords.statusInactive')" value="inactive" />
        </el-select>

        <el-input
          v-model="keyword"
          :placeholder="t('admin.sensitiveWords.searchKeyword')"
          style="width: 260px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="onSearch">{{ t('common.search') }}</el-button>
        <el-button :icon="Refresh" @click="fetchList" :loading="loading">{{ t('common.refresh') }}</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="word" :label="t('admin.sensitiveWords.word')" min-width="160">
          <template #default="{ row }">
            <span class="word-text">{{ row.word }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" :label="t('admin.sensitiveWords.category')" width="140" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" :label="t('admin.sensitiveWords.description')" min-width="200">
          <template #default="{ row }">
            <span v-if="row.description" class="desc-text">{{ row.description }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.sensitiveWords.status')" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="(val: boolean) => onToggleActive(row, val)"
              :active-text="t('admin.sensitiveWords.statusActive')"
              :inactive-text="t('admin.sensitiveWords.statusInactive')"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="t('admin.sensitiveWords.createTime')" width="170" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.sensitiveWords.actions')" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="openEditDialog(row)">{{ t('admin.sensitiveWords.edit') }}</el-button>
            <el-button type="danger" size="small" link @click="onDelete(row)">{{ t('admin.sensitiveWords.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? t('admin.sensitiveWords.dialogEdit') : t('admin.sensitiveWords.dialogAdd')"
      width="480px"
      @close="resetForm"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="80px">
        <el-form-item :label="t('admin.sensitiveWords.word')" prop="word">
          <el-input v-model="form.word" :placeholder="t('admin.sensitiveWords.inputWord')" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('admin.sensitiveWords.category')" prop="category">
          <el-select
            v-model="form.category"
            :placeholder="t('admin.sensitiveWords.inputCategory')"
            filterable
            allow-create
            default-first-option
            style="width: 100%"
          >
            <el-option
              v-for="(name, key) in categories"
              :key="key"
              :label="name"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('admin.sensitiveWords.description')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :placeholder="t('admin.sensitiveWords.inputDesc')"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item :label="t('admin.sensitiveWords.status')" prop="is_active">
          <el-switch v-model="form.is_active" :active-text="t('admin.sensitiveWords.statusActive')" :inactive-text="t('admin.sensitiveWords.statusInactive')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onSubmit">
          {{ isEdit ? t('common.save') : t('admin.sensitiveWords.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog
      v-model="importDialogVisible"
      :title="t('admin.sensitiveWords.importTitle')"
      width="560px"
      @close="resetImportForm"
    >
      <el-form :model="importForm" label-width="100px" label-position="right">
        <el-form-item :label="t('admin.sensitiveWords.wordList')">
          <el-input
            v-model="importForm.words"
            type="textarea"
            :rows="10"
            :placeholder="t('admin.sensitiveWords.importInputHint')"
            maxlength="5000"
            show-word-limit
          />
          <div class="form-tip">{{ t('admin.sensitiveWords.importFormatTip') }}</div>
        </el-form-item>
        <el-form-item :label="t('admin.sensitiveWords.importCategory')">
          <el-select v-model="importForm.category" style="width: 200px">
            <el-option
              v-for="(name, key) in categories"
              :key="key"
              :label="name"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('admin.sensitiveWords.skipExisting')">
          <el-switch
            v-model="importForm.skip_existing"
            :active-text="t('common.yes')"
            :inactive-text="t('common.no')"
          />
          <div class="form-tip">{{ t('admin.sensitiveWords.skipExistingTip') }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="importLoading" @click="onImportSubmit">
          {{ t('admin.sensitiveWords.startImport') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Search, Refresh, Upload } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import {
  getSensitiveWords,
  createSensitiveWord,
  updateSensitiveWord,
  deleteSensitiveWord,
  batchImportSensitiveWords
} from '@/api/admin'
import type { SensitiveWordItem } from '@/api/admin'

const { t } = useI18n()

const loading = ref(false)
const list = ref<SensitiveWordItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filterCategory = ref<string>('')
const filterStatus = ref<string>('')
const keyword = ref('')

const categories = ref<Record<string, string>>({})

const dialogVisible = ref(false)
const isEdit = ref(false)
const submitLoading = ref(false)
const editingId = ref<number | null>(null)

const formRef = ref<FormInstance>()
const form = ref({
  word: '',
  category: '',
  description: '',
  is_active: true
})

const formRules = computed<FormRules>(() => ({
  word: [
    { required: true, message: t('admin.sensitiveWords.inputWordRequired'), trigger: 'blur' },
    { min: 1, max: 100, message: t('admin.sensitiveWords.inputWordLength'), trigger: 'blur' }
  ],
  category: [
    { required: true, message: t('admin.sensitiveWords.inputCategoryRequired'), trigger: 'change' }
  ]
}))

function formatTime(val?: string | null) {
  if (!val) return ''
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

async function fetchList() {
  loading.value = true
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filterCategory.value) params.category = filterCategory.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (filterStatus.value === 'active') params.is_active = true
    if (filterStatus.value === 'inactive') params.is_active = false

    const resp = await getSensitiveWords(params)
    list.value = resp.items || []
    total.value = resp.total || 0
    if (resp.categories) {
      categories.value = resp.categories
    }
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  fetchList()
}

function onSearch() {
  page.value = 1
  fetchList()
}

async function onToggleActive(row: SensitiveWordItem, active: boolean) {
  try {
    await updateSensitiveWord(row.id, { is_active: active })
    row.is_active = active
    ElMessage.success(active ? t('admin.sensitiveWords.enabled') : t('admin.sensitiveWords.disabled'))
  } catch (e) {
    console.warn(e)
    fetchList()
  }
}

function openCreateDialog() {
  isEdit.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row: SensitiveWordItem) {
  isEdit.value = true
  editingId.value = row.id
  form.value = {
    word: row.word,
    category: row.category,
    description: row.description || '',
    is_active: row.is_active
  }
  dialogVisible.value = true
}

function resetForm() {
  form.value = {
    word: '',
    category: '',
    description: '',
    is_active: true
  }
  formRef.value?.clearValidate()
}

async function onSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitLoading.value = true
  try {
    if (isEdit.value && editingId.value !== null) {
      await updateSensitiveWord(editingId.value, {
        word: form.value.word,
        category: form.value.category,
        description: form.value.description || undefined,
        is_active: form.value.is_active
      })
      ElMessage.success(t('admin.sensitiveWords.updateSuccess'))
    } else {
      await createSensitiveWord(
        form.value.word,
        form.value.category,
        form.value.description || undefined
      )
      ElMessage.success(t('admin.sensitiveWords.createSuccess'))
    }
    dialogVisible.value = false
    fetchList()
  } catch (e) {
    console.warn(e)
  } finally {
    submitLoading.value = false
  }
}

async function onDelete(row: SensitiveWordItem) {
  try {
    await ElMessageBox.confirm(
      t('admin.sensitiveWords.deleteConfirmMessage', { word: row.word }),
      t('admin.sensitiveWords.deleteConfirmTitle'),
      { confirmButtonText: t('admin.sensitiveWords.confirmDelete'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteSensitiveWord(row.id)
    ElMessage.success(t('admin.sensitiveWords.deleteSuccess'))
    fetchList()
  } catch (e) {
    console.warn(e)
  }
}

// ---------- 批量导入 ----------

const importDialogVisible = ref(false)
const importLoading = ref(false)
const importForm = ref({
  words: '',
  category: 'other',
  skip_existing: true
})

function openImportDialog() {
  importForm.value = {
    words: '',
    category: 'other',
    skip_existing: true
  }
  importDialogVisible.value = true
}

function resetImportForm() {
  importForm.value = {
    words: '',
    category: 'other',
    skip_existing: true
  }
}

async function onImportSubmit() {
  if (!importForm.value.words.trim()) {
    ElMessage.warning(t('admin.sensitiveWords.importEmptyWarning'))
    return
  }
  importLoading.value = true
  try {
    const resp = await batchImportSensitiveWords(importForm.value)
    ElMessage.success(
      t('admin.sensitiveWords.importResult', { inserted: resp.inserted_count, skipped: resp.skipped_count })
    )
    importDialogVisible.value = false
    fetchList()
  } catch (e) {
    console.warn(e)
  } finally {
    importLoading.value = false
  }
}

onMounted(fetchList)
</script>

<style scoped>
.sensitive-words-wrap {
  max-width: 1600px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
}

.head-actions {
  display: flex;
  gap: 8px;
}

.page-head h2 {
  margin: 0 0 4px;
  color: var(--agnes-text-primary);
  font-size: 20px;
}

.muted {
  color: var(--agnes-text-muted);
  font-size: 13px;
  margin: 0;
}

.filter-card,
.table-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
}

.filter-card {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

:deep(.el-table) {
  background: transparent;
  color: var(--agnes-text-secondary);
}

:deep(.el-table th.el-table__cell) {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-secondary);
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: var(--agnes-bg-hover);
}

.word-text {
  color: var(--agnes-text-primary);
  font-weight: 500;
}

.desc-text {
  color: var(--agnes-text-secondary);
  font-size: 13px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}

.form-tip {
  color: var(--agnes-text-muted);
  font-size: 12px;
  margin-top: 6px;
}
</style>

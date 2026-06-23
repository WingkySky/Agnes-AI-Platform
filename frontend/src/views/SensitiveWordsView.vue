<!-- =====================================================
     敏感词管理页
     - 管理内容审核的敏感词库
     - 支持增删改查、按分类筛选
     ===================================================== -->

<template>
  <div class="sensitive-words-wrap">
    <header class="page-head">
      <div>
        <h2>敏感词管理</h2>
        <p class="muted">管理内容审核敏感词库</p>
      </div>
      <div class="head-actions">
        <el-button :icon="Upload" @click="openImportDialog">批量导入</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增敏感词</el-button>
      </div>
    </header>

    <el-card class="filter-card" shadow="never">
      <div class="filter-row">
        <el-select v-model="filterCategory" placeholder="全部分类" style="width: 160px" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option
            v-for="(name, key) in categories"
            :key="key"
            :label="name"
            :value="key"
          />
        </el-select>

        <el-select v-model="filterStatus" placeholder="全部状态" style="width: 140px" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="启用" value="active" />
          <el-option label="停用" value="inactive" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="搜索关键词"
          style="width: 260px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="onSearch">搜索</el-button>
        <el-button :icon="Refresh" @click="fetchList" :loading="loading">刷新</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="word" label="关键词" min-width="160">
          <template #default="{ row }">
            <span class="word-text">{{ row.word }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="140" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="200">
          <template #default="{ row }">
            <span v-if="row.description" class="desc-text">{{ row.description }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="(val: boolean) => onToggleActive(row, val)"
              active-text="启用"
              inactive-text="停用"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" size="small" link @click="onDelete(row)">删除</el-button>
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
      :title="isEdit ? '编辑敏感词' : '新增敏感词'"
      width="480px"
      @close="resetForm"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="80px">
        <el-form-item label="关键词" prop="word">
          <el-input v-model="form.word" placeholder="请输入敏感词" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select
            v-model="form.category"
            placeholder="请选择或输入分类"
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
        <el-form-item label="说明" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入说明（可选）"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="启用状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog
      v-model="importDialogVisible"
      title="批量导入敏感词"
      width="560px"
      @close="resetImportForm"
    >
      <el-form :model="importForm" label-width="100px" label-position="right">
        <el-form-item label="敏感词列表">
          <el-input
            v-model="importForm.words"
            type="textarea"
            :rows="10"
            placeholder="请输入敏感词，支持换行、逗号、分号、空格分隔&#10;例如：&#10;敏感词1&#10;敏感词2,敏感词3；敏感词4"
            maxlength="5000"
            show-word-limit
          />
          <div class="form-tip">支持换行、逗号、分号、顿号、空格分隔，自动去重和跳过已存在的词</div>
        </el-form-item>
        <el-form-item label="默认分类">
          <el-select v-model="importForm.category" style="width: 200px">
            <el-option
              v-for="(name, key) in categories"
              :key="key"
              :label="name"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="跳过已存在">
          <el-switch
            v-model="importForm.skip_existing"
            active-text="是"
            inactive-text="否"
          />
          <div class="form-tip">关闭后会覆盖已存在词的分类（暂未实现，建议保持开启）</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="onImportSubmit">
          开始导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Search, Refresh, Upload } from '@element-plus/icons-vue'
import {
  getSensitiveWords,
  createSensitiveWord,
  updateSensitiveWord,
  deleteSensitiveWord,
  batchImportSensitiveWords
} from '@/api/admin'
import type { SensitiveWordItem } from '@/api/admin'

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

const formRules: FormRules = {
  word: [
    { required: true, message: '请输入关键词', trigger: 'blur' },
    { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' }
  ],
  category: [
    { required: true, message: '请选择或输入分类', trigger: 'change' }
  ]
}

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
    ElMessage.success(active ? '已启用' : '已停用')
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
      ElMessage.success('修改成功')
    } else {
      await createSensitiveWord(
        form.value.word,
        form.value.category,
        form.value.description || undefined
      )
      ElMessage.success('创建成功')
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
      `确认删除敏感词「${row.word}」？`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteSensitiveWord(row.id)
    ElMessage.success('已删除')
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
    ElMessage.warning('请输入要导入的敏感词')
    return
  }
  importLoading.value = true
  try {
    const resp = await batchImportSensitiveWords(importForm.value)
    ElMessage.success(
      `导入完成：新增 ${resp.inserted_count} 条，跳过 ${resp.skipped_count} 条`
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

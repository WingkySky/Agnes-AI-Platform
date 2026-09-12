<!-- =====================================================
     剧本 Tab ScriptTab
     - 展示剧本列表（卡片网格）
     - 单个剧本：查看全文 / 编辑 / 重新生成 / 删除
     - 顶部：新建剧本（手动）/ 从已有剧本拆分分镜
     - 状态徽标：draft / ready
     ===================================================== -->

<template>
  <div class="script-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Plus" @click="onCreate">新建剧本</el-button>
        <el-button
          v-if="selectedScript"
          :icon="MagicStick"
          :loading="splitting"
          @click="onSplitShots"
        >
          按此剧本拆分分镜
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-button :icon="Refresh" link @click="onRefresh">刷新</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && scripts.length === 0" class="empty-state">
      <el-icon :size="48"><Document /></el-icon>
      <p class="empty-text">还没有剧本，点击「新建剧本」开始创作</p>
    </div>

    <!-- 剧本卡片网格 -->
    <div v-else class="script-grid">
      <div
        v-for="script in scripts"
        :key="script.id"
        class="script-card"
        :class="{ selected: selectedScriptId === script.id }"
        @click="selectScript(script)"
      >
        <div class="card-header">
          <div class="card-title">
            <span v-if="script.title">{{ script.title }}</span>
            <span v-else class="title-empty">第 {{ script.episode_no }} 集</span>
          </div>
          <el-tag size="small" :type="script.status === 'ready' ? 'success' : 'info'">
            {{ script.status === 'ready' ? '已就绪' : '草稿' }}
          </el-tag>
        </div>
        <div class="card-content">{{ script.content }}</div>
        <div class="card-meta">
          <span>第 {{ script.episode_no }} 集</span>
          <span>{{ formatDate(script.updated_at) }}</span>
        </div>
        <div class="card-actions" @click.stop>
          <el-button link :icon="View" @click="onView(script)">查看</el-button>
          <el-button link :icon="Edit" @click="onEdit(script)">编辑</el-button>
          <el-dropdown trigger="click" @command="(cmd: string) => onMoreCommand(cmd, script)">
            <el-button link :icon="MoreFilled" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="regenerate" :icon="Refresh">重新生成</el-dropdown-item>
                <el-dropdown-item command="delete" :icon="Delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <!-- 查看对话框 -->
    <el-dialog v-model="viewVisible" :title="viewingScript?.title || '剧本详情'" width="720px">
      <div v-if="viewingScript" class="view-content">
        <pre>{{ viewingScript.content }}</pre>
      </div>
    </el-dialog>

    <!-- 编辑/新建对话框 -->
    <el-dialog
      v-model="editVisible"
      :title="editingScript ? '编辑剧本' : '新建剧本'"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form :model="editForm" label-position="top">
        <el-form-item label="集数">
          <el-input-number v-model="editForm.episode_no" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="标题（可选）">
          <el-input v-model="editForm.title" placeholder="剧本标题" maxlength="100" />
        </el-form-item>
        <el-form-item label="剧本内容">
          <el-input
            v-model="editForm.content"
            type="textarea"
            :rows="12"
            placeholder="输入或粘贴剧本正文"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Refresh, MagicStick, Document, View, Edit, Delete, MoreFilled,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { ProjectScript, ScriptCreateRequest, ScriptUpdateRequest } from '@/types/project'

const projectStore = useProjectStore()

// ---------- 数据 ----------
const loading = ref(false)
const scripts = computed(() => projectStore.scripts)

// ---------- 选中状态 ----------
const selectedScriptId = ref<number | null>(null)
const selectedScript = computed(() => scripts.value.find(s => s.id === selectedScriptId.value) || null)

function selectScript(script: ProjectScript) {
  selectedScriptId.value = selectedScriptId.value === script.id ? null : script.id
}

// ---------- 查看 ----------
const viewVisible = ref(false)
const viewingScript = ref<ProjectScript | null>(null)
function onView(script: ProjectScript) {
  viewingScript.value = script
  viewVisible.value = true
}

// ---------- 新建/编辑 ----------
const editVisible = ref(false)
const editingScript = ref<ProjectScript | null>(null)
const saving = ref(false)
const editForm = ref<{ episode_no: number; title: string; content: string }>({
  episode_no: 1,
  title: '',
  content: '',
})

function onCreate() {
  editingScript.value = null
  editForm.value = {
    episode_no: (scripts.value.length || 0) + 1,
    title: '',
    content: '',
  }
  editVisible.value = true
}

function onEdit(script: ProjectScript) {
  editingScript.value = script
  editForm.value = {
    episode_no: script.episode_no,
    title: script.title || '',
    content: script.content,
  }
  editVisible.value = true
}

async function onSave() {
  if (!editForm.value.content.trim()) {
    ElMessage.warning('剧本内容不能为空')
    return
  }
  saving.value = true
  try {
    if (editingScript.value) {
      const data: ScriptUpdateRequest = {
        title: editForm.value.title || undefined,
        content: editForm.value.content,
      }
      await projectStore.updateScript(editingScript.value.id, data)
      ElMessage.success('剧本已更新')
    } else {
      const data: ScriptCreateRequest = {
        episode_no: editForm.value.episode_no,
        title: editForm.value.title || undefined,
        content: editForm.value.content,
      }
      await projectStore.createScript(data)
      ElMessage.success('剧本已创建')
    }
    editVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------- 重新生成（前端管线 generateScript，参数取项目 wizard_inputs） ----------
const regenerating = ref(false)
async function onRegenerate(script: ProjectScript) {
  try {
    await ElMessageBox.confirm(
      `将按项目模板参数重新生成「${script.title || '第 ' + script.episode_no + ' 集'}」的内容并覆盖，是否继续？`,
      '重新生成剧本',
      { type: 'info', confirmButtonText: '开始生成', cancelButtonText: '取消' },
    )
  } catch (_) { return }
  regenerating.value = true
  try {
    await projectStore.regenerateScript(script.id)
    ElMessage.success('剧本已重新生成')
  } catch (e: any) {
    ElMessage.error(e?.message || '重新生成失败')
  } finally {
    regenerating.value = false
  }
}

// ---------- 拆分分镜 ----------
const splitting = ref(false)
async function onSplitShots() {
  if (!selectedScript.value) return
  try {
    await ElMessageBox.confirm(
      `将根据「${selectedScript.value.title || '第 ' + selectedScript.value.episode_no + ' 集'}」的内容拆分为多个分镜，是否继续？`,
      '拆分分镜',
      { type: 'info', confirmButtonText: '开始拆分', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  splitting.value = true
  try {
    const result = await projectStore.splitShotsFromScript(selectedScript.value.id)
    ElMessage.success(`已拆分出 ${result.shot_count} 个分镜`)
  } catch (e: any) {
    ElMessage.error(e?.message || '拆分失败')
  } finally {
    splitting.value = false
  }
}

// ---------- 下拉菜单 ----------
async function onMoreCommand(cmd: string, script: ProjectScript) {
  if (cmd === 'regenerate') {
    await onRegenerate(script)
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `确定要删除「${script.title || '第 ' + script.episode_no + ' 集'}」吗？`,
        '删除确认',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
      )
      await projectStore.deleteScript(script.id)
      if (selectedScriptId.value === script.id) selectedScriptId.value = null
      ElMessage.success('剧本已删除')
    } catch (_) { /* 取消 */ }
  }
}

// ---------- 工具函数 ----------
function onRefresh() {
  loading.value = true
  projectStore.fetchScripts().finally(() => {
    loading.value = false
  })
}

function formatDate(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  if (scripts.value.length === 0) {
    onRefresh()
  }
})
</script>

<style scoped>
.script-tab { padding: 4px 0; }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.toolbar-left { display: flex; gap: 8px; }

.empty-state {
  text-align: center; padding: 60px 0; color: var(--el-text-color-secondary);
}
.empty-text { margin-top: 12px; font-size: 13px; }

.script-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.script-card {
  background: var(--el-bg-color); border: 1px solid var(--el-border-color-light);
  border-radius: 8px; padding: 12px 16px; cursor: pointer; transition: all 0.2s;
  display: flex; flex-direction: column; gap: 8px;
}
.script-card:hover { border-color: var(--el-color-primary); }
.script-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}

.card-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.card-title {
  font-size: 14px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  flex: 1; min-width: 0;
}
.title-empty { color: var(--el-text-color-secondary); font-weight: 500; }

.card-content {
  font-size: 12px; color: var(--el-text-color-secondary);
  line-height: 1.5; height: 96px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical;
  white-space: pre-wrap;
}

.card-meta {
  display: flex; gap: 12px; font-size: 12px; color: var(--el-text-color-secondary);
}

.card-actions {
  display: flex; gap: 4px; justify-content: flex-end;
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 8px;
}

.view-content pre {
  white-space: pre-wrap; word-wrap: break-word;
  font-family: inherit; line-height: 1.6; font-size: 13px;
  margin: 0; padding: 0;
}
</style>

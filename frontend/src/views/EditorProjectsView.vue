<script setup lang="ts">
/* =====================================================
 * 剪辑工程列表页（/editor-projects，顶部菜单「视频剪辑」入口）
 * 新建 / 打开 / 删除；按作品挂靠展示
 * ===================================================== */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Delete, Edit, EditPen, Plus, VideoCamera } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createEditorProject, deleteEditorProject, listEditorProjects, updateEditorProject, type EditingProjectBrief } from '@/api/editor'
import { useRename } from '@/composables/useRename'
import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'

const router = useRouter()
const editorStore = useEditorStore()
const { t } = useI18n()
const { rename } = useRename()

const items = ref<EditingProjectBrief[]>([])
const loading = ref(false)
const creating = ref(false)

function renderTag(status: EditingProjectBrief['render_status']): 'warning' | 'success' | 'danger' | 'info' {
  if (status === 'rendering') return 'warning'
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

async function reload(): Promise<void> {
  loading.value = true
  try {
    items.value = (await listEditorProjects()).items
  } finally {
    loading.value = false
  }
}

async function create(): Promise<void> {
  const { value } = await ElMessageBox.prompt(t('editorProjects.newPrompt'), t('editorProjects.new'), {
    inputValue: t('editorProjects.defaultTitle'),
    inputPattern: /\S+/,
    inputErrorMessage: t('editorProjects.titleRequired'),
  })
  creating.value = true
  try {
    const detail = await createEditorProject({ title: value.trim() })
    editorStore.reset()
    await router.push(`/editor/${detail.uid}`)
  } finally {
    creating.value = false
  }
}

async function open(uid: string): Promise<void> {
  editorStore.reset()
  await router.push(`/editor/${uid}`)
}

async function remove(project: EditingProjectBrief): Promise<void> {
  await ElMessageBox.confirm(t('editorProjects.deleteConfirm', { title: project.title }), t('common.delete'), { type: 'warning' })
  await deleteEditorProject(project.uid)
  ElMessage.success(t('editorProjects.deleted'))
  await reload()
}

async function renameProject(project: EditingProjectBrief): Promise<void> {
  const name = await rename(project.title)
  if (!name) return
  await updateEditorProject(project.uid, { title: name })
  ElMessage.success(t('common.renameDone'))
  await reload()
}

onMounted(() => void reload())
</script>

<template>
  <div class="projects-page">
    <div class="page-head">
      <h2>{{ t('editorProjects.title') }}</h2>
      <el-button type="primary" :icon="Plus" :loading="creating" @click="create">{{ t('editorProjects.new') }}</el-button>
    </div>

    <div v-loading="loading" class="project-grid">
      <div v-for="project in items" :key="project.uid" class="project-card" @click="open(project.uid)">
        <div class="card-cover">
          <img v-if="project.cover_url" :src="project.cover_url" alt="" loading="lazy">
          <el-icon v-else :size="28"><VideoCamera /></el-icon>
          <el-tag v-if="project.final_url" type="success" size="small">{{ t('editorProjects.hasFinal') }}</el-tag>
        </div>
        <div class="card-body">
          <span class="card-title" :title="project.title">{{ project.title }}</span>
          <span class="card-meta">{{ project.updated_at?.slice(0, 16).replace('T', ' ') }}</span>
        </div>
        <div class="card-actions">
          <el-tag :type="renderTag(project.render_status)" size="small">{{ t(`editor.renderStates.${project.render_status}`) }}</el-tag>
          <el-button :icon="EditPen" text size="small" @click.stop="open(project.uid)" />
          <el-button :icon="Edit" text size="small" :title="t('common.rename')" @click.stop="renameProject(project)" />
          <el-button :icon="Delete" text size="small" type="danger" @click.stop="remove(project)" />
        </div>
      </div>
      <div v-if="!loading && !items.length" class="empty">
        <p>{{ t('editorProjects.empty') }}</p>
        <el-button type="primary" :icon="Plus" @click="create">{{ t('editorProjects.new') }}</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.projects-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-head h2 { margin: 0; }
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.project-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s;
}
.project-card:hover { box-shadow: var(--el-box-shadow-light); }
.card-cover {
  height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  overflow: hidden;
}
.card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.card-body {
  padding: 8px 12px 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.card-title { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px 10px;
}
.card-actions .el-tag { margin-right: auto; }
.empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 0;
  color: var(--el-text-color-secondary);
}
</style>

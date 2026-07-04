<!-- =====================================================
     项目列表页 ProjectListView
     - 展示当前用户的所有项目
     - 支持搜索、状态筛选、分页
     - 顶部"创建项目"按钮 → 弹出 ProjectLaunchDialog
     ===================================================== -->

<template>
  <div class="project-list-view">
    <!-- 头部 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">我的项目</h2>
        <p class="page-desc">从模板创建项目，引导式生成剧本/分镜/视频</p>
      </div>
      <div class="header-right">
        <el-button type="primary" :icon="Plus" @click="launchDialogVisible = true">
          创建项目
        </el-button>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索项目标题或描述"
        class="search-input"
        clearable
        @input="onSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select v-model="statusFilter" placeholder="状态" clearable @change="fetchList" style="width: 140px">
        <el-option label="草稿" value="draft" />
        <el-option label="创建中" value="creating" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="合成中" value="merging" />
        <el-option label="已完成" value="completed" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-button :icon="Refresh" @click="fetchList">刷新</el-button>
    </div>

    <!-- 项目网格 -->
    <div v-loading="projectStore.listLoading" class="project-grid-wrapper">
      <div v-if="!projectStore.listLoading && projectStore.projects.length === 0" class="empty-state">
        <el-icon :size="56"><FolderOpened /></el-icon>
        <p class="empty-text">还没有项目，点击右上角创建第一个吧</p>
      </div>
      <div v-else class="project-grid">
        <div
          v-for="project in projectStore.projects"
          :key="project.id"
          class="project-card"
          @click="openProject(project.id)"
        >
          <div class="card-cover">
            <img v-if="project.cover_url" :src="project.cover_url" :alt="project.title" />
            <div v-else class="cover-placeholder">
              <el-icon :size="40"><Film /></el-icon>
            </div>
            <el-tag class="card-status" :type="statusTagType(project.status)" size="small">
              {{ statusLabel(project.status) }}
            </el-tag>
          </div>
          <div class="card-body">
            <div class="card-title" :title="project.title">{{ project.title }}</div>
            <div class="card-desc">{{ project.description || '暂无描述' }}</div>
            <div class="card-meta">
              <span><el-icon><Clock /></el-icon> {{ formatDate(project.created_at) }}</span>
              <span><el-icon><Picture /></el-icon> {{ project.shots?.length || 0 }} 镜</span>
            </div>
          </div>
          <div class="card-actions" @click.stop>
            <el-dropdown trigger="click" @command="(cmd: string) => onCardAction(cmd, project)">
              <el-button link :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="open">打开</el-dropdown-item>
                  <el-dropdown-item command="archive" :disabled="project.status === 'archived'">归档</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="projectStore.listTotal > projectStore.listPageSize" class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="projectStore.listPageSize"
          :total="projectStore.listTotal"
          layout="prev, pager, next, total"
          @current-change="fetchList"
        />
      </div>
    </div>

    <!-- 创建项目对话框 -->
    <ProjectLaunchDialog v-model="launchDialogVisible" :initial-category="initialCategory" @created="onProjectCreated" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  Plus, Search, Refresh, Film, Clock, Picture, FolderOpened, MoreFilled,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import ProjectLaunchDialog from '@/components/project/ProjectLaunchDialog.vue'
import type { Project, ProjectStatus } from '@/types/project'

const router = useRouter()
const route = useRoute()
const projectStore = useProjectStore()

const launchDialogVisible = ref(false)
const initialCategory = ref<string>('')
const searchKeyword = ref('')
const statusFilter = ref<ProjectStatus | ''>('')
const currentPage = ref(1)

let searchTimer: number | null = null

onMounted(() => {
  fetchList()
  // 从 WorkshopView 跳转过来时带 category 参数，自动打开创建对话框
  const cat = route.query.category
  if (cat && typeof cat === 'string') {
    initialCategory.value = cat
    launchDialogVisible.value = true
  }
})

async function fetchList() {
  await projectStore.fetchList({
    search: searchKeyword.value || undefined,
    status: statusFilter.value || undefined,
    page: currentPage.value,
    page_size: 20,
  })
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    currentPage.value = 1
    fetchList()
  }, 300)
}

function openProject(id: number) {
  router.push(`/projects/${id}`)
}

function onProjectCreated(projectId: number) {
  router.push(`/projects/${projectId}`)
}

async function onCardAction(cmd: string, project: Project) {
  if (cmd === 'open') {
    openProject(project.id)
  } else if (cmd === 'archive') {
    await projectStore.archiveProject(project.id)
    await fetchList()
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `确定要删除项目「${project.title}」吗？此操作不可撤销。`,
        '删除确认',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
      )
      await projectStore.deleteProject(project.id)
      await fetchList()
    } catch (_) { /* 取消 */ }
  }
}

function statusLabel(status: ProjectStatus): string {
  const map: Record<ProjectStatus, string> = {
    draft: '草稿',
    creating: '创建中',
    in_progress: '进行中',
    merging: '合成中',
    completed: '已完成',
    archived: '已归档',
  }
  return map[status] || status
}

function statusTagType(status: ProjectStatus): 'primary' | 'success' | 'info' | 'warning' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'creating': return 'warning'
    case 'merging': return 'warning'
    case 'archived': return 'info'
    case 'draft': return 'info'
    case 'in_progress': return 'primary'
    default: return 'info'
  }
}

function formatDate(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
</script>

<style scoped>
.project-list-view { padding: 20px; max-width: 1400px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.page-desc { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.filter-bar { display: flex; gap: 12px; margin-bottom: 20px; }
.search-input { flex: 1; max-width: 320px; }
.project-grid-wrapper { min-height: 400px; }
.empty-state { text-align: center; padding: 60px 0; color: var(--el-text-color-secondary); }
.empty-text { margin-top: 12px; }
.project-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.project-card {
  background: var(--el-bg-color); border: 1px solid var(--el-border-color-light);
  border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.2s;
  position: relative;
}
.project-card:hover { border-color: var(--el-color-primary); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.card-cover { position: relative; aspect-ratio: 16 / 9; background: var(--el-fill-color); }
.card-cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--el-text-color-secondary); }
.card-status { position: absolute; top: 8px; right: 8px; }
.card-body { padding: 12px 14px; }
.card-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-desc { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; height: 36px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.card-meta { display: flex; gap: 12px; margin-top: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
.card-meta span { display: inline-flex; align-items: center; gap: 4px; }
.card-actions { position: absolute; bottom: 12px; right: 12px; }
.pagination-wrapper { margin-top: 24px; display: flex; justify-content: center; }
</style>

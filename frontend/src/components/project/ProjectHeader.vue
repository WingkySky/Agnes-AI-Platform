<!-- =====================================================
     项目头部工具栏 ProjectHeader
     - 显示标题 / 状态 / 元信息
     - 视图切换：管理视图 / 画布视图
     - 操作按钮：合成 / 归档 / 删除
     ===================================================== -->

<template>
  <div class="project-header">
    <div class="header-left">
      <el-button link :icon="ArrowLeft" @click="$router.push('/projects')">返回</el-button>
      <div class="header-title-block">
        <div class="title-row">
          <span class="title">{{ project?.title || '加载中...' }}</span>
          <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
        </div>
        <div class="meta-row">
          <span><el-icon><Calendar /></el-icon> 创建于 {{ formatDate(project?.created_at) }}</span>
          <span v-if="project?.aspect_ratio"><el-icon><FullScreen /></el-icon> {{ project.aspect_ratio }}</span>
          <span v-if="project?.resolution"><el-icon><Monitor /></el-icon> {{ project.resolution }}</span>
          <span v-if="project?.shots?.length"><el-icon><Picture /></el-icon> {{ project.shots.length }} 镜</span>
        </div>
      </div>
    </div>

    <div class="header-right">
      <!-- SSE 连接状态 -->
      <el-tooltip :content="sseTooltip" placement="bottom">
        <el-tag :type="sseConnected ? 'success' : 'info'" size="small" effect="plain">
          <el-icon><Connection /></el-icon>
          {{ sseConnected ? '实时' : '轮询' }}
        </el-tag>
      </el-tooltip>

      <!-- 视图切换 -->
      <el-radio-group
        :model-value="project?.active_view || 'manager'"
        size="small"
        @change="onViewChange"
      >
        <el-radio-button value="manager">
          <el-icon><Grid /></el-icon> 管理
        </el-radio-button>
        <el-radio-button value="canvas">
          <el-icon><Histogram /></el-icon> 画布
        </el-radio-button>
      </el-radio-group>

      <!-- 合成按钮 -->
      <el-button
        v-if="projectStore.isEditable"
        type="primary"
        :loading="projectStore.mergeLoading"
        :icon="VideoPlay"
        @click="onMerge"
      >
        合成视频
      </el-button>

      <!-- 已合成视频播放 -->
      <el-button
        v-if="project?.final_video_url"
        :icon="VideoPlay"
        @click="playFinalVideo"
      >
        播放成片
      </el-button>
    </div>

    <!-- 成片播放弹窗 -->
    <el-dialog
      v-model="finalVideoDialogVisible"
      title="项目成片预览"
      width="80%"
      align-center
      destroy-on-close
    >
      <video
        v-if="finalVideoUrl"
        :src="finalVideoUrl"
        controls
        autoplay
        style="width: 100%; max-height: 70vh; background: #000"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Calendar, FullScreen, Monitor, Picture, Connection,
  Grid, Histogram, VideoPlay,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useUserStore } from '@/stores/user'
import type { Project, ProjectActiveView, ProjectStatus } from '@/types/project'

const props = defineProps<{
  project: Project | null
  sseConnected: boolean
}>()

const projectStore = useProjectStore()
const userStore = useUserStore()

// 成片播放弹窗
const finalVideoDialogVisible = ref(false)
const finalVideoUrl = ref('')

function buildFinalVideoUrl(): string {
  if (!props.project?.final_video_url) return ''
  // final_video_url 是相对路径 /api/projects/{id}/final-video?v=ts
  // <video> 标签无法设置 Authorization header，需要拼 token query 参数
  const rel = props.project.final_video_url
  const token = userStore.token || ''
  const sep = rel.includes('?') ? '&' : '?'
  // 拼接 baseURL（开发环境走 vite 代理 /api，生产环境是同源）
  return `${rel}${sep}token=${encodeURIComponent(token)}`
}

function playFinalVideo() {
  if (!props.project?.final_video_url) return
  finalVideoUrl.value = buildFinalVideoUrl()
  finalVideoDialogVisible.value = true
}

const statusLabel = computed(() => {
  const map: Record<ProjectStatus, string> = {
    draft: '草稿', creating: '创建中', in_progress: '进行中',
    merging: '合成中', completed: '已完成', archived: '已归档',
  }
  return map[props.project?.status as ProjectStatus] || '未知'
})

const statusTagType = computed<'primary' | 'success' | 'info' | 'warning' | 'danger'>(() => {
  switch (props.project?.status) {
    case 'completed': return 'success'
    case 'creating': case 'merging': return 'warning'
    case 'archived': case 'draft': return 'info'
    case 'in_progress': return 'primary'
    default: return 'info'
  }
})

const sseTooltip = computed(() => props.sseConnected ? '已建立实时连接' : '使用轮询模式（每 10 秒）')

async function onViewChange(view: string | number | boolean | undefined) {
  if (!props.project) return
  await projectStore.updateActiveView(props.project.id, view as ProjectActiveView)
}

async function onMerge() {
  if (!props.project) return
  try {
    await ElMessageBox.confirm(
      '将按分镜顺序合成最终视频，可能需要几分钟。是否继续？',
      '合成确认',
      { type: 'info', confirmButtonText: '开始合成', cancelButtonText: '取消' },
    )
    await projectStore.mergeProject()
  } catch (_) { /* 取消 */ }
}

function formatDate(s?: string | null): string {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.project-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 20px; background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
}
.header-left { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
.header-title-block { min-width: 0; }
.title-row { display: flex; align-items: center; gap: 8px; }
.title { font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta-row {
  display: flex; gap: 16px; margin-top: 4px;
  color: var(--el-text-color-secondary); font-size: 12px;
}
.meta-row span { display: inline-flex; align-items: center; gap: 4px; }
.header-right { display: flex; align-items: center; gap: 12px; }
</style>

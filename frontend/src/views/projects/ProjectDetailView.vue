<!-- =====================================================
     项目详情页 ProjectDetailView
     - 加载项目详情并订阅 SSE
     - 头部：ProjectHeader（标题/状态/视图切换/合成按钮）
     - 主体：根据 activeView 切换 ProjectManagerView / ProjectCanvasView
     - 向导进行中（status=creating）时显示向导进度面板
     - SSE 事件触发局部刷新（实体列表/分镜/合成进度）
     ===================================================== -->

<template>
  <div v-loading="projectStore.currentLoading && !projectStore.currentProject" class="project-detail-view">
    <!-- 错误提示 -->
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="load-error"
    >
      <template #default>
        <el-button link type="primary" @click="$router.push('/projects')">返回列表</el-button>
      </template>
    </el-alert>

    <template v-else-if="project">
      <!-- 顶部工具栏 -->
      <ProjectHeader
        :project="project"
        :sse-connected="sse.connected.value"
        :merge-progress="sse.mergeProgress.value"
      />

      <!-- 向导进度面板：status=creating 时展示 -->
      <div v-if="project.status === 'creating'" class="wizard-panel">
        <div class="wizard-panel-header">
          <h3 class="wizard-title">
            <el-icon class="loading-icon" v-if="sse.currentWizardStep.value"><Loading /></el-icon>
            项目创建中
          </h3>
          <p class="wizard-desc">AI 正在按步骤生成项目内容，请稍候</p>
        </div>
        <div class="wizard-steps">
          <div
            v-for="step in wizardStepList"
            :key="step.key"
            class="wizard-step"
            :class="`step-${step.status}`"
          >
            <div class="step-icon">
              <el-icon v-if="step.status === 'completed'"><Check /></el-icon>
              <el-icon v-else-if="step.status === 'failed'"><Close /></el-icon>
              <el-icon v-else-if="step.status === 'running'" class="loading-icon"><Loading /></el-icon>
              <span v-else class="step-index">{{ step.index }}</span>
            </div>
            <div class="step-info">
              <div class="step-name">{{ step.name }}</div>
              <div v-if="step.error" class="step-error">{{ step.error }}</div>
            </div>
          </div>
        </div>
        <div v-if="sse.projectError.value" class="wizard-error">
          <el-alert :title="sse.projectError.value" type="error" show-icon />
          <el-button
            v-if="failedStep"
            type="primary"
            size="small"
            style="margin-top: 8px"
            :loading="resuming"
            @click="onResumeWizard"
          >
            从失败步骤恢复
          </el-button>
        </div>
      </div>

      <!-- 主体：根据视图切换 -->
      <div v-else class="project-body">
        <ProjectManagerView v-if="project.active_view === 'manager'" />
        <ProjectCanvasView v-else />
      </div>
    </template>

    <!-- 加载占位（首次加载中） -->
    <div v-else class="loading-placeholder">
      <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
      <p>正在加载项目...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, Check, Close } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useProjectSSE } from '@/composables/useProjectSSE'
import ProjectHeader from '@/components/project/ProjectHeader.vue'
import ProjectManagerView from '@/components/project/ProjectManagerView.vue'
import ProjectCanvasView from '@/components/project/ProjectCanvasView.vue'

const route = useRoute()
const projectStore = useProjectStore()

// ---------- 本地状态 ----------
const loadError = ref('')
const resuming = ref(false)

// 项目 ID（响应式，随路由变化）
const projectIdRef = computed(() => {
  const id = route.params.id
  return id ? Number(id) : null
})

// SSE 订阅
const sse = useProjectSSE(projectIdRef)

// 当前项目
const project = computed(() => projectStore.currentProject)

// ---------- 向导步骤展示 ----------
const WIZARD_STEP_NAMES: Record<string, string> = {
  script_generation: '生成剧本',
  entity_extraction: '提取角色/场景/道具',
  storyboard_split: '拆分分镜',
  frame_prompt_extract: '生成画面提示词',
}

const wizardStepList = computed(() => {
  const steps = sse.wizardSteps.value
  const keys = Object.keys(WIZARD_STEP_NAMES)
  return keys.map((key, idx) => ({
    key,
    index: idx + 1,
    name: WIZARD_STEP_NAMES[key] || steps[key]?.step_name || key,
    status: steps[key]?.status || 'pending',
    error: steps[key]?.error,
  }))
})

const failedStep = computed(() => wizardStepList.value.find(s => s.status === 'failed'))

// ---------- 加载项目详情 ----------
async function loadProject() {
  const id = projectIdRef.value
  if (!id) {
    loadError.value = '无效的项目 ID'
    return
  }
  loadError.value = ''
  try {
    await projectStore.fetchProject(id)
    if (!projectStore.currentProject) {
      loadError.value = '项目不存在或无权访问'
    }
  } catch (e: any) {
    loadError.value = e?.message || '加载项目失败'
  }
}

// ---------- 从失败步骤恢复向导 ----------
async function onResumeWizard() {
  if (!failedStep.value || !projectIdRef.value) return
  resuming.value = true
  try {
    await projectStore.resumeWizard(projectIdRef.value, { resume_from: failedStep.value.key })
    ElMessage.success('已恢复向导执行')
  } catch (e: any) {
    ElMessage.error(e?.message || '恢复失败')
  } finally {
    resuming.value = false
  }
}

// ---------- 监听 SSE 事件 → 局部刷新 ----------
// 当向导某步骤完成时刷新对应实体
watch(
  () => sse.wizardSteps.value,
  (steps) => {
    // 找到刚刚变为 completed 的步骤
    for (const [key, state] of Object.entries(steps)) {
      if (state.status === 'completed') {
        // 只在项目状态仍为 creating 时刷新（避免重复刷新）
        if (projectStore.currentProject?.status === 'creating') {
          projectStore.refreshAfterWizardStep(key).catch(() => {/* 忽略并发刷新错误 */})
        }
      }
    }
  },
  { deep: true },
)

// 项目状态变化时刷新详情
watch(
  () => sse.projectStatus.value,
  (newStatus) => {
    if (!newStatus) return
    // 状态从 creating → in_progress 时主动拉取一次详情
    if (projectStore.currentProject && projectStore.currentProject.status !== newStatus) {
      projectStore.updateStatusFromEvent(newStatus)
      // 重要状态变更时重新拉取详情，确保实体列表完整
      if (newStatus === 'in_progress' || newStatus === 'completed') {
        if (projectIdRef.value) {
          projectStore.fetchProject(projectIdRef.value).catch(() => {/* 忽略 */})
        }
      }
    }
  },
)

// 实体更新事件 → 刷新对应列表
watch(
  () => sse.lastEntityUpdate.value,
  (evt) => {
    if (!evt) return
    const entityType = evt.entity_type as string | undefined
    if (entityType && ['character', 'scene', 'prop'].includes(entityType)) {
      projectStore.fetchEntities(entityType as any).catch(() => {/* 忽略 */})
    } else if (evt.shot_id || evt.entity_type === 'shot') {
      // 分镜相关更新：刷新对应分镜
      const shotId = evt.shot_id as number | undefined
      if (shotId) projectStore.refreshShot(shotId).catch(() => {/* 忽略 */})
      else projectStore.fetchShots().catch(() => {/* 忽略 */})
    }
  },
)

// 合成完成事件 → 刷新详情
watch(
  () => sse.mergeProgress.value,
  (evt) => {
    if (evt && evt.status === 'completed') {
      if (projectIdRef.value) {
        projectStore.fetchProject(projectIdRef.value).catch(() => {/* 忽略 */})
      }
    }
  },
)

// ---------- 路由参数变化时重新加载 ----------
watch(
  projectIdRef,
  () => {
    if (projectIdRef.value) {
      loadProject()
    } else {
      projectStore.clearCurrent()
    }
  },
)

onMounted(() => {
  if (projectIdRef.value) {
    loadProject()
  }
})

onBeforeUnmount(() => {
  // 离开页面时清空当前项目状态
  projectStore.clearCurrent()
})
</script>

<style scoped>
.project-detail-view {
  min-height: 100%;
  background: var(--el-bg-color-page);
  display: flex;
  flex-direction: column;
}

.load-error {
  margin: 20px;
}

.loading-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
}

.loading-icon {
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------- 向导进度面板 ---------- */
.wizard-panel {
  padding: 32px 24px;
  background: var(--el-bg-color);
  margin: 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
}

.wizard-panel-header {
  text-align: center;
  margin-bottom: 24px;
}

.wizard-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.wizard-desc {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.wizard-steps {
  max-width: 560px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wizard-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  transition: background 0.2s;
}

.wizard-step.step-running {
  background: var(--el-color-primary-light-9);
}

.wizard-step.step-failed {
  background: var(--el-color-danger-light-9);
}

.wizard-step.step-completed {
  opacity: 0.8;
}

.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  font-weight: 600;
}

.step-completed .step-icon {
  background: var(--el-color-success);
  color: #fff;
}

.step-running .step-icon {
  background: var(--el-color-primary);
  color: #fff;
}

.step-failed .step-icon {
  background: var(--el-color-danger);
  color: #fff;
}

.step-info {
  flex: 1;
  min-width: 0;
}

.step-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.step-error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}

.wizard-error {
  max-width: 560px;
  margin: 16px auto 0;
  text-align: center;
}

/* ---------- 主体 ---------- */
.project-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>

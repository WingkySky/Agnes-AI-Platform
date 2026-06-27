<!--
  流水线执行结果页（渐进式产物可见）
  - 左右分栏布局：左侧 PipelineProgress（步骤时间线）+ 右侧 StepResultGallery（步骤结果画廊）
  - 每当 step_completed 事件触发，自动切换右侧画廊焦点到该步骤
  - 完成最终视频后，最终视频产物也展示在画廊下方
  - 通过 SSE (Server-Sent Events) 实时接收后端进度推送，HTTP 轮询兜底
  - 同步更新 taskQueue 与 pipelineStore
-->
<template>
  <div class="pipeline-result">
    <!-- 顶部：运行信息 + 状态徽章 + SSE 连接状态 -->
    <div class="result-header">
      <el-page-header @back="goBack">
        <template #content>
          <span class="header-content">
            <!-- 运行信息：#id · 创建时间 -->
            <span class="run-info">
              {{ t('pipelineResult.runInfo', { id: run?.id ?? '-', time: formatTime(run?.created_at) }) }}
            </span>
            <!-- 运行状态徽章 -->
            <el-tag
              class="status-tag"
              :type="getStatusTagType(runStatus)"
              size="small"
            >
              {{ t(`pipelineResult.stepStatus.${runStatus || 'pending'}`) }}
            </el-tag>
            <!-- SSE 连接状态徽章 -->
            <el-tag
              v-if="connectionStatusText"
              class="conn-tag"
              type="info"
              size="small"
            >
              {{ connectionStatusText }}
            </el-tag>
          </span>
        </template>
      </el-page-header>
      <div class="header-actions">
        <!-- 导出到画布按钮（仅 success 状态显示） -->
        <el-button
          v-if="runStatus === 'success'"
          type="primary"
          size="small"
          @click="handleExportToCanvas"
        >
          <el-icon><VideoCamera /></el-icon>
          {{ t('pipelineResult.exportToCanvas') }}
        </el-button>
        <!-- 暂停状态下：编辑参数 + 继续按钮 -->
        <template v-if="runStatus === 'paused'">
          <el-button
            size="small"
            @click="showEditInputsDialog = true"
          >
            <el-icon><EditPen /></el-icon>
            {{ t('pipelineResult.editInputs') }}
          </el-button>
          <el-button
            type="primary"
            size="small"
            @click="handleResume"
          >
            <el-icon><VideoCamera /></el-icon>
            {{ t('pipelineResult.continueRun') }}
          </el-button>
        </template>
        <el-button
          type="danger"
          size="small"
          :icon="Delete"
          @click="deleteCurrentRun"
        >
          {{ t('pipelineResult.deleteRun') }}
        </el-button>
      </div>
    </div>

    <!-- 主体：左右分栏（左 30% 时间线 · 右 70% 结果画廊） -->
    <div class="result-body">
      <!-- 左侧：步骤时间线 -->
      <div class="steps-panel">
        <PipelineProgress
          :steps="steps"
          :current-step-key="currentStepKey"
          :run-status="runStatus"
          :selected-step-key="selectedStepKey"
          @select-step="handleStepClick"
          @retry-step="handleRetryStep"
          @pause="handlePause"
          @resume="handleResume"
        />
      </div>

      <!-- 右侧：当前选中步骤的产出展示 -->
      <div class="output-panel">
        <StepResultGallery v-if="selectedStep" :step="selectedStep" />
        <el-empty v-else :description="t('pipelineResult.steps.preparing')" />
      </div>
    </div>

    <!-- 底部：最终结果区（仅当有最终视频时显示） -->
    <div v-if="finalVideoUrl" class="final-result">
      <el-divider />
      <h3 class="final-title">{{ t('pipelineResult.resultTitle') }}</h3>
      <!-- 成片播放器：字幕切换 + 倍速播放 + 下载 -->
      <FinalVideoPlayer
        ref="finalPlayerRef"
        :src="finalVideoUrl"
        :subtitle-url="finalVttUrl"
        :duration="finalDuration"
        :segments-count="finalSegmentsCount"
        :download-url="downloadUrl"
        @download="handleDownload"
        @time-update="handleTimeUpdate"
      />
      <div class="final-actions">
        <el-button v-permission="'pipeline:save_asset'" @click="saveToAsset">
          <el-icon><Plus /></el-icon>
          {{ t('pipelineResult.saveToAssets') }}
        </el-button>
        <!-- 切换时间轴预览显隐 -->
        <el-button v-if="finalSubtitles.length" @click="showTimeline = !showTimeline">
          <el-icon><VideoCamera /></el-icon>
          {{ t('timelinePreview.title') }}
        </el-button>
        <!-- 切换字幕编辑器显隐 -->
        <el-button v-if="finalSubtitles.length" @click="showSubtitleEditor = !showSubtitleEditor">
          <el-icon><EditPen /></el-icon>
          {{ t('subtitleEditor.title') }}
        </el-button>
      </div>

      <!-- 时间轴预览（点击可跳转视频） -->
      <el-collapse-transition>
        <TimelinePreview
          v-if="showTimeline && finalSubtitles.length"
          :subtitles="finalSubtitles"
          :duration="finalDuration"
          :current-time="currentPlayTime"
          @seek="handleTimelineSeek"
          @select="handleSubtitleSelect"
        />
      </el-collapse-transition>

      <!-- 字幕编辑器（保存后重新生成 SRT） -->
      <el-collapse-transition>
        <SubtitleEditor
          v-if="showSubtitleEditor && finalSubtitles.length"
          :run-id="runId"
          :subtitles="finalSubtitles"
          :srt-url="finalSrtUrl"
          @saved="handleSubtitlesSaved"
        />
      </el-collapse-transition>
    </div>

    <!-- 加载中状态（仅在初次加载且未拿到 run 时显示） -->
    <div v-if="loading && !run" class="loading-container">
      <el-icon :size="40" class="spin"><Loading /></el-icon>
      <p>{{ t('common.loading') }}</p>
    </div>

    <!-- 编辑输入参数对话框（paused 状态下使用） -->
    <el-dialog
      v-model="showEditInputsDialog"
      :title="t('pipelineResult.editInputs')"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item
          v-for="(_val, key) in editableInputs"
          :key="key"
          :label="key"
        >
          <el-input v-model="editableInputs[key]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditInputsDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveInputs">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElPageHeader, ElTag, ElEmpty, ElDivider, ElButton, ElIcon, ElCollapseTransition, ElDialog, ElForm, ElFormItem, ElInput } from 'element-plus'
import { Download, Plus, Loading, VideoCamera, EditPen, Delete } from '@element-plus/icons-vue'
import {
  getPipelineRunDetail,
  getPipelineRunSteps,
  retryPipelineStep,
  deletePipelineRun,
  pausePipelineRun,
  retryPipelineRun,
  updatePipelineRunInputs,
  exportRunToCanvas,
  buildDownloadUrl,
  type PipelineRun,
  type PipelineStep,
  type SubtitleEntry,
} from '@/api/pipeline'
import { usePipelineSSE } from '@/composables/usePipelineSSE'
import { useI18n } from '@/i18n'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useAssetStore } from '@/stores/asset'
import PipelineProgress from '@/components/pipeline/PipelineProgress.vue'
import StepResultGallery from '@/components/pipeline/StepResultGallery.vue'
import FinalVideoPlayer from '@/components/pipeline/FinalVideoPlayer.vue'
import TimelinePreview from '@/components/pipeline/TimelinePreview.vue'
import SubtitleEditor from '@/components/pipeline/SubtitleEditor.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// 路由参数为 :runId（见 router/index.ts）
const runId = ref<string | number>(route.params.runId as string)
const loading = ref(false)
// 运行实例（API 拉取，不会自动随 SSE 更新；状态以 sseStatus 为准）
const run = ref<PipelineRun | null>(null)
const stepsFromApi = ref<PipelineStep[]>([])

// 全局 stores
const taskQueue = useTaskQueueStore()
const assetStore = useAssetStore()

// 使用 SSE 获取实时进度（内部已集成 taskQueue / pipelineStore 同步）
const {
  connectionStatus,
  pipelineStatus: sseStatus,
  currentStep: sseCurrentStep,
  stepStates,
  outputSummary: sseOutputSummary,
  stepsFromApi: sseStepsFromApi,
  reconnect: reconnectSSE,
  pollNow: pollStatus,
} = usePipelineSSE(runId)

// ================ 合并后的步骤数据（API + SSE 实时状态） ================
// SSE 推送的 stepStates 优先覆盖 API 返回的 status / output_data，
// 这样 step_completed 后 StepResultGallery 能立即拿到新产物
// 同时保留 progress / progress_detail / output_summary，供 PipelineProgress 展示元素级进度
const steps = computed<PipelineStep[]>(() => {
  const source = sseStepsFromApi.value.length > 0 ? sseStepsFromApi.value : stepsFromApi.value
  return source.map(s => {
    const sseState = stepStates.value[s.step_key]
    if (!sseState) return s
    return {
      ...s,
      status: (sseState.status as any) || s.status,
      output_data: sseState.output || s.output_data,
      error_message: sseState.error || s.error_message,
      // SSE 实时进度（PipelineProgress 据此渲染进度条 + 元素计数 + 阶段文案）
      progress: sseState.progress,
      progress_detail: sseState.progress_detail,
      output_summary: sseState.output_summary,
    } as PipelineStep
  })
})

// ================ 选中步骤 ================
const selectedStepKey = ref<string>('')

// 当前选中步骤对象（传给 StepResultGallery）
const selectedStep = computed(() =>
  steps.value.find(s => s.step_key === selectedStepKey.value)
)

// ================ 时间轴 / 字幕编辑器显隐状态 ================
const showTimeline = ref(false)
const showSubtitleEditor = ref(false)
// 当前播放时间（秒，由 FinalVideoPlayer 的 timeupdate 事件同步）
const currentPlayTime = ref(0)
// FinalVideoPlayer 组件引用（用于 seek 跳转）
const finalPlayerRef = ref<InstanceType<typeof FinalVideoPlayer> | null>(null)

// ================ 暂停 / 编辑输入参数 ================
const showEditInputsDialog = ref(false)
const editableInputs = ref<Record<string, any>>({})

// ================ 状态便捷访问 ================
const runStatus = computed(() => sseStatus.value || run.value?.status || 'pending')
const currentStepKey = computed(() =>
  sseCurrentStep.value || run.value?.current_step_key || run.value?.current_step || ''
)

// 最终视频地址：优先使用 SSE 推送的 output_summary，其次取最后一个成功步骤的输出
// 兼容 ffmpeg_composite 步骤的输出结构（final_video_url 字段 / videos 数组）
const finalVideoUrl = computed(() => {
  const summary = sseOutputSummary.value
  if (summary) {
    if (typeof summary === 'string') return summary
    if (summary.video_url) return summary.video_url
    if (summary.url) return summary.url
    if (summary.result_url) return summary.result_url
    if (summary.final_video_url) return summary.final_video_url
  }
  // 回退：按 sort_order 倒序找最后一个成功步骤（通常是 ffmpeg_composite）
  const lastSuccess = [...steps.value]
    .filter(s => s.status === 'success')
    .sort((a, b) => b.sort_order - a.sort_order)[0]
  const out = lastSuccess?.output_data
  if (!out) return ''
  // ffmpeg_composite 步骤：优先 final_video_url，其次从 videos 数组提取 is_final 的视频
  if (out.final_video_url) return out.final_video_url
  const vids = out.videos || []
  const finalVid = vids.find((v: any) => v?.is_final) || vids[0]
  if (finalVid?.video_url || finalVid?.url) return finalVid.video_url || finalVid.url
  // 通用回退
  return out.video_url || out.url || out.result_url || ''
})

// ================ 最终视频元信息（供 FinalVideoPlayer / TimelinePreview 使用） ================
// 取最后一个 ffmpeg_composite 步骤的 output_data（包含 srt_url/duration_seconds/segments_count/subtitles）
const finalCompositeOutput = computed(() => {
  const lastSuccess = [...steps.value]
    .filter(s => s.status === 'success' && s.step_type === 'ffmpeg_composite')
    .sort((a, b) => b.sort_order - a.sort_order)[0]
  return lastSuccess?.output_data || null
})

// SRT 字幕文件 URL（来自 ffmpeg_composite 步骤输出的 srt_url 字段）
const finalSrtUrl = computed(() => finalCompositeOutput.value?.srt_url || '')

// 最终视频的 VTT 字幕 URL（浏览器 <track> 标签需要 VTT 格式，非 SRT）
const finalVttUrl = computed(() => {
  const vtt = finalCompositeOutput.value?.vtt_url || ''
  if (!vtt) return ''
  // 加时间戳防缓存（recompose 后会更新）
  return vtt
})

// 下载 URL（走带水印路由，FinalVideoPlayer 内部用 window.open 触发下载）
const downloadUrl = computed(() => {
  if (!run.value) return ''
  return buildDownloadUrl(Number(runId.value), true)
})

// 最终视频时长（秒，来自 ffprobe 测量）
const finalDuration = computed(() => finalCompositeOutput.value?.duration_seconds || 0)

// 最终视频片段数（合成前的视频段数）
const finalSegmentsCount = computed(() => finalCompositeOutput.value?.segments_count || 0)

// 字幕条目列表（来自 ffmpeg_composite 步骤输出的 subtitles 字段，供字幕编辑器使用）
// 结构: [{index, scene_index, start, end, text}, ...]
const finalSubtitles = computed<any[]>(() => finalCompositeOutput.value?.subtitles || [])

// SSE 连接状态文案
const connectionStatusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connecting': return t('pipelineResult.connectionStatus.connecting')
    case 'connected': return t('pipelineResult.connectionStatus.connected')
    case 'disconnected': return t('pipelineResult.connectionStatus.disconnected')
    case 'error': return t('pipelineResult.connectionStatus.error')
    default: return ''
  }
})

// ================ 渐进式产物可见性 ================
// 监听 steps 变化：
//   1. 检测新增的 success 步骤 → 自动切换焦点 + 触发历史刷新（让 HistoryView 看到新图片/视频）
//   2. 当前选中失效 → 回退到最新完成的步骤
const prevCompletedKeys = ref<Set<string>>(new Set())

watch(steps, (newSteps) => {
  // 当前所有已完成步骤的 key 集合
  const currentCompletedKeys = new Set(
    newSteps.filter(s => s.status === 'success').map(s => s.step_key)
  )

  // 找出"刚刚"变为 success 的步骤（之前不在已完成集合中）
  let newlyCompletedKey: string | null = null
  for (const key of currentCompletedKeys) {
    if (!prevCompletedKeys.value.has(key)) {
      newlyCompletedKey = key
    }
  }
  prevCompletedKeys.value = currentCompletedKeys

  if (newlyCompletedKey) {
    // step_completed 后自动切换右侧画廊焦点到该步骤
    selectedStepKey.value = newlyCompletedKey
    // 触发历史刷新，让 HistoryView 看到新生成的图片/视频
    taskQueue.historyRefreshSignal++
    return
  }

  // 没有新完成但当前选中无效 → 回退到最新完成的步骤
  if (
    !selectedStepKey.value ||
    !newSteps.find(s => s.step_key === selectedStepKey.value)
  ) {
    const latestCompleted = [...newSteps].reverse().find(s => s.status === 'success')
    if (latestCompleted) {
      selectedStepKey.value = latestCompleted.step_key
    }
  }
}, { deep: true, immediate: true })

// ================ 工具函数 ================

function getStatusTagType(status?: string): 'success' | 'primary' | 'danger' | 'warning' | 'info' {
  switch (status) {
    case 'success': return 'success'
    case 'running': return 'primary'
    case 'failed': return 'danger'
    case 'cancelled': return 'info'
    case 'waiting_review': return 'warning'
    case 'paused': return 'warning'
    default: return 'info'
  }
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ================ 操作处理 ================

// 修复 goBack 路由：返回工坊（原误指向 /pipeline/runs）
function goBack() {
  router.push('/workshop')
}

// 删除当前运行记录
async function deleteCurrentRun() {
  if (!run.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除运行记录「${run.value.name || run.value.template_name}」吗？此操作不可恢复。`,
      t('pipelineResult.deleteRun'),
      { confirmButtonText: t('common.delete'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    await deletePipelineRun(run.value.id)
    ElMessage.success(t('pipelineResult.deleteSuccess') || '删除成功')
    router.push('/workshop')
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '删除失败')
    }
  }
}

// 点击时间线节点切换焦点
function handleStepClick(stepKey: string) {
  selectedStepKey.value = stepKey
}

// 重试单个失败步骤（PipelineProgress 触发）
async function handleRetryStep(stepKey: string) {
  try {
    await retryPipelineStep(Number(runId.value), stepKey)
    ElMessage.success(t('pipelineResult.retried'))
    reconnectSSE()
    loadRunData()
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineResult.retryFailed'))
  }
}

// ================ 暂停 / 继续 / 编辑输入参数 ================

// 暂停流水线
async function handlePause() {
  if (!runId.value) return
  try {
    await pausePipelineRun(Number(runId.value))
    ElMessage.success(t('pipelineResult.pauseSuccess') || '已暂停')
    pollStatus()
  } catch (e: any) {
    ElMessage.error(e?.message || '暂停失败')
  }
}

// 继续运行（暂停后恢复）
async function handleResume() {
  if (!runId.value) return
  try {
    await retryPipelineRun(Number(runId.value))
    ElMessage.success(t('pipelineResult.resumeSuccess') || '已恢复运行')
    reconnectSSE()
    loadRunData()
  } catch (e: any) {
    ElMessage.error(e?.message || '恢复失败')
  }
}

// 打开编辑输入参数对话框
watch(showEditInputsDialog, (val) => {
  if (val && run.value?.inputs) {
    editableInputs.value = JSON.parse(JSON.stringify(run.value.inputs))
  }
})

// 保存编辑后的输入参数
async function handleSaveInputs() {
  if (!runId.value) return
  try {
    const result = await updatePipelineRunInputs(Number(runId.value), editableInputs.value)
    ElMessage.success(t('pipelineResult.inputsSaved') || '参数已保存')
    showEditInputsDialog.value = false
    // 刷新 run 数据以同步 inputs
    if (run.value) {
      run.value.inputs = result.inputs || editableInputs.value
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

// ================ 导出到画布 ================

async function handleExportToCanvas() {
  if (!runId.value) return
  try {
    const data = await exportRunToCanvas(Number(runId.value))
    if (!data) {
      ElMessage.warning(t('pipelineResult.noExportData') || '无可导出数据')
      return
    }
    // 导入到画布素材库
    const assets = await assetStore.importFromPipeline(data)
    ElMessage.success(t('pipelineResult.exportSuccess', { count: assets.length }) || `已导出 ${assets.length} 个素材到画布`)
    // 跳转到画布页面
    router.push('/canvas')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

// ================ 下载最终视频 ================
// FinalVideoPlayer 内部已用 window.open(downloadUrl) 触发下载（走带水印路由）
// 父组件的 handleDownload 只做副作用（日志/埋点），实际下载由 FinalVideoPlayer 完成
function handleDownload() {
  console.log('[PipelineResult] download triggered, runId=', runId.value)
}

// 保存最终视频到资产库
async function saveToAsset() {
  if (!run.value || !finalVideoUrl.value) return
  try {
    await assetStore.saveFromGeneration(run.value.id, {
      type: 'scene',
      name: `流水线 #${run.value.id} 最终视频`,
    })
    ElMessage.success(t('pipelineResult.saveToAssets'))
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineResult.saveToAssetsTip'))
  }
}

// ================ 时间轴 / 字幕编辑器事件处理 ================

// 视频播放进度更新（同步给 TimelinePreview 的游标）
function handleTimeUpdate(time: number) {
  currentPlayTime.value = time
}

// 时间轴点击 seek：跳转视频到对应时间
function handleTimelineSeek(time: number) {
  finalPlayerRef.value?.seek(time)
}

// 时间轴点击选中某条字幕：跳转到该字幕开头
function handleSubtitleSelect(sub: SubtitleEntry) {
  finalPlayerRef.value?.seek(sub.start)
}

// 字幕编辑器保存/重新烧录完成回调
// - 普通保存：后端会重新生成 SRT/VTT 文件并更新 step.output_data
// - 重新烧录（recompose）：后端会重新烧录字幕到视频，返回新的 final_video_url / vtt_url
function handleSubtitlesSaved(result: {
  srt_url: string
  subtitles: SubtitleEntry[]
  recomposed?: boolean
  final_video_url?: string
  vtt_url?: string
}) {
  // 更新本地字幕数据 + srt/vtt URL（避免等待 loadRunData 完成才生效）
  if (finalCompositeOutput.value) {
    finalCompositeOutput.value.subtitles = result.subtitles
    finalCompositeOutput.value.srt_url = result.srt_url
    if (result.vtt_url) {
      finalCompositeOutput.value.vtt_url = result.vtt_url
    }
  }

  if (result.recomposed && result.final_video_url) {
    // recompose 场景：更新 final_video_url，触发播放器重新加载
    // finalVideoUrl 是 computed，依赖 finalCompositeOutput.final_video_url
    if (finalCompositeOutput.value) {
      finalCompositeOutput.value.final_video_url = result.final_video_url
    }
    ElMessage.success(t('pipelineResult.recomposeSuccess'))
  } else {
    // 普通保存场景：提示字幕已保存
    ElMessage.success(t('pipelineResult.subtitlesSaved'))
  }

  // 主动拉取一次最新步骤，让 finalSrtUrl / finalSubtitles / vtt_url 与后端同步
  loadRunData()
  // 同时让 SSE 也拉取一次（双重保险）
  pollStatus()
}

// 拉取运行详情与步骤列表
async function loadRunData() {
  if (!runId.value) return
  loading.value = true
  try {
    const [runRes, stepsRes] = await Promise.all([
      getPipelineRunDetail(Number(runId.value)),
      getPipelineRunSteps(Number(runId.value)),
    ])
    run.value = runRes
    stepsFromApi.value = stepsRes
    // 若 SSE 仍处于 pending 但 API 已有更新状态，主动拉取一次
    if (sseStatus.value === 'pending' && runRes.status !== 'pending') {
      pollStatus()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || t('pipelineResult.loadFailed'))
  } finally {
    loading.value = false
  }
}

// ================ 生命周期 ================

onMounted(() => {
  loadRunData()
})

// 路由参数变化时重新加载
watch(() => route.params.runId, (newId) => {
  if (newId && newId !== runId.value) {
    runId.value = newId as string
    run.value = null
    stepsFromApi.value = []
    // 重置已完成步骤追踪集合，避免误判
    prevCompletedKeys.value = new Set()
    selectedStepKey.value = ''
    loadRunData()
  }
})
</script>

<style scoped>
/* =====================================================
 * 流水线结果页样式（使用全局 --agnes-* CSS 变量，支持深/浅色主题）
 * 左右分栏：左 30% 时间线 · 右 70% 结果画廊
 * ===================================================== */

.pipeline-result {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px;
}

/* ---------- 顶部页头 ---------- */
.result-header {
  margin-bottom: 16px;
}

.header-content {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.run-info {
  font-size: 14px;
  color: var(--agnes-text-secondary);
}

.status-tag,
.conn-tag {
  margin-left: 4px;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ---------- 主体分栏 ---------- */
.result-body {
  display: grid;
  grid-template-columns: minmax(280px, 30%) 1fr;
  gap: 20px;
  align-items: flex-start;
}

.steps-panel {
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  padding: 16px;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}

.output-panel {
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  padding: 20px;
  min-height: 400px;
}

/* ---------- 最终结果区 ---------- */
.final-result {
  margin-top: 24px;
}

.final-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0 0 12px 0;
}

.final-video {
  width: 100%;
  max-width: 720px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border);
  background: #000;
}

.final-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

/* ---------- 加载状态 ---------- */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: var(--agnes-text-muted);
  gap: 16px;
}

.loading-container .spin {
  color: var(--agnes-primary);
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------- 响应式 ---------- */
@media (max-width: 960px) {
  .result-body {
    grid-template-columns: 1fr;
  }

  .steps-panel {
    position: static;
    max-height: none;
  }
}
</style>

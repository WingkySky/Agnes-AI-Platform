<!-- =====================================================
     视频生成视图 VideoView（已接入全局任务队列 Store）
     模式：
       - 文生视频 (text2video)
       - 图生视频 (image2video)
       - 关键帧动画 (keyframes)
     - 所有 UI 文案通过 i18n.t() 调用实现多语言
     ===================================================== -->

<template>
  <div class="video-view">
    <h2 class="page-title">{{ t('view.videoTitle') }}</h2>
    <p class="page-desc">{{ t('view.videoDesc') }}</p>

    <el-row :gutter="24">
      <!-- 左侧：参数 -->
      <el-col :xs="24" :md="11">
        <el-card shadow="never">
          <template #header>
          <div class="card-header"><span>{{ t('params.title') }}</span></div>
          </template>

          <!-- 模式切换：三选一，图标 + 标题 + 短副标签，一眼分辨 -->
          <el-tabs v-model="mode" class="mode-tabs">
              <el-tab-pane name="text2video">
                <template #label>
                  <span class="mode-label">
                    <el-icon class="mode-icon"><Edit /></el-icon>
                    <span class="mode-text">
                      <span class="mode-title">{{ t('params.mode.text2video') }}</span>
                      <span class="mode-sub">{{ t('params.mode.textOnly') }}</span>
                    </span>
                  </span>
                </template>
              </el-tab-pane>
              <el-tab-pane name="image2video">
                <template #label>
                  <span class="mode-label">
                    <el-icon class="mode-icon"><PictureFilled /></el-icon>
                    <span class="mode-text">
                      <span class="mode-title">{{ t('params.mode.image2video') }}</span>
                      <span class="mode-sub">{{ t('params.mode.imageOnly') }}</span>
                    </span>
                  </span>
                </template>
              </el-tab-pane>
              <el-tab-pane name="keyframes">
                <template #label>
                  <span class="mode-label">
                    <el-icon class="mode-icon"><Film /></el-icon>
                    <span class="mode-text">
                      <span class="mode-title">{{ t('params.mode.keyframes') }}</span>
                      <span class="mode-sub">{{ t('params.mode.keyframesHint') }}</span>
                    </span>
                  </span>
                </template>
              </el-tab-pane>
          </el-tabs>

          <!-- 图生视频：单张参考图（限制1张，URL/文件混用） -->
          <ImageUploader
            v-if="mode === 'image2video'"
            :max-count="1"
            :title="t('params.startFrameImage')"
            @change="handleImageChange"
            @clear="handleImageClear"
          />

          <!-- 首尾帧模式：起始帧 + 结束帧（上下排列，各1张，URL/文件混用） -->
          <div v-if="mode === 'keyframes'" class="frame-upload">
            <div class="frame-section frame-section-start">
              <ImageUploader
                :max-count="1"
                :title="t('params.startFrameImage')"
                @change="(f) => handleFrameChange('start', f)"
                @clear="() => handleFrameClear('start')"
              />
            </div>

            <!-- 连接指示线：起始帧 → 结束帧 -->
            <div class="frame-connector">
              <div class="connector-line"></div>
              <div class="connector-arrow"><el-icon><ArrowDownBold /></el-icon></div>
              <div class="connector-line"></div>
            </div>

            <div class="frame-section frame-section-end">
              <ImageUploader
                :max-count="1"
                :title="t('params.endFrameImage')"
                :optional="true"
                @change="(f) => handleFrameChange('end', f)"
                @clear="() => handleFrameClear('end')"
              />
            </div>
          </div>

          <el-form label-position="top" class="param-form">
            <el-form-item :label="t('params.prompt')">
              <el-input v-model="prompt" type="textarea" :rows="4"
                :placeholder="t('params.videoPromptPlaceholder')" maxlength="15000" show-word-limit />
              <div :class="['prompt-length-hint', promptLengthLevel]">
                <el-icon><InfoFilled /></el-icon>
                <span>{{ promptLengthText }}</span>
              </div>
            </el-form-item>

            <el-form-item :label="t('params.negativePrompt')">
              <el-input v-model="negativePrompt" type="textarea" :rows="2"
                :placeholder="t('params.negativePromptPlaceholder')" />
            </el-form-item>

            <PromptTemplates :templates="videoTemplates" @select="appendStylePrompt" />

            <!-- 紧凑参数选择：比例 + 分辨率 + 时长 + 帧率 + 模型，一行标签搞定 -->
            <el-form-item :label="t('params.aspectRatio')">
              <ParamSelector
                mode="video"
                v-model:aspectRatio="aspectRatio"
                v-model:resolution="resolution"
                v-model:seconds="seconds"
                v-model:frameRate="frameRate"
                v-model:model="videoModel"
              />
            </el-form-item>

            <el-row :gutter="16">
              <el-col :span="24">
                <el-form-item :label="t('params.randomSeed')">
                  <el-input v-model="seed" :placeholder="t('params.seedPlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 生成按钮 -->
            <el-button
              type="primary"
              size="large"
              class="generate-btn"
              :disabled="!canSubmit"
              @click="startGenerate">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ t('generate.videoBtn') }}</span>
            </el-button>

            <!-- 分享到广场开关：提交时携带 is_public 参数 -->
            <div class="share-toggle">
              <el-icon class="share-icon"><Share /></el-icon>
              <span class="share-label">{{ t('plaza.shareToPlaza') }}</span>
              <el-switch v-model="shareToPlaza" size="small" />
            </div>

            <!-- 积分扣除提示：显示本次生成预估消耗的积分 -->
            <div v-if="userStore.credits > 0" class="cost-hint">
              <span v-if="costLoading" class="cost-loading">{{ t('generate.costLoading') }}</span>
              <span v-else-if="cost !== null" :class="['cost-value', { insufficient: costInsufficient }]">
                {{ t('generate.costHint').replace('{n}', String(cost)) }}
              </span>
            </div>

            <!-- 积分不足提示：禁用生成按钮时引导用户充值 -->
            <div v-if="userStore.credits <= 0" class="no-credits-hint">
              {{ t('generate.noCreditsVideo') }}
            </div>

            <div class="queue-hint">
              {{ t('generate.running') }}: {{ queue.runningVideoCount }} / 5 · {{ t('generate.submitted') }}: {{ queue.tasks && Object.keys(queue.tasks).length }}
            </div>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：预览/结果区（显示 "当前选中任务" 的状态） -->
      <el-col :xs="24" :md="13">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <div class="header-title">
                <span>{{ t('preview.resultTitle') }}</span>
                <span v-if="activeTask" class="task-pill" :class="'status-' + activeTask.status">
                  {{ statusLabel }}
                </span>
              </div>
              <span v-if="videoUrl" class="header-actions">
                <el-button size="small" @click="downloadVideo">
                  <el-icon><Download /></el-icon>
                  {{ t('preview.download') }}
                </el-button>
              </span>
            </div>
          </template>

          <!-- 情况 A：有选中任务且正在进行中 -->
          <div v-if="activeTask && taskRunning" class="result-loading">
            <div class="task-id-row">{{ t('status.taskId') }}: {{ activeTask.taskId }}</div>
            <el-progress
              :percentage="taskProgress"
              :stroke-width="12"
              :color="progressColor" />
            <div class="loading-text">{{ statusLabel }} ...</div>
            <div class="loading-sub">{{ t('status.elapsedSeconds') }} {{ taskElapsedSec }} {{ t('common.seconds') }}</div>
            <div class="prompt-row">{{ activeTask.prompt }}</div>
            <el-button
              type="danger"
              size="small"
              class="cancel-btn-inline"
              @click="cancelActiveTask">
              <el-icon><CircleCloseFilled /></el-icon>
              {{ t('status.cancelTask') }}
            </el-button>
          </div>

          <!-- 情况 B：有选中任务且已成功 -->
          <div v-else-if="activeTask && activeTask.status === 'success'" class="result-wrap">
            <div class="video-container">
              <video
                v-if="videoUrl"
                ref="videoEl"
                :src="videoUrl"
                :poster="posterUrl"
                controls
                playsinline
                preload="metadata"
                class="result-video"
                @loadeddata="capturePoster"
                @loadedmetadata="onVideoLoaded"
                @error="handleVideoError"
                @canplay="onVideoCanPlay"
              ></video>
              <div v-else class="video-placeholder">
                <el-icon :size="48" color="var(--agnes-warning)"><VideoPlay /></el-icon>
                <div class="placeholder-title">{{ t('preview.videoUrlEmptyTitle') }}</div>
                <div class="placeholder-sub">{{ t('preview.videoEmpty') }}</div>
              </div>
            </div>

            <!-- 操作区 -->
            <div class="action-row">
              <el-button type="primary" size="small" @click="downloadVideo">
                <el-icon><Download /></el-icon>
                {{ t('preview.download') }}
              </el-button>
              <el-button size="small" @click="copyVideoUrl">
                <el-icon><CopyDocument /></el-icon>
                {{ t('preview.copyLink') }}
              </el-button>
              <el-button size="small" @click="openInNewTab">
                <el-icon><VideoPlay /></el-icon>
                {{ t('preview.openNewTab') }}
              </el-button>
            </div>

            <!-- 元信息 -->
            <div class="result-meta">
              <div class="meta-row">{{ t('params.prompt') }}: {{ activeTask.prompt }}</div>
              <div class="meta-row">{{ t('status.label') }}: <span class="tag-success">{{ t('status.success') }}</span> · {{ t('status.elapsedSeconds') }} {{ taskElapsedSec }} {{ t('common.seconds') }}</div>
              <div v-if="activeTask.taskId" class="meta-row">{{ t('status.taskId') }}: {{ activeTask.taskId }}</div>
            </div>
          </div>

          <!-- 情况 C：任务失败 -->
          <div v-else-if="activeTask && activeTask.status === 'failed'" class="result-failed">
            <el-icon :size="48" :color="'var(--agnes-error)'"><CircleCloseFilled /></el-icon>
            <div class="failed-text">{{ t('status.videoGenerateFailed') }}</div>
            <div class="failed-sub">{{ activeTask.errorMessage || '' }}</div>
            <el-button type="primary" size="small" class="retry-btn" @click="retryActiveTask">
              {{ t('status.retryWithSame') }}
            </el-button>
          </div>

          <!-- 情况 D：任务已取消 -->
          <div v-else-if="activeTask && activeTask.status === 'cancelled'" class="result-failed">
            <el-icon :size="48" :color="'var(--agnes-warning)'"><CircleCloseFilled /></el-icon>
            <div class="failed-text">{{ t('status.cancelled') }}</div>
            <div class="failed-sub">{{ t('preview.wrongTypeHint') }}</div>
          </div>

          <!-- 情况 E：选中的是图片任务，不匹配当前视图 -->
          <div v-else-if="activeTaskIsOtherType" class="empty-state">
            <el-icon :size="48"><MagicStick /></el-icon>
            <p class="empty-text">{{ t('preview.wrongTypeVideo') }}</p>
            <p class="empty-sub">{{ t('preview.switchPageHint') }}</p>
          </div>

          <!-- 情况 F：没有选中的任务 -->
          <div v-else class="empty-state">
            <el-icon :size="48"><VideoCameraFilled /></el-icon>
            <p class="empty-text">{{ t('preview.notSelectable') }}</p>
            <p class="empty-sub">{{ t('preview.emptyHint') }}</p>
          </div>
        </el-card>

        <div class="tips-card">
          <div class="tip-title">{{ t('tips.title') }}</div>
          <ul>
            <li>{{ t('tips.concurrentVideo') }}</li>
            <li>{{ t('tips.queueSwitch') }}</li>
            <li>{{ t('tips.historyKeep') }}</li>
          </ul>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  VideoPlay, Download, CopyDocument, CircleCloseFilled, VideoCameraFilled, Loading, MagicStick,
  Edit, Film, PictureFilled, ArrowDownBold, Share, InfoFilled
} from '@element-plus/icons-vue'
import PromptTemplates from '@/components/PromptTemplates.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import ParamSelector from '@/components/ParamSelector.vue'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'
import { useI18n } from '@/i18n'
import { useCreditEstimate } from '@/composables/useCreditEstimate'
import { useDownload } from '@/composables/useDownload'
import { matchVideoAspectRatio, getVideoAspectRatioLabel } from '@/config/model-params'
import type { FileInfo } from '@/types'

const { t } = useI18n()
const userStore = useUserStore()
const { downloadViaProxy } = useDownload()

const videoTemplates = computed(() => ([
  { label: t('presets.cinematicShot'), prompt: '，电影镜头感，缓慢平移，平滑 dolly-in，戏剧性光影' },
  { label: t('presets.slowMotion'), prompt: '，慢动作，细腻细节，优雅节奏' },
  { label: t('presets.handheldFollow'), prompt: '，手持跟拍，真实感，纪实' },
  { label: t('presets.neonNight'), prompt: '，霓虹夜景，水面反光，都市感' },
  { label: t('presets.aerialShot'), prompt: '，航拍大远景，缓慢扫镜，史诗感' },
  { label: t('presets.smoothTransition'), prompt: '，丝滑电影感过渡，电影级调色' }
]))

// ---------- 模型列表 ----------
const modelsStore = useModelsStore()
const VIDEO_MODELS = computed(() => modelsStore.videoModels)

// ---------- 表单参数 ----------
const mode = ref('text2video')
const prompt = ref('')
const negativePrompt = ref('')

// ---------- 提示词长度分阶提示 ----------
// 视频：0-2000 适中，2000-6000 较长，6000+ 过长
const promptLengthLevel = computed(() => {
  const len = prompt.value.length
  if (len <= 2000) return 'level-good'
  if (len <= 6000) return 'level-long'
  return 'level-too-long'
})
const promptLengthText = computed(() => {
  const len = prompt.value.length
  if (len === 0) return ''
  if (len <= 2000) return t('params.promptLengthGood')
  if (len <= 6000) return t('params.promptLengthLong')
  return t('params.promptLengthTooLong')
})

// 分享到广场开关：是否将本次生成结果公开到广场
const shareToPlaza = ref(false)
// 画面比例、时长、帧率均从 store 配置获取默认值
const aspectRatio = ref(modelsStore.defaultVideoAspectRatio || '16:9')
const resolution = ref(modelsStore.defaultVideoResolution || 768)
const seconds = ref(modelsStore.defaultVideoDuration || 5)
const frameRate = ref(modelsStore.defaultFrameRate || 24)
const seed = ref('')
const videoModel = ref('')  // 初始值在 store 加载后自动设置

// ---------- 积分预估：根据 mode + seconds + frameRate 自动计算本次生成消耗 ----------
// num_frames = seconds * frameRate，与后端计费逻辑保持一致
const { cost, loading: costLoading, insufficient: costInsufficient } = useCreditEstimate(
  () => ({
    type: 'video' as const,
    mode: mode.value,
    seconds: seconds.value,
    num_frames: seconds.value * frameRate.value,
  })
)

// 视频时长选项从 store 配置获取
// 默认全量候选项；按当前帧率过滤后的可选列表在 ParamSelector 内部实现
const DURATION_OPTIONS = computed(() => modelsStore.videoDurations.length > 0
  ? modelsStore.videoDurations
  : [3, 5, 7, 10, 15])

// 视频帧率选项从 store 配置获取
const FRAME_RATE_OPTIONS = computed(() => modelsStore.videoFrameRates.length > 0
  ? modelsStore.videoFrameRates
  : [24, 30])

// store 加载完成后自动设置默认模型和参数
watch(() => modelsStore.defaultVideoModel, (v) => {
  if (v && !videoModel.value) videoModel.value = v
}, { immediate: true })
watch(() => modelsStore.defaultVideoAspectRatio, (v) => {
  if (v && aspectRatio.value === '16:9') aspectRatio.value = v
})
watch(() => modelsStore.defaultVideoDuration, (v) => {
  if (v && seconds.value === 5) seconds.value = v
})
watch(() => modelsStore.defaultFrameRate, (v) => {
  if (v && frameRate.value === 24) frameRate.value = v
})

// ---------- 图片状态（图生视频：单张；首尾帧：起始帧+结束帧）----------
const referenceFile = ref<FileInfo | null>(null)         // image2video 模式的参考图
const startFrameFile = ref<FileInfo | null>(null)        // keyframes 模式的起始帧
const endFrameFile = ref<FileInfo | null>(null)          // keyframes 模式的结束帧

// ---------- 视频播放状态 ----------
const videoEl = ref<HTMLVideoElement | null>(null)
const posterUrl = ref('')

// ---------- 使用全局 Store 管理任务 ----------
const queue = useTaskQueueStore()

// 当前预览的任务 = Store 中的 activeTask，但仅当其是视频类型
const activeTask = computed(() => {
  if (!queue.activeTaskId) return null
  const task = queue.tasks[queue.activeTaskId]
  if (!task) return null
  return task.type === 'video' ? task : null
})

// 选中任务是否为图片类型
const activeTaskIsOtherType = computed(() => {
  if (!queue.activeTaskId) return false
  const task = queue.tasks[queue.activeTaskId]
  return task && task.type !== 'video'
})

// 选中任务是否正在进行中
const taskRunning = computed(() => {
  if (!activeTask.value) return false
  return ['pending', 'queued', 'processing'].includes(activeTask.value.status)
})

// 进度、耗时
const taskProgress = computed(() => {
  if (!activeTask.value) return 0
  return Math.min(activeTask.value.progress || 0, 99)
})
const taskElapsedSec = computed(() => {
  if (!activeTask.value) return 0
  const created = activeTask.value.createdAt || 0
  if (!created) return 0
  queue._tick
  return Math.floor((Date.now() - created) / 1000)
})

// 视频 URL：代理地址
const videoUrl = computed(() => {
  if (!activeTask.value) return ''
  const status = activeTask.value.status
  if (status === 'success') {
    // 直接使用 Agnes CDN 的原始 URL，
    // 不走后端代理，因为 <video src> 无法携带 JWT
    return activeTask.value.resultUrl || (activeTask.value as any).url || ''
  }
  return ''
})

// 原始直链 URL（下载、复制链接）
const rawVideoUrl = computed(() => {
  if (!activeTask.value) return ''
  return activeTask.value.resultUrl || (activeTask.value as any).url || ''
})

// 状态标签（使用 i18n 显示本地化名称）
const statusLabel = computed(() => {
  if (!activeTask.value) return ''
  const s = activeTask.value.status
  const key = `status.${s}`
  const localized = t(key)
  return localized === key ? s : localized
})

const progressColor = 'var(--agnes-primary)'

// 能否提交
const canSubmit = computed(() => {
  if (!prompt.value.trim()) return false
  if (queue.runningVideoCount >= 5) return false
  if (userStore.credits <= 0) return false
  return true
})

function appendStylePrompt(tpl: string) {
  if (!prompt.value.trim().endsWith(tpl)) {
    prompt.value = prompt.value.trim() + tpl
  }
}

// ---------- 图片管理（图生视频 + 首尾帧）----------
// 图生视频：单张参考图
function handleImageChange(files: FileInfo[]) {
  if (!files || !files.length) {
    referenceFile.value = null
    return
  }
  referenceFile.value = files[0]
  // 图生视频自适应比例：上传参考图后自动匹配最接近的预设比例
  autoMatchAspectRatio(files[0])
}
function handleImageClear() {
  referenceFile.value = null
}

// 首尾帧模式：起始帧 / 结束帧
function handleFrameChange(frameType: string, files: FileInfo[]) {
  if (!files || !files.length) {
    if (frameType === 'start') startFrameFile.value = null
    else endFrameFile.value = null
    return
  }
  if (frameType === 'start') {
    startFrameFile.value = files[0]
    // 起始帧上传后自动匹配比例
    autoMatchAspectRatio(files[0])
  } else {
    endFrameFile.value = files[0]
  }
}
function handleFrameClear(frameType: string) {
  if (frameType === 'start') startFrameFile.value = null
  else endFrameFile.value = null
}

/** 根据上传图片的实际尺寸自动匹配最接近的视频宽高比 */
function autoMatchAspectRatio(file: FileInfo) {
  const img = new Image()
  img.onload = () => {
    const matched = matchVideoAspectRatio(img.naturalWidth, img.naturalHeight)
    if (matched && matched !== aspectRatio.value) {
      aspectRatio.value = matched
    }
  }
  img.src = file.previewUrl || file.url || ''
}

// ---------- 开始生成 ----------
async function startGenerate() {
  if (!prompt.value.trim()) {
    ElMessage.warning(t('message.pleaseFillPrompt'))
    return
  }
  if (mode.value === 'image2video' && !referenceFile.value) {
    ElMessage.warning(t('message.pleaseUploadRefImage'))
    return
  }
  if (queue.runningVideoCount >= 5) {
    ElMessage.warning(t('generate.concurrentVideoLimit'))
    return
  }
  // 积分预检：避免无积分用户提交后被后端 402 拒绝
  if (userStore.credits <= 0) {
    ElMessage.warning(t('generate.noCreditsVideo'))
    return
  }

  // 根据分辨率（高度）和宽高比计算具体的 width/height
  // 宽高必须为 8 的倍数（视频编码硬性要求）
  let videoWidth: number | undefined
  let videoHeight: number | undefined
  if (resolution.value && aspectRatio.value) {
    const arParts = aspectRatio.value.split(':')
    if (arParts.length === 2) {
      const arW = parseInt(arParts[0], 10)
      const arH = parseInt(arParts[1], 10)
      if (arW > 0 && arH > 0) {
        const h = resolution.value
        const w = Math.round(h * arW / arH)
        // 确保宽高为 8 的倍数（视频编码硬性要求，向上取整）
        videoWidth = Math.floor((w + 7) / 8) * 8
        videoHeight = Math.floor((h + 7) / 8) * 8
      }
    }
  }

  const params: Record<string, any> = {
    prompt: prompt.value.trim(),
    negative_prompt: negativePrompt.value.trim() || undefined,
    model: videoModel.value,
    aspect_ratio: aspectRatio.value,
    width: videoWidth,
    height: videoHeight,
    seconds: seconds.value,
    frame_rate: frameRate.value,
    mode: mode.value,
    seed: seed.value ? Number(seed.value) : undefined,
    is_public: shareToPlaza.value,
  }
  if (mode.value === 'image2video' && referenceFile.value) {
    // 图生视频：单张参考图（优先纯 base64 → url → Data URI 兜底）
    params.image = referenceFile.value.base64 || referenceFile.value.url || referenceFile.value.previewUrl
    if (referenceFile.value.mimeType) {
      params.image_mime_type = referenceFile.value.mimeType
    }
  }
  if (mode.value === 'keyframes') {
    // 首尾帧模式：起始帧必填，结束帧可选
    if (!startFrameFile.value) {
      ElMessage.warning(t('message.pleaseUploadStartFrame'))
      return
    }
    // 收集起始帧和结束帧为 images 数组（后端统一处理）
    const imgs = []
    const mimeTypes = []

    // 起始帧
    const startImg = startFrameFile.value.base64 || startFrameFile.value.url || startFrameFile.value.previewUrl
    if (startImg) {
      imgs.push(startImg.trim())
      mimeTypes.push(startFrameFile.value.mimeType || 'image/png')
    }

    // 结束帧（可选）
    if (endFrameFile.value) {
      const endImg = endFrameFile.value.base64 || endFrameFile.value.url || endFrameFile.value.previewUrl
      if (endImg) {
        imgs.push(endImg.trim())
        mimeTypes.push(endFrameFile.value.mimeType || 'image/png')
      }
    }

    if (imgs.length === 0) {
      ElMessage.warning(t('message.pleaseUploadStartFrame'))
      return
    }
    params.images = imgs
    params.image_mime_types = mimeTypes
  }

  try {
    const taskId = await queue.submitVideoTask(params)
    queue.setActiveTask(taskId)
    ElMessage.success(t('generate.videoSubmitted'))
  } catch (e) {
    console.error('[VideoView] 提交任务失败：', e)
    ElMessage.error(t('generate.createTaskFailed') + ((e as Error).message || ''))
  }
}

// ---------- 中止/重试 ----------
function cancelActiveTask() {
  if (!queue.activeTaskId) return
  queue.cancelTask(queue.activeTaskId)
  ElMessage.info(t('status.taskCancelled'))
}

function retryActiveTask() {
  if (!activeTask.value) return
  const taskId = queue.retryTask(activeTask.value.taskId)
  if (taskId) {
    queue.setActiveTask(taskId)
    ElMessage.success(t('status.taskResubmitted'))
  } else {
    ElMessage.warning(t('status.retryFailed'))
  }
}

// ---------- 下载 / 复制 / 新标签页 ----------
async function downloadVideo() {
  const url = rawVideoUrl.value || videoUrl.value
  if (!url) {
    ElMessage.warning(t('preview.videoEmpty'))
    return
  }
  try {
    // 通过后端代理下载，携带 JWT 并设置 Content-Disposition: attachment 强制浏览器保存文件
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const proxyUrl = `${baseURL}/api/download?url=${encodeURIComponent(url)}&type=video`
    await downloadViaProxy(proxyUrl, `agnes-video-${Date.now()}.mp4`)
    ElMessage.success(t('preview.download'))
  } catch (err: any) {
    console.warn('[VideoView] 下载失败：', err)
    ElMessage.error(err?.message || t('preview.videoCorsWarning'))
  }
}

function copyVideoUrl() {
  const url = rawVideoUrl.value || videoUrl.value
  if (!url) {
    ElMessage.warning(t('preview.imageUrlEmpty'))
    return
  }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url)
      .then(() => ElMessage.success(t('preview.copySuccess')))
      .catch(() => ElMessage.error(t('preview.copyFailed')))
  } else {
    const ta = document.createElement('textarea')
    ta.value = url
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    ElMessage.success(t('preview.copySuccess'))
  }
}

function openInNewTab() {
  const url = rawVideoUrl.value || videoUrl.value
  if (!url) {
    ElMessage.warning(t('preview.videoEmpty'))
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
  ElMessage.success(t('preview.openNewTab'))
}

// ---------- 视频事件 ----------
function capturePoster() {
  const el = videoEl.value
  if (!el || !el.videoWidth) return
  try {
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 720 / el.videoWidth)
    canvas.width = Math.floor(el.videoWidth * scale)
    canvas.height = Math.floor(el.videoHeight * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(el, 0, 0, canvas.width, canvas.height)
    posterUrl.value = canvas.toDataURL('image/jpeg', 0.82)
  } catch (e) {
    console.warn('[VideoView] canvas 截图失败：', e)
  }
}
function onVideoLoaded() { }
function onVideoCanPlay() { }
function handleVideoError(e: Event) {
  console.error('[VideoView] 视频播放失败：', e)
  ElMessage.error(t('preview.videoLoadFailed'))
}
</script>

<style scoped>
.video-view { color: var(--agnes-text-primary); }
.page-title { margin: 0 0 4px 0; }
.page-desc { color: var(--agnes-text-muted); font-size: 14px; margin-bottom: 20px; line-height: 1.6; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.task-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.task-pill.status-queued,
.task-pill.status-pending,
.task-pill.status-processing {
  background: var(--agnes-info-bg);
  color: var(--agnes-text-muted);
}
.task-pill.status-success {
  background: var(--agnes-success-bg);
  color: var(--agnes-success);
}
.task-pill.status-failed {
  background: var(--agnes-error-bg);
  color: var(--agnes-error);
}
.task-pill.status-cancelled {
  background: var(--agnes-warning-bg);
  color: var(--agnes-warning);
}
.tab-sub { font-size: 12px; color: var(--agnes-text-muted); margin-left: 6px; }
/* 模式切换：图标 + 标题 + 短副标签，三行结构，让三个功能一眼可辨 */
.mode-tabs :deep(.el-tabs__nav) {
  width: 100%;
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid var(--agnes-border);
}
.mode-tabs :deep(.el-tabs__item) {
  flex: 1;
  min-width: 0;
  text-align: center;
  padding: 14px 16px;
  height: auto;
  line-height: 1.4;
}
.mode-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  background: linear-gradient(90deg, var(--agnes-primary), var(--agnes-primary-soft));
  border-radius: 3px 3px 0 0;
}
.mode-tabs .mode-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
}
.mode-tabs .mode-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.mode-tabs .mode-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  line-height: 1.3;
}
.mode-tabs .mode-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  white-space: nowrap;
}
.mode-tabs :deep(.is-active) .mode-title,
.mode-tabs :deep(.is-active) .mode-icon {
  color: var(--agnes-primary-soft);
}
.mode-tabs .mode-sub {
  font-size: 12px;
  color: var(--agnes-text-muted);
  margin-top: 2px;
  white-space: nowrap;
}

/* 统一表单标签：更醒目、更有视觉层级 */
.param-form :deep(.el-form-item__label) {
  color: var(--agnes-text-secondary) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding-bottom: 6px !important;
  letter-spacing: 0.3px;
}

/* 统一输入/下拉控件：贴合深色主题 */
.param-form :deep(.el-input__wrapper),
.param-form :deep(.el-textarea__inner),
.param-form :deep(.el-select) {
  background: var(--agnes-bg-input) !important;
  border-color: var(--agnes-border) !important;
  border-radius: 10px !important;
  box-shadow: none !important;
  color: var(--agnes-text-primary) !important;
}

.param-form :deep(.el-textarea__inner) {
  padding: 12px !important;
  font-size: 14px !important;
  line-height: 1.55 !important;
}

.param-form :deep(.el-input__wrapper:hover),
.param-form :deep(.el-textarea__inner:hover),
.param-form :deep(.el-select .el-select__wrapper:hover) {
  border-color: var(--agnes-primary-border) !important;
}

.param-form :deep(.el-select .el-select__wrapper) {
  box-shadow: none !important;
  background: var(--agnes-bg-input) !important;
  border-radius: 10px !important;
  min-height: 36px !important;
}

.param-form :deep(.el-input__inner),
.param-form :deep(.el-select__placeholder),
.param-form :deep(.el-select__selected-item) {
  color: var(--agnes-text-primary) !important;
  font-size: 14px !important;
}

.param-form :deep(.el-input__placeholder),
.param-form :deep(.el-select__placeholder) {
  color: var(--agnes-text-muted) !important;
}

.param-form { margin-top: 12px; }

/* 提示词长度分阶提示 */
.prompt-length-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 12px;
}
.prompt-length-hint .el-icon {
  font-size: 14px;
}
.prompt-length-hint.level-good {
  color: var(--agnes-success);
}
.prompt-length-hint.level-long {
  color: var(--agnes-warning);
}
.prompt-length-hint.level-too-long {
  color: var(--agnes-error);
}

.generate-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  margin-top: 8px;
  border-radius: 12px !important;
}
/* 分享到广场开关：低调显示在生成按钮下方 */
.share-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.share-toggle .share-icon {
  font-size: 14px;
}
.share-toggle .share-label {
  margin-right: 4px;
}
.queue-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  text-align: center;
}

/* 积分不足提示 */
.no-credits-hint {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--agnes-error-bg);
  border: 1px solid var(--agnes-error-border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--agnes-error);
  text-align: center;
}

/* 积分扣除提示 */
.cost-hint {
  margin-top: 8px;
  font-size: 12px;
  text-align: center;
  color: var(--agnes-warning);
}
.cost-hint .cost-loading {
  color: var(--agnes-text-muted);
}
.cost-hint .cost-value.insufficient {
  color: var(--agnes-error);
}
.section-title {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  margin: 12px 0 10px;
  font-weight: 500;
}

/* 结果区 */
.result-loading {
  padding: 50px 20px;
  text-align: center;
}
.task-id-row {
  font-size: 12px;
  color: var(--agnes-text-faint);
  margin-bottom: 16px;
  font-family: monospace;
}
.loading-text {
  margin-top: 16px;
  font-size: 16px;
  color: var(--agnes-text-primary);
}
.loading-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.prompt-row {
  margin-top: 16px;
  padding: 10px 14px;
  background: var(--agnes-bg-inset);
  border-radius: 8px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
  text-align: left;
  word-break: break-word;
  max-height: 80px;
  overflow: auto;
}
.cancel-btn-inline { margin-top: 20px; }
.result-wrap { text-align: center; }

.video-container {
  position: relative;
  width: 100%;
  background: var(--agnes-bg-dark-surface);
  border-radius: 12px;
  overflow: hidden;
}
.video-placeholder {
  padding: 60px 20px;
  text-align: center;
  color: var(--agnes-warning);
  background: linear-gradient(135deg, #2a1a0a 0%, #1a1a2e 100%);
  border-radius: 12px;
}
.placeholder-title { margin-top: 16px; font-size: 16px; font-weight: 600; }
.placeholder-sub { margin-top: 8px; font-size: 13px; color: var(--agnes-text-muted); }

.result-video {
  width: 100%;
  max-height: 500px;
  border-radius: 12px;
  background: var(--agnes-bg-dark-surface);
  display: block;
}

.action-row {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  justify-content: center;
  flex-wrap: wrap;
}

.result-meta {
  margin-top: 16px;
  padding: 12px;
  background: var(--agnes-bg-inset);
  border-radius: 8px;
  text-align: left;
}
.meta-row { font-size: 13px; padding: 4px 0; color: var(--agnes-text-primary); word-break: break-word; }
.tag-success {
  display: inline-block;
  padding: 2px 8px;
  background: var(--agnes-success-bg);
  color: var(--agnes-success);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.result-failed {
  padding: 60px 20px;
  text-align: center;
  color: var(--agnes-error);
}
.failed-text { margin-top: 16px; font-size: 16px; color: var(--agnes-error); }
.failed-sub { font-size: 12px; color: var(--agnes-text-muted); margin-top: 6px; }
.retry-btn { margin-top: 20px; }

.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--agnes-text-faint);
}
.empty-text { margin-top: 16px; font-size: 14px; }
.empty-sub { margin-top: 8px; font-size: 12px; color: var(--agnes-text-muted); line-height: 1.6; }

.tips-card {
  margin-top: 16px;
  padding: 16px 20px;
  background: var(--agnes-bg-inset);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 12px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
}
.tip-title { font-weight: 600; color: var(--agnes-text-primary); margin-bottom: 8px; }
.tips-card ul { margin: 0; padding-left: 20px; line-height: 1.8; }
/* 首尾帧上传布局（上下排列） */
.frame-upload {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.frame-section {
  width: 100%;
}
.frame-section-start .image-uploader,
.frame-section-end .image-uploader {
  margin-bottom: 0;
}

/* 连接线：起始帧 → 结束帧 */
.frame-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 26px;
  gap: 2px;
}
.connector-line {
  width: 2px;
  height: 8px;
  background: linear-gradient(to bottom, var(--agnes-primary), var(--agnes-primary-hover));
  border-radius: 2px;
}
.connector-arrow {
  font-size: 14px;
  color: var(--agnes-primary);
  font-weight: bold;
}


</style>

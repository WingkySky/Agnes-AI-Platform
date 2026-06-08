<!-- =====================================================
     视频生成视图 VideoView
     模式：
       - 文生视频 (text2video)
       - 图生视频 (image2video)
       - 关键帧动画 (keyframes)
     ===================================================== -->

<template>
  <div class="video-view">
    <h2 class="page-title">🎬 视频生成</h2>
    <p class="page-desc">
      根据文字描述或参考图生成短视频。通常需要 2-5 分钟完成，请耐心等待。</p>

    <el-row :gutter="24">
      <!-- 左侧：参数 -->
      <el-col :xs="24" :md="11">
        <el-card shadow="never">
          <template #header>
          <div class="card-header"><span>生成参数</span></div>
          </template>

          <!-- 模式切换 -->
          <el-tabs v-model="mode">
              <el-tab-pane label="📝 文生视频" name="text2video">
                <span class="tab-sub">仅提示词</span>
              </el-tab-pane>
              <el-tab-pane label="🖼 图生视频" name="image2video">
                <span class="tab-sub">参考图 + 提示词</span>
              </el-tab-pane>
              <el-tab-pane label="🎞 关键帧动画" name="keyframes">
                <span class="tab-sub">多张关键帧 + 提示词</span>
              </el-tab-pane>
          </el-tabs>

          <!-- 单图上传 -->
          <ImageUploader
            v-if="mode === 'image2video'"
            @change="handleImageChange"
            @clear="handleImageClear"
          />

          <!-- 多图上传 -->
          <div v-if="mode === 'keyframes'" class="multi-upload">
            <div class="section-title">上传关键帧</div>
            <ImageUploader
              v-for="(_, idx) in keyframes"
              :key="idx"
              :optional="false"
              @change="(f) => handleKeyframeChange(idx, f)"
              @clear="() => handleKeyframeClear(idx)"
            />
            <el-button plain size="small" @click="addKeyframe">+ 再添加一张关键帧</el-button>
          </div>

          <el-form label-position="top">
            <el-form-item label="提示词">
              <el-input v-model="prompt" type="textarea" :rows="4" placeholder="描述视频内容与动态，例如：一位身穿飘逸长袍的剑客，在雨夜都市穿行，电影镜头感" maxlength="2000" show-word-limit />
            </el-form-item>

            <el-form-item label="负向提示词 (可选)">
              <el-input v-model="negativePrompt" type="textarea" :rows="2" placeholder="描述不希望出现的元素（可选）" />
            </el-form-item>

            <PromptTemplates :templates="VIDEO_TEMPLATES" @select="appendStylePrompt" />

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="总帧数">
                  <el-select v-model="numFrames">
                    <el-option v-for="n in FRAME_OPTIONS" :key="n" :label="n + '帧'" :value="n" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="帧率 (fps)">
                  <el-input-number v-model="frameRate" :min="1" :max="60" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="宽度">
                  <el-input-number v-model="width" :min="512" :max="2048" :step="64" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="高度">
                  <el-input-number v-model="height" :min="512" :max="2048" :step="64" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="16">
              <el-col :span="24">
                <el-form-item label="随机种子 (可选)">
                  <el-input v-model="seed" placeholder="留空自动生成" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-button
              v-if="!runningTask"
              type="primary" size="large"
              class="generate-btn"
              :disabled="!canSubmit"
              @click="startGenerate">
              <el-icon><VideoPlay /></el-icon>
              <span>✨ 生成视频</span>
            </el-button>

            <el-button
              v-else
              type="danger" size="large"
              class="generate-btn"
              @click="cancelTask">
              <el-icon><CircleCloseFilled /></el-icon>
              <span>中止任务</span>
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：结果 -->
      <el-col :xs="24" :md="13">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>生成结果</span>
              <span v-if="videoUrl" class="header-actions">
                <el-button size="small" @click="downloadVideo">
                  <el-icon><Download /></el-icon>
                  下载
                </el-button>
              </span>
            </div>
          </template>

          <!-- 运行中 -->
          <div v-if="runningTask && status !== 'success' && status !== 'failed'" class="result-loading">
            <el-progress
              :percentage="progressPercent"
              :stroke-width="12"
              :color="progressColor" />
            <div class="loading-text">{{ statusText }}</div>
            <div class="loading-sub">已耗时 {{ elapsedSec }}秒 · 每 5 秒查询一次状态</div>
            <div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>
          </div>

          <!-- 成功 -->
          <div v-else-if="videoUrl" class="result-wrap">
            <video :src="videoUrl" controls class="result-video" />
            <div class="result-meta">
              <div class="meta-row">提示词：{{ prompt }}</div>
              <div class="meta-row">分辨率：{{ width }}×{{ height }} · {{ numFrames }}帧 · {{ frameRate }}fps</div>
            </div>
          </div>

          <!-- 失败 -->
          <div v-else-if="status === 'failed'" class="result-failed">
            <el-icon :size="48" color="#ff7b7b"><CircleCloseFilled /></el-icon>
            <div class="failed-text">视频生成失败</div>
            <div class="failed-sub">{{ errorMessage || '请检查 API 或稍后重试' }}</div>
          </div>

          <!-- 空状态 -->
          <div v-else class="empty-state">
            <el-icon :size="48"><VideoCameraFilled /></el-icon>
            <p class="empty-text">点击左侧配置参数，开始创作你的 AI 视频</p>
          </div>
        </el-card>

        <div class="tips-card">
          <div class="tip-title">💡 视频生成提示</div>
          <ul>
            <li>帧数越多，视频越长：9帧 = 约 0.3 秒；121帧 = 约 5 秒；441帧 = 约 18 秒</li>
            <li>建议帧率 24 或 30 fps</li>
            <li>图生视频/关键帧模式下参考图需为公开可访问 URL</li>
            <li>生成过程可随时中止，但已生成部分无法恢复</li>
          </ul>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  VideoPlay, Download, CircleCloseFilled, VideoCameraFilled
} from '@element-plus/icons-vue'
import PromptTemplates from '@/components/PromptTemplates.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import {
  createVideoTask,
  getVideoStatus,
  cancelVideoTask
} from '@/api/videos'

const VIDEO_TEMPLATES = [
  { label: '电影镜头', prompt: '，电影镜头感，缓慢平移，平滑 dolly-in，戏剧性光影' },
  { label: '慢动作', prompt: '，慢动作，细腻细节，优雅节奏' },
  { label: '手持跟拍', prompt: '，手持跟拍，真实感，纪实' },
  { label: '霓虹夜景', prompt: '，霓虹夜景，水面反光，都市感' },
  { label: '航拍', prompt: '，航拍大远景，缓慢扫镜，史诗感' },
  { label: '丝滑过渡', prompt: '，丝滑电影感过渡，电影级调色' }
]

const FRAME_OPTIONS = [9, 33, 49, 81, 121, 161, 241, 441]

// ---------- 状态 ----------
const mode = ref('text2video')
const prompt = ref('')
const negativePrompt = ref('')
const numFrames = ref(121)
const frameRate = ref(24)
const width = ref(1152)
const height = ref(768)
const seed = ref('')
const referenceFile = ref(null)
const keyframes = ref([null]) // keyframes 模式下的多张图

const runningTask = ref(false)
const status = ref('')
const videoUrl = ref('')
const errorMessage = ref('')
const progress = ref(0)
const startTime = ref(0)
const elapsedSec = ref(0)

let pollTimer = null

const canSubmit = computed(() => prompt.value.trim().length > 0)
const statusText = computed(() => {
  if (status.value === 'processing') return 'AI 正在绘制视频中...'
  if (status.value === 'pending') return '排队中...'
  if (status.value === 'success') return '生成完成'
  return '创建任务中...'
})
const progressPercent = computed(() => Math.min(progress.value, 99))
const progressColor = '#6b9cff'

function appendStylePrompt(t) {
  if (!prompt.value.trim().endsWith(t)) {
    prompt.value = prompt.value.trim() + t
  }
}

// ---------- 关键帧管理 ----------
function addKeyframe() {
  if (keyframes.value.length < 6) {
    keyframes.value.push(null)
  } else {
    ElMessage.warning('最多添加 6 张关键帧')
  }
}
function handleImageChange(file) {
  referenceFile.value = file
}
function handleImageClear() {
  referenceFile.value = null
}
function handleKeyframeChange(idx, file) {
  keyframes.value[idx] = file
}
function handleKeyframeClear(idx) {
  keyframes.value[idx] = null
}

// ---------- 开始生成 ----------
async function startGenerate() {
  if (!canSubmit.value) {
    ElMessage.warning('请先填写提示词')
    return
  }
  if (mode.value === 'image2video' && !referenceFile.value) {
    ElMessage.warning('请先上传参考图')
    return
  }

  const params = {
    prompt: prompt.value.trim(),
    negative_prompt: negativePrompt.value.trim() || undefined,
    model: 'agnes-video-v2.0',
    num_frames: numFrames.value,
    frame_rate: frameRate.value,
    width: width.value,
    height: height.value,
    mode: mode.value,
    seed: seed.value ? Number(seed.value) : undefined
  }
  if (mode.value === 'image2video' && referenceFile.value) {
    params.image = referenceFile.value.base64 || referenceFile.value.url
  }
  if (mode.value === 'keyframes') {
    const imgs = keyframes.value.filter(Boolean).map(f => f.base64 || f.url)
    if (imgs.length > 0) params.images = imgs
  }

  runningTask.value = true
  status.value = 'pending'
  videoUrl.value = ''
  errorMessage.value = ''
  progress.value = 0
  startTime.value = Date.now()

  try {
    const task = await createVideoTask(params)
    const taskId = task.task_id

    // 轮询状态
    const doPoll = async () => {
      try {
        const data = await getVideoStatus(taskId)
        status.value = data.status || 'processing'

        if (typeof data.progress !== 'undefined' && data.progress !== null) {
          progress.value = data.progress
        } else {
          // 基于时间估算
          const elapsed = (Date.now() - startTime.value) / 1000
          progress.value = Math.min(Math.floor((elapsed / 180) * 100), 85)
        }
        elapsedSec.value = Math.floor((Date.now() - startTime.value) / 1000)

        if (status.value === 'success') {
          videoUrl.value = data.video_url
          runningTask.value = false
          clearInterval(pollTimer)
          ElMessage.success('视频生成完成！')
          return
        }
        if (status.value === 'failed') {
          errorMessage.value = data.message || '未知错误'
          runningTask.value = false
          clearInterval(pollTimer)
          ElMessage.error('视频生成失败')
          return
        }
        errorMessage.value = data.message || ''
      } catch (e) {
          // 单次轮询失败，继续下一次
        }
      }
    // 启动轮询
    pollTimer = setInterval(doPoll, 5000)
    doPoll()
  } catch (e) {
    runningTask.value = false
    status.value = 'failed'
    errorMessage.value = e.message || '创建任务失败'
  }
}

function cancelTask() {
  if (!runningTask.value) return
  clearInterval(pollTimer)
  runningTask.value = false
  status.value = 'cancelled'
  ElMessage.info('已中止任务')
}

function downloadVideo() {
  if (!videoUrl.value) return
  const a = document.createElement('a')
  a.href = videoUrl.value
  a.download = `agnes-video-${Date.now()}.mp4`
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  ElMessage.success('已开始下载')
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.video-view { color: #e8eef7; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.tab-sub { font-size: 12px; color: #8ba3c9; margin-left: 6px; }
.generate-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  margin-top: 8px;
}
.section-title {
  font-size: 13px;
  color: #a0b4d6;
  margin: 12px 0 10px;
  font-weight: 500;
}

.result-loading {
  padding: 60px 20px;
  text-align: center;
}
.loading-text {
  margin-top: 16px;
  font-size: 16px;
  color: #d5e3f7;
}
.loading-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #8ba3c9;
}
.error-msg {
  margin-top: 16px;
  color: #ff9b9b;
  font-size: 13px;
}
.result-wrap { text-align: center; }
.result-video {
  width: 100%;
  max-height: 500px;
  border-radius: 12px;
  background: #000;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35);
}
.result-meta {
  margin-top: 16px;
  padding: 12px;
  background: rgba(15,24,42,0.4);
  border-radius: 8px;
  text-align: left;
}
.meta-row { font-size: 13px; padding: 4px 0; }

.result-failed {
  padding: 60px 20px;
  text-align: center;
  color: #ff9b9b;
}
.failed-text { margin-top: 16px; font-size: 16px; color: #ffb5b5; }
.failed-sub { font-size: 12px; color: #8ba3c9; }

.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: #6b84aa;
}
.empty-text { margin-top: 16px; font-size: 14px; }

.tips-card {
  margin-top: 16px;
  padding: 16px 20px;
  background: rgba(15, 24, 42, 0.5);
  border: 1px solid rgba(120, 170, 255, 0.15);
  border-radius: 12px;
  font-size: 13px;
  color: #a0b4d6;
}
.tips-title { font-weight: 600; color: #d5e3f7; margin-bottom: 8px; }
.tips-card ul { margin: 0; padding-left: 20px; line-height: 1.8; }
.multi-upload .el-button { margin-top: 8px; }
</style>

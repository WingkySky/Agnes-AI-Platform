<!-- =====================================================
     分镜卡片 ShotCard
     - 展示：序号 / 标题 / 镜头信息 / 帧图 / 视频 / 配音
     - 操作：生成帧图 / 上传帧图 / 生成视频 / 上传视频 / 生成配音 / 上传配音 / 编辑 / 删除 / 多选
     - 绑定角色/道具（标签形式展示，可解绑）
     - 帧图/视频/音频版本切换器（内联 el-dropdown）
     ===================================================== -->

<template>
  <div
    class="shot-card"
    :class="{ selected: selected }"
    @click="$emit('toggle-select', shot.id)"
  >
    <!-- 顶部：序号 + 标题 + 镜头信息 -->
    <div class="shot-header">
      <div class="shot-no">镜 {{ shot.sequence_no }}</div>
      <div class="shot-title-block">
        <div class="shot-title">{{ shot.title || '未命名分镜' }}</div>
        <div class="shot-meta">
          <el-tag v-if="shot.shot_type" size="small" type="info">{{ shotTypeLabel }}</el-tag>
          <el-tag v-if="shot.camera_movement" size="small" type="info">{{ cameraMovementLabel }}</el-tag>
          <span v-if="shot.duration_ms" class="meta-text">{{ durationLabel }}</span>
        </div>
      </div>
    </div>

    <!-- 帧图预览 -->
    <div class="frame-preview">
      <img
        v-if="activeFrameImage?.file_url"
        :src="activeFrameImage.file_url"
        :alt="`分镜 ${shot.sequence_no} 帧图`"
      />
      <img
        v-else-if="activeFrameImage?.thumbnail_url"
        :src="activeFrameImage.thumbnail_url"
        :alt="`分镜 ${shot.sequence_no} 帧图`"
      />
      <div v-else class="preview-placeholder">
        <el-icon :size="32"><Picture /></el-icon>
        <span>暂无帧图</span>
      </div>

      <!-- 生成中遮罩 -->
      <div v-if="generatingFrame || localGeneratingFrame" class="generating-mask">
        <el-icon class="loading-icon" :size="28"><Loading /></el-icon>
        <span>帧图生成中...</span>
      </div>

      <!-- 操作浮层 -->
      <div v-if="projectStore.isEditable && !generatingFrame && !localGeneratingFrame" class="frame-overlay">
        <el-button
          type="primary"
          size="small"
          :icon="MagicStick"
          :loading="localGeneratingFrame"
          @click.stop="onGenerateFrame"
        >生成帧图</el-button>
        <div class="upload-wrapper" @click.stop>
          <el-upload
            :show-file-list="false"
            :before-upload="onUploadFrame"
            accept="image/*"
          >
            <el-button size="small" :icon="Upload" :loading="uploadingFrame">上传</el-button>
          </el-upload>
        </div>
      </div>

      <!-- 帧图版本切换器 -->
      <div
        v-if="shot.frame_images && shot.frame_images.length > 1"
        class="version-switcher"
        @click.stop
      >
        <el-dropdown trigger="click" @command="onSetActiveFrame">
          <el-button link size="small" type="primary">
            v{{ activeFrameImage?.version || '-' }}
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="fi in shot.frame_images"
                :key="fi.id"
                :command="fi.id"
                :disabled="fi.is_active"
              >
                v{{ fi.version }}
                <el-tag v-if="fi.is_active" type="success" size="small">采用</el-tag>
                <el-tag v-if="fi.is_manual" type="warning" size="small">手动</el-tag>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 视频预览 -->
    <div class="video-preview">
      <template v-if="activeVideo?.file_url">
        <video
          :src="activeVideo.file_url"
          :poster="activeFrameImage?.file_url || undefined"
          controls
          preload="metadata"
          class="video-player"
        />
        <!-- 视频版本切换器 -->
        <div
          v-if="shot.videos && shot.videos.length > 1"
          class="video-version-switcher"
          @click.stop
        >
          <el-dropdown trigger="click" @command="onSetActiveVideo">
            <el-button link size="small" type="primary">
              v{{ activeVideo?.version || '-' }}
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="vid in shot.videos"
                  :key="vid.id"
                  :command="vid.id"
                  :disabled="vid.is_active"
                >
                  v{{ vid.version }}
                  <el-tag v-if="vid.is_active" type="success" size="small">采用</el-tag>
                  <el-tag v-if="vid.is_manual" type="warning" size="small">手动</el-tag>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
      <template v-else>
        <div class="video-placeholder">
          <el-icon :size="32"><VideoPlay /></el-icon>
          <span v-if="generatingVideo || localGeneratingVideo" class="generating-text">
            <el-icon class="loading-icon"><Loading /></el-icon>
            视频生成中...
          </span>
          <span v-else>暂无视频</span>
          <el-button
            v-if="projectStore.isEditable && !generatingVideo && !localGeneratingVideo && activeFrameImage"
            type="primary"
            size="small"
            :icon="VideoPlay"
            :loading="localGeneratingVideo"
            @click.stop="onGenerateVideo"
          >生成视频</el-button>
          <div class="upload-wrapper" @click.stop>
            <el-upload
              v-if="projectStore.isEditable && !generatingVideo && !localGeneratingVideo"
              :show-file-list="false"
              :before-upload="onUploadVideo"
              accept="video/*"
            >
              <el-button size="small" :icon="Upload" :loading="uploadingVideo">上传视频</el-button>
            </el-upload>
          </div>
        </div>
      </template>
    </div>

    <!-- 音频预览（配音） -->
    <div class="audio-preview">
      <template v-if="activeAudio?.file_url">
        <div class="audio-row">
          <el-icon class="audio-icon"><Microphone /></el-icon>
          <audio
            :src="activeAudio.file_url"
            controls
            preload="metadata"
            class="audio-player"
          />
          <!-- 音频版本切换器 -->
          <div
            v-if="shot.audios && shot.audios.length > 1"
            class="audio-version-switcher"
            @click.stop
          >
            <el-dropdown trigger="click" @command="onSetActiveAudio">
              <el-button link size="small" type="primary">
                v{{ activeAudio?.version || '-' }}
                <el-icon><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="aud in shot.audios"
                    :key="aud.id"
                    :command="aud.id"
                    :disabled="aud.is_active"
                  >
                    v{{ aud.version }}
                    <el-tag v-if="aud.is_active" type="success" size="small">采用</el-tag>
                    <el-tag v-if="aud.is_manual" type="warning" size="small">手动</el-tag>
                    <el-tag v-if="aud.voice_name" type="info" size="small">{{ aud.voice_name }}</el-tag>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <el-button
            v-if="projectStore.isEditable"
            link
            size="small"
            type="danger"
            :icon="Delete"
            @click.stop="onDeleteAudio(activeAudio.id)"
          >删除</el-button>
        </div>
      </template>
      <template v-else>
        <div class="audio-placeholder">
          <el-icon :size="20"><Microphone /></el-icon>
          <span v-if="localGeneratingAudio" class="generating-text">
            <el-icon class="loading-icon"><Loading /></el-icon>
            配音生成中...
          </span>
          <span v-else>暂无配音</span>
          <el-button
            v-if="projectStore.isEditable && !localGeneratingAudio"
            type="primary"
            size="small"
            :icon="Microphone"
            :loading="localGeneratingAudio"
            :disabled="!shot.dialogue"
            @click.stop="onGenerateAudio"
          >生成配音</el-button>
          <div class="upload-wrapper" @click.stop>
            <el-upload
              v-if="projectStore.isEditable && !localGeneratingAudio"
              :show-file-list="false"
              :before-upload="onUploadAudio"
              accept="audio/*"
            >
              <el-button size="small" :icon="Upload" :loading="uploadingAudio">上传</el-button>
            </el-upload>
          </div>
        </div>
      </template>
    </div>

    <!-- 对话台词 -->
    <div v-if="shot.dialogue" class="shot-section">
      <div class="section-label">台词</div>
      <div class="section-content">{{ shot.dialogue }}</div>
    </div>

    <!-- 画面描述 -->
    <div v-if="shot.visual_desc" class="shot-section">
      <div class="section-label">画面</div>
      <div class="section-content">{{ shot.visual_desc }}</div>
    </div>

    <!-- 提示词 -->
    <div v-if="shot.image_prompt" class="shot-section">
      <div class="section-label">
        提示词
        <el-button
          v-if="projectStore.isEditable"
          link
          size="small"
          :icon="Refresh"
          :loading="generatingPrompt"
          @click.stop="onGeneratePrompt"
        >重生成</el-button>
      </div>
      <div class="section-content prompt">{{ shot.image_prompt }}</div>
    </div>

    <!-- 关联实体 -->
    <div v-if="shot.characters?.length || shot.props?.length" class="shot-section">
      <div class="section-label">关联</div>
      <div class="section-content">
        <el-tag
          v-for="char in shot.characters"
          :key="`char-${char.id}`"
          size="small"
          closable
          @close="onUnbindCharacter(char)"
          @click.stop
        >{{ char.name }}</el-tag>
        <el-tag
          v-for="prop in shot.props"
          :key="`prop-${prop.id}`"
          size="small"
          type="warning"
          closable
          @close="onUnbindProp(prop)"
          @click.stop
        >{{ prop.name }}</el-tag>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="card-actions" @click.stop>
      <el-button
        v-if="projectStore.isEditable"
        link
        size="small"
        :icon="Edit"
        @click="$emit('edit', shot)"
      >编辑</el-button>
      <el-button
        v-if="projectStore.isEditable"
        link
        size="small"
        :icon="Delete"
        @click="onDelete"
      >删除</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Picture, Loading, MagicStick, Upload, Edit, Delete, Refresh, VideoPlay, ArrowDown, Microphone,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { ProjectShot } from '@/types/project'

const props = defineProps<{
  shot: ProjectShot
  selected?: boolean
  /** 是否在生成帧图（外部传入避免重复触发） */
  generatingFrame?: boolean
  /** 是否在生成视频 */
  generatingVideo?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-select', id: number): void
  (e: 'edit', shot: ProjectShot): void
  (e: 'refresh'): void
}>()

const projectStore = useProjectStore()

// ---------- 内部状态 ----------
const generatingPrompt = ref(false)
const localGeneratingFrame = ref(false)
const localGeneratingVideo = ref(false)
const uploadingFrame = ref(false)
const uploadingVideo = ref(false)
const localGeneratingAudio = ref(false)
const uploadingAudio = ref(false)

// ---------- 计算 ----------
const activeFrameImage = computed(() => props.shot.active_frame_image)
const activeVideo = computed(() => props.shot.active_video)
const activeAudio = computed(() => props.shot.active_audio)

const shotTypeLabel = computed(() => {
  const map: Record<string, string> = {
    wide: '远景', full: '全景', medium: '中景', close_up: '近景', extreme_close_up: '特写',
  }
  return map[props.shot.shot_type || ''] || props.shot.shot_type
})

const cameraMovementLabel = computed(() => {
  const map: Record<string, string> = {
    static: '固定', pan: '摇', tilt: '俯仰', dolly: '推拉', tracking: '跟拍', zoom: '变焦',
  }
  return map[props.shot.camera_movement || ''] || props.shot.camera_movement
})

const durationLabel = computed(() => {
  const ms = props.shot.duration_ms || 0
  const s = ms / 1000
  return s >= 1 ? `${s.toFixed(1)}s` : `${ms}ms`
})

// ---------- 帧图操作 ----------
async function onGenerateFrame() {
  try {
    await ElMessageBox.confirm(
      `将调用 AI 为分镜 ${props.shot.sequence_no} 生成帧图，是否继续？`,
      '生成帧图',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  localGeneratingFrame.value = true
  try {
    await projectStore.generateFrameImage(props.shot.id, {})
    ElMessage.success('帧图已生成')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    localGeneratingFrame.value = false
  }
}

async function onUploadFrame(file: File): Promise<boolean> {
  uploadingFrame.value = true
  try {
    await projectStore.uploadFrameImage(props.shot.id, file)
    ElMessage.success('帧图已上传')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploadingFrame.value = false
  }
  return false
}

// ---------- 视频操作 ----------
async function onGenerateVideo() {
  try {
    await ElMessageBox.confirm(
      `将基于当前帧图为分镜 ${props.shot.sequence_no} 生成视频，是否继续？`,
      '生成视频',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  localGeneratingVideo.value = true
  try {
    // generateVideo 立即返回（任务已入队列，后端按速率限制串行提交）
    // 实际生成进度通过右下角任务队列面板查看
    await projectStore.generateVideo(props.shot.id, {})
    ElMessage.success('视频生成任务已加入队列，请在右下角任务面板查看进度')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    localGeneratingVideo.value = false
  }
}

async function onUploadVideo(file: File): Promise<boolean> {
  uploadingVideo.value = true
  try {
    await projectStore.uploadVideo(props.shot.id, file)
    ElMessage.success('视频已上传')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploadingVideo.value = false
  }
  return false
}

// ---------- 提示词生成 ----------
async function onGeneratePrompt() {
  generatingPrompt.value = true
  try {
    await projectStore.generateFramePrompt(props.shot.id)
    ElMessage.success('提示词已重新生成')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generatingPrompt.value = false
  }
}

// ---------- 版本切换 ----------
async function onSetActiveFrame(frameImageId: number) {
  try {
    await projectStore.setActiveFrameImage(props.shot.id, frameImageId)
    ElMessage.success('已切换帧图版本')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '切换失败')
  }
}

async function onSetActiveVideo(videoId: number) {
  try {
    await projectStore.setActiveVideo(props.shot.id, videoId)
    ElMessage.success('已切换视频版本')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '切换失败')
  }
}

// ---------- 音频操作 ----------
async function onGenerateAudio() {
  if (!props.shot.dialogue) {
    ElMessage.warning('该分镜没有台词，无法生成配音')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将基于台词生成分镜 ${props.shot.sequence_no} 的配音，是否继续？`,
      '生成配音',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  localGeneratingAudio.value = true
  try {
    // 不指定 voice_id，由后端按角色绑定/默认音色选取
    await projectStore.generateTTS(props.shot.id, {})
    ElMessage.success('配音已生成')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    localGeneratingAudio.value = false
  }
}

async function onUploadAudio(file: File): Promise<boolean> {
  uploadingAudio.value = true
  try {
    await projectStore.uploadAudio(props.shot.id, file)
    ElMessage.success('音频已上传')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploadingAudio.value = false
  }
  return false
}

async function onSetActiveAudio(audioId: number) {
  try {
    await projectStore.setActiveAudio(props.shot.id, audioId)
    ElMessage.success('已切换音频版本')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '切换失败')
  }
}

async function onDeleteAudio(audioId: number) {
  try {
    await ElMessageBox.confirm('确定删除该音频版本？此操作不可撤销。', '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch (_) { return }

  try {
    await projectStore.deleteAudio(props.shot.id, audioId)
    ElMessage.success('音频已删除')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// ---------- 解绑 ----------
async function onUnbindCharacter(char: any) {
  try {
    await projectStore.unbindCharacter(props.shot.id, char.id)
    ElMessage.success(`已解绑角色「${char.name}」`)
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '解绑失败')
  }
}

async function onUnbindProp(prop: any) {
  try {
    await projectStore.unbindProp(props.shot.id, prop.id)
    ElMessage.success(`已解绑道具「${prop.name}」`)
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '解绑失败')
  }
}

// ---------- 删除 ----------
async function onDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除分镜 ${props.shot.sequence_no}？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.deleteShot(props.shot.id)
    ElMessage.success('分镜已删除')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}
</script>

<style scoped>
.shot-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.shot-card:hover { border-color: var(--el-color-primary); }
.shot-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}

.shot-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.shot-no {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  padding: 2px 8px;
  flex-shrink: 0;
}

.shot-title-block {
  flex: 1;
  min-width: 0;
}

.shot-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}

.shot-meta {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.meta-text { padding: 2px 0; }

.frame-preview {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--el-fill-color);
  border-radius: 6px;
  overflow: hidden;
}
.frame-preview img {
  width: 100%; height: 100%; object-fit: cover;
}

.preview-placeholder {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 6px; color: var(--el-text-color-secondary);
  font-size: 12px;
}

.generating-mask {
  position: absolute; inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 6px; color: #fff; font-size: 13px;
}

.loading-icon {
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.frame-overlay {
  position: absolute;
  bottom: 6px; left: 6px; right: 6px;
  display: flex; gap: 6px;
  opacity: 0; transition: opacity 0.2s;
}
.shot-card:hover .frame-overlay { opacity: 1; }

.upload-wrapper {
  display: inline-flex;
}

.version-switcher {
  position: absolute;
  top: 6px;
  right: 6px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 0 4px;
}

.video-preview {
  background: var(--el-fill-color);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}
.video-player {
  width: 100%;
  display: block;
  max-height: 220px;
}
.video-version-switcher {
  position: absolute;
  top: 6px;
  right: 6px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 0 4px;
}
.video-placeholder {
  padding: 16px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 8px; color: var(--el-text-color-secondary);
  font-size: 12px;
}
.generating-text {
  display: inline-flex; align-items: center; gap: 4px;
  color: var(--el-color-primary);
}

/* ---------- 音频预览 ---------- */
.audio-preview {
  background: var(--el-fill-color);
  border-radius: 6px;
  padding: 8px 10px;
  position: relative;
}
.audio-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.audio-icon {
  color: var(--el-color-success);
  flex-shrink: 0;
}
.audio-player {
  flex: 1;
  height: 32px;
  min-width: 0;
}
.audio-version-switcher {
  flex-shrink: 0;
}
.audio-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.shot-section {
  font-size: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 8px;
}
.section-label {
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-content {
  line-height: 1.5;
  word-wrap: break-word;
}
.section-content.prompt {
  font-family: 'Menlo', 'Monaco', monospace;
  background: var(--el-fill-color-light);
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.section-content :deep(.el-tag) {
  margin-right: 4px;
  margin-bottom: 4px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 8px;
}
</style>

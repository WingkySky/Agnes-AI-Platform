<!-- =====================================================
     时间线 Tab 主容器 TimelineTab
     - 组合工具栏 + 编辑器 + 属性面板 + 三个对话框
     - 拖拽/裁剪实时维护本地 drafts，结束后批量保存到 store
     - 提供初始化、生成字幕、字幕样式、BGM、合成入口
     ===================================================== -->

<template>
  <div class="timeline-tab">
    <!-- 顶部工具栏 -->
    <TimelineToolbar
      :editable="projectStore.isEditable"
      :has-timeline="hasTimeline"
      :total-duration="totalDuration"
      :whisper-available="projectStore.whisperAvailable"
      :current-bgm="currentBgm"
      :loading="initLoading"
      :subtitle-loading="subtitleLoading"
      :whisper-loading="whisperLoading"
      :merge-loading="projectStore.mergeLoading"
      :merge-progress="projectStore.mergeProgress"
      @init="onInit"
      @generate-subtitles="onGenerateSubtitles"
      @open-subtitle-style="subtitleStyleVisible = true"
      @open-bgm-picker="bgmPickerVisible = true"
      @merge-advanced="onMergeAdvanced"
    />

    <!-- 主体区：编辑器 + 属性面板 -->
    <div class="timeline-main">
      <div class="editor-wrap">
        <el-empty
          v-if="!hasTimeline && !projectStore.timelineLoading"
          description="暂无时间线数据，请先点击「初始化时间线」"
        >
          <el-button type="primary" :icon="Refresh" @click="onInit">初始化时间线</el-button>
        </el-empty>

        <el-skeleton
          v-else-if="projectStore.timelineLoading && !hasTimeline"
          :rows="6"
          animated
        />

        <TimelineEditor
          v-else
          :clips="draftClips"
          :total-duration="totalDuration"
          :selected-clip-id="selectedClipId"
          :editable="projectStore.isEditable"
          @select-clip="onSelectClip"
          @deselect="selectedClipId = null"
          @clip-drag="onClipDrag"
          @clip-trim="onClipTrim"
          @clip-updated="onClipUpdated"
          @play="onPlay"
          @seek="onSeek"
        />
      </div>

      <ClipPropertyPanel
        :clip="selectedClip"
        :editable="projectStore.isEditable"
        @save="onSaveClip"
        @delete="onDeleteClip"
      />
    </div>

    <!-- 三个对话框 -->
    <SubtitleStyleDialog
      v-model:visible="subtitleStyleVisible"
      :style="projectStore.subtitleStyle"
    />
    <BgmPickerDialog
      v-model:visible="bgmPickerVisible"
      :default-bgm-id="currentBgmId"
      @confirm="onBgmConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type {
  TimelineClip,
  TransitionType,
  BGMItem,
} from '@/types/project'
import TimelineToolbar from './TimelineToolbar.vue'
import TimelineEditor from './TimelineEditor.vue'
import ClipPropertyPanel from './ClipPropertyPanel.vue'
import SubtitleStyleDialog from './SubtitleStyleDialog.vue'
import BgmPickerDialog from './BgmPickerDialog.vue'

const projectStore = useProjectStore()

// ---------- 本地状态 ----------
const initLoading = ref(false)
const subtitleLoading = ref(false)
const whisperLoading = ref(false)
const subtitleStyleVisible = ref(false)
const bgmPickerVisible = ref(false)

const selectedClipId = ref<number | null>(null)

// 片段草稿（拖拽/裁剪过程实时修改，结束后通过 store 持久化）
const draftClips = ref<TimelineClip[]>([])

// BGM 选中状态
const currentBgmId = ref<string | null>(null)
const currentBgm = ref<BGMItem | null>(null)

// ---------- 计算 ----------
const hasTimeline = computed(() => (projectStore.timelineData?.clips?.length ?? 0) > 0)

const totalDuration = computed(() => projectStore.timelineData?.total_duration ?? 0)

const selectedClip = computed(() =>
  draftClips.value.find((c) => c.id === selectedClipId.value) ?? null,
)

// store.timelineData.clips 变化时同步到本地 drafts
watch(
  () => projectStore.timelineData?.clips,
  (clips) => {
    draftClips.value = clips ? clips.map((c) => ({ ...c })) : []
  },
  { immediate: true },
)

// ---------- 初始化 ----------
onMounted(async () => {
  if (!projectStore.currentProjectId) return
  // 首次进入时拉取时间线数据 + Whisper 可用性
  await Promise.all([
    projectStore.fetchTimelineData(),
    projectStore.fetchWhisperAvailable(),
  ])
})

// ---------- 工具栏事件 ----------
async function onInit() {
  try {
    await ElMessageBox.confirm(
      '初始化将根据当前分镜的活跃视频/音频/字幕重新生成时间线，已有手动调整可能被覆盖，是否继续？',
      '初始化时间线',
      { type: 'warning', confirmButtonText: '初始化', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  initLoading.value = true
  try {
    await projectStore.initTimeline()
    ElMessage.success('时间线已初始化')
  } catch (e: any) {
    ElMessage.error(e?.message || '初始化失败')
  } finally {
    initLoading.value = false
  }
}

async function onGenerateSubtitles(mode: 'llm' | 'whisper') {
  const loading = mode === 'whisper' ? whisperLoading : subtitleLoading
  loading.value = true
  try {
    const result = mode === 'whisper'
      ? await projectStore.generateSubtitlesWithWhisper({})
      : await projectStore.generateSubtitles({})
    ElMessage.success(`已生成 ${result.count} 条字幕（${result.mode} 模式）`)
    // 重新拉取时间线以反映字幕片段
    await projectStore.fetchTimelineData()
  } catch (e: any) {
    ElMessage.error(e?.message || '生成字幕失败')
  } finally {
    loading.value = false
  }
}

async function onMergeAdvanced() {
  try {
    await ElMessageBox.confirm(
      '将基于当前时间线进行多轨合成（视频 + 音频 + 字幕 + BGM），是否继续？',
      '合成视频',
      { type: 'info', confirmButtonText: '开始合成', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.mergeProjectAdvanced({
      with_audio: true,
      with_subtitle: true,
      with_bgm: !!currentBgmId.value,
      bgm_id: currentBgmId.value || undefined,
      use_timeline: true,
    })
    ElMessage.success('合成任务已提交，请在合成状态中查看进度')
  } catch (e: any) {
    ElMessage.error(e?.message || '合成失败')
  }
}

function onBgmConfirm(bgmId: string | null, bgm: BGMItem | null) {
  currentBgmId.value = bgmId
  currentBgm.value = bgm
  if (bgmId) {
    ElMessage.success(`已选择 BGM：${bgm?.name || bgmId}`)
  } else {
    ElMessage.info('已清除 BGM 选择')
  }
}

// ---------- 编辑器事件 ----------
function onSelectClip(clipId: number) {
  selectedClipId.value = clipId
}

function onClipDrag(clipId: number, deltaSeconds: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return
  clip.start_time = Math.max(0, clip.start_time + deltaSeconds)
}

function onClipTrim(clipId: number, side: 'left' | 'right', deltaSeconds: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return
  if (side === 'left') {
    // 左侧裁剪：trim_start 增加，duration 减少，start_time 增加
    const newTrim = Math.max(0, clip.trim_start + deltaSeconds)
    const newDuration = Math.max(0.1, clip.duration - deltaSeconds)
    clip.trim_start = newTrim
    clip.duration = newDuration
    clip.start_time = Math.max(0, clip.start_time + deltaSeconds)
  } else {
    // 右侧裁剪：duration 调整
    clip.duration = Math.max(0.1, clip.duration + deltaSeconds)
  }
}

async function onClipUpdated(clipId: number) {
  const clip = draftClips.value.find((c) => c.id === clipId)
  if (!clip) return
  try {
    await projectStore.updateTimelineClip(clipId, {
      start_time: clip.start_time,
      duration: clip.duration,
      trim_start: clip.trim_start,
      trim_end: clip.trim_end ?? undefined,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '保存片段失败')
    // 失败时回滚到 store 数据
    await projectStore.fetchTimelineData()
  }
}

async function onSaveClip(clipId: number, data: Partial<TimelineClip>) {
  try {
    // 构造符合 TimelineClipUpdateRequest 形状的 payload（trim_end 不允许 null）
    const payload = {
      start_time: data.start_time,
      duration: data.duration,
      trim_start: data.trim_start,
      trim_end: data.trim_end ?? undefined,
      transition_type: data.transition_type,
      transition_duration: data.transition_duration,
      subtitle_text: data.subtitle_text ?? undefined,
    }
    await projectStore.updateTimelineClip(clipId, payload)
    ElMessage.success('片段属性已保存')
    // 同步本地 draft
    const idx = draftClips.value.findIndex((c) => c.id === clipId)
    if (idx >= 0) {
      draftClips.value[idx] = { ...draftClips.value[idx], ...data } as TimelineClip
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

async function onDeleteClip(clipId: number) {
  try {
    await ElMessageBox.confirm('确定删除该片段？此操作不可撤销。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch (_) { return }

  try {
    await projectStore.deleteTimelineClip(clipId)
    ElMessage.success('片段已删除')
    if (selectedClipId.value === clipId) selectedClipId.value = null
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

function onPlay() {
  ElMessage.info('播放预览需要后端合成支持')
}

function onSeek(_t: number) {
  // 当前仅本地维护播放头位置，不与后端交互
}
</script>

<style scoped>
.timeline-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.timeline-main {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.editor-wrap {
  flex: 1;
  min-width: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
</style>

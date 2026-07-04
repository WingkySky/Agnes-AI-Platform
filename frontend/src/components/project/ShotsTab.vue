<!-- =====================================================
     分镜 Tab ShotsTab
     - 展示分镜卡片网格（ShotCard）
     - 多选批量生成帧图/视频
     - 新建分镜（手动）/ 从剧本拆分（在剧本 Tab 已有入口）
     - 编辑分镜（弹出 ShotEditDialog 内联）
     - 重排分镜（拖拽）
     ===================================================== -->

<template>
  <div class="shots-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Plus" @click="onCreate">新建分镜</el-button>
        <el-button
          v-if="selectedIds.length > 0"
          :icon="MagicStick"
          :loading="batchGenerating"
          @click="onBatchGenerateFrames"
        >
          批量生成帧图 ({{ selectedIds.length }})
        </el-button>
        <el-button
          v-if="selectedIds.length > 0"
          :icon="VideoPlay"
          :loading="batchGeneratingVideo"
          @click="onBatchGenerateVideos"
        >
          批量生成视频 ({{ selectedIds.length }})
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-tooltip content="按 sequence_no 重新排序" placement="top">
          <el-button :icon="Sort" link @click="onReorder">重排</el-button>
        </el-tooltip>
        <el-button :icon="Refresh" link @click="onRefresh">刷新</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && shots.length === 0" class="empty-state">
      <el-icon :size="48"><Film /></el-icon>
      <p class="empty-text">还没有分镜</p>
      <p class="empty-hint">可点击「新建分镜」手动添加，或在「剧本」Tab 中选择剧本后点击「按此剧本拆分分镜」</p>
    </div>

    <!-- 分镜卡片网格 -->
    <div v-else class="card-grid">
      <ShotCard
        v-for="shot in sortedShots"
        :key="shot.id"
        :shot="shot"
        :selected="selectedIds.includes(shot.id)"
        :generating-frame="generatingFrameIds.includes(shot.id)"
        :generating-video="generatingVideoIds.includes(shot.id)"
        @toggle-select="onToggleSelect"
        @edit="onEdit"
        @refresh="onRefresh"
      />
    </div>

    <!-- 编辑/新建分镜对话框 -->
    <el-dialog
      v-model="editVisible"
      :title="editingShot ? '编辑分镜' : '新建分镜'"
      width="640px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form :model="editForm" label-position="top">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" placeholder="分镜标题（可选）" />
        </el-form-item>
        <el-form-item label="镜头类型">
          <el-select v-model="editForm.shot_type" placeholder="选择镜头类型" clearable style="width: 100%">
            <el-option label="远景" value="wide" />
            <el-option label="全景" value="full" />
            <el-option label="中景" value="medium" />
            <el-option label="近景" value="close_up" />
            <el-option label="特写" value="extreme_close_up" />
          </el-select>
        </el-form-item>
        <el-form-item label="运镜">
          <el-select v-model="editForm.camera_movement" placeholder="选择运镜方式" clearable style="width: 100%">
            <el-option label="固定" value="static" />
            <el-option label="摇" value="pan" />
            <el-option label="俯仰" value="tilt" />
            <el-option label="推拉" value="dolly" />
            <el-option label="跟拍" value="tracking" />
            <el-option label="变焦" value="zoom" />
          </el-select>
        </el-form-item>
        <el-form-item label="时长（毫秒）">
          <el-input-number v-model="editForm.duration_ms" :min="0" :step="500" />
        </el-form-item>
        <el-form-item label="台词">
          <el-input v-model="editForm.dialogue" type="textarea" :rows="2" placeholder="本镜的对话或旁白" />
        </el-form-item>
        <el-form-item label="画面描述">
          <el-input v-model="editForm.visual_desc" type="textarea" :rows="3" placeholder="画面中发生的内容" />
        </el-form-item>
        <el-form-item label="氛围">
          <el-input v-model="editForm.atmosphere" placeholder="本镜的氛围，如：紧张 / 温馨" />
        </el-form-item>
        <el-form-item label="画面提示词">
          <el-input
            v-model="editForm.image_prompt"
            type="textarea"
            :rows="4"
            placeholder="用于 AI 生成帧图的提示词（留空可在卡片内点「重生成」）"
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
import { Plus, Refresh, MagicStick, VideoPlay, Film, Sort } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import ShotCard from './ShotCard.vue'
import type { ProjectShot, ShotCreateRequest, ShotUpdateRequest } from '@/types/project'

const projectStore = useProjectStore()

const loading = ref(false)
const sortedShots = computed(() => projectStore.sortedShots)
const shots = computed(() => projectStore.shots)

// 选中状态
const selectedIds = ref<number[]>([])
function onToggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

// 生成中状态
const generatingFrameIds = ref<number[]>([])
const generatingVideoIds = ref<number[]>([])
const batchGenerating = ref(false)
const batchGeneratingVideo = ref(false)

// 编辑/新建
const editVisible = ref(false)
const editingShot = ref<ProjectShot | null>(null)
const saving = ref(false)
const editForm = ref<any>({
  title: '',
  shot_type: '',
  camera_movement: '',
  duration_ms: 0,
  dialogue: '',
  visual_desc: '',
  atmosphere: '',
  image_prompt: '',
})

function onCreate() {
  editingShot.value = null
  editForm.value = {
    title: '',
    shot_type: '',
    camera_movement: '',
    duration_ms: 0,
    dialogue: '',
    visual_desc: '',
    atmosphere: '',
    image_prompt: '',
  }
  editVisible.value = true
}

function onEdit(shot: ProjectShot) {
  editingShot.value = shot
  editForm.value = {
    title: shot.title || '',
    shot_type: shot.shot_type || '',
    camera_movement: shot.camera_movement || '',
    duration_ms: shot.duration_ms || 0,
    dialogue: shot.dialogue || '',
    visual_desc: shot.visual_desc || '',
    atmosphere: shot.atmosphere || '',
    image_prompt: shot.image_prompt || '',
  }
  editVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    const data: any = {}
    if (editForm.value.title) data.title = editForm.value.title
    if (editForm.value.shot_type) data.shot_type = editForm.value.shot_type
    if (editForm.value.camera_movement) data.camera_movement = editForm.value.camera_movement
    if (editForm.value.duration_ms) data.duration_ms = editForm.value.duration_ms
    if (editForm.value.dialogue) data.dialogue = editForm.value.dialogue
    if (editForm.value.visual_desc) data.visual_desc = editForm.value.visual_desc
    if (editForm.value.atmosphere) data.atmosphere = editForm.value.atmosphere
    if (editForm.value.image_prompt) data.image_prompt = editForm.value.image_prompt

    if (editingShot.value) {
      await projectStore.updateShot(editingShot.value.id, data as ShotUpdateRequest)
      ElMessage.success('分镜已更新')
    } else {
      await projectStore.createShot(data as ShotCreateRequest)
      ElMessage.success('分镜已创建')
    }
    editVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// 批量生成帧图
async function onBatchGenerateFrames() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `将为选中的 ${selectedIds.value.length} 个分镜批量生成帧图，是否继续？`,
      '批量生成帧图',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  batchGenerating.value = true
  generatingFrameIds.value.push(...selectedIds.value)
  try {
    await projectStore.batchGenerateFrameImages({ shot_ids: selectedIds.value })
    ElMessage.success('批量生成任务已启动')
  } catch (e: any) {
    ElMessage.error(e?.message || '批量生成失败')
  } finally {
    batchGenerating.value = false
    setTimeout(() => { generatingFrameIds.value = [] }, 8000)
  }
}

// 批量生成视频
async function onBatchGenerateVideos() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `将为选中的 ${selectedIds.value.length} 个分镜批量生成视频，是否继续？\n注意：仅会为已有帧图的分镜生成视频。`,
      '批量生成视频',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  batchGeneratingVideo.value = true
  generatingVideoIds.value.push(...selectedIds.value)
  try {
    await Promise.all(
      selectedIds.value.map(id =>
        projectStore.generateVideo(id, {}).catch(() => {/* 忽略单个失败 */}),
      ),
    )
    ElMessage.success('批量生成任务已启动')
  } catch (e: any) {
    ElMessage.error(e?.message || '批量生成失败')
  } finally {
    batchGeneratingVideo.value = false
    setTimeout(() => { generatingVideoIds.value = [] }, 8000)
  }
}

// 重排
async function onReorder() {
  const ids = sortedShots.value.map(s => s.id)
  try {
    await projectStore.reorderShots({ shot_ids: ids })
    ElMessage.success('已按序号重排')
  } catch (e: any) {
    ElMessage.error(e?.message || '重排失败')
  }
}

function onRefresh() {
  loading.value = true
  projectStore.fetchShots().finally(() => {
    loading.value = false
  })
}

onMounted(() => {
  if (shots.value.length === 0) onRefresh()
})
</script>

<style scoped>
.shots-tab { padding: 4px 0; }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.toolbar-left { display: flex; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; }

.empty-state {
  text-align: center; padding: 60px 0; color: var(--el-text-color-secondary);
}
.empty-text { margin-top: 12px; font-size: 13px; }
.empty-hint { margin-top: 4px; font-size: 12px; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
</style>

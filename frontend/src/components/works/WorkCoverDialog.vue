<!-- =====================================================
     作品封面更换弹窗（四来源收拢）：本作品素材图 / 成片选帧 / 剪辑工程封面 / 上传
     统一确认走 PATCH /api/works/{id} {cover_url}；零新增后端
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('works.coverDialogTitle')" width="640px" @open="onOpen">
    <el-segmented
      class="cover-tabs"
      size="small"
      :model-value="tab"
      :options="tabOptions"
      @change="(v: unknown) => { if (typeof v === 'string') tab = v as TabKey }"
    />

    <!-- ① 本作品素材图（范围可切全部我的素材） -->
    <div v-if="tab === 'assets'">
      <el-segmented
        class="scope-tabs"
        size="small"
        :model-value="assetScope"
        :options="[
          { label: t('works.coverScopeWork'), value: 'work' },
          { label: t('works.coverScopeAll'), value: 'all' },
        ]"
        @change="switchAssetScope"
      />
    </div>
    <div v-if="tab === 'assets'" v-loading="assetsLoading" class="pick-grid">
      <button
        v-for="a in assetImages"
        :key="a.id"
        type="button"
        class="pick-card"
        :class="{ active: selectedUrl === a.url }"
        @click="selectedUrl = a.url"
      >
        <img :src="a.url" loading="lazy" alt="">
      </button>
      <div v-if="!assetsLoading && assetImages.length === 0" class="pick-empty">{{ t('works.coverNoAssets') }}</div>
    </div>

    <!-- ② 成片选帧 -->
    <div v-else-if="tab === 'final'">
      <div v-if="finalProjects.length > 0" class="final-picker">
        <el-select v-model="finalUid" size="small" :placeholder="t('works.coverPickProject')" @change="onFinalChange">
          <el-option
            v-for="p in finalProjects"
            :key="p.uid"
            :label="p.title"
            :value="p.uid"
          />
        </el-select>
        <template v-if="finalUid">
          <div class="final-preview">
            <img v-if="frameSrc" :src="frameSrc" alt="">
            <div v-else class="pick-empty">{{ t('works.coverFrameLoading') }}</div>
          </div>
          <el-slider
            v-model="frameT"
            :min="0"
            :max="frameDuration || 1"
            :step="0.1"
            @change="grabFinalFrame"
          />
        </template>
      </div>
      <div v-else class="pick-empty">{{ t('works.coverNoFinals') }}</div>
    </div>

    <!-- ③ 剪辑工程封面 -->
    <div v-else-if="tab === 'project'" class="pick-grid">
      <button
        v-for="p in coveredProjects"
        :key="p.uid"
        type="button"
        class="pick-card"
        :class="{ active: selectedUrl === p.cover_url }"
        @click="selectedUrl = p.cover_url!"
      >
        <img :src="p.cover_url || ''" loading="lazy" alt="">
      </button>
      <div v-if="coveredProjects.length === 0" class="pick-empty">{{ t('works.coverNoProjectCovers') }}</div>
    </div>

    <!-- ④ 上传 -->
    <div v-else class="upload-row">
      <el-button :loading="uploading" @click="fileInput?.click()">{{ t('works.coverUploadNew') }}</el-button>
      <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="onPickFile">
      <span v-if="selectedUrl && tab === 'upload'" class="upload-done">{{ t('works.coverUploadReady') }}</span>
    </div>

    <template #footer>
      <el-button size="small" @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button
        size="small"
        type="primary"
        :loading="saving"
        :disabled="!selectedUrl && !frameSrc"
        @click="save"
      >{{ t('common.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useI18n } from '@/i18n'
import { uploadWorkCover, updateWork, type WorkItem } from '@/api/works'
import { listAssets, updateAsset } from '@/api/assets'
import { listEditorProjects, type EditingProjectBrief } from '@/api/editor'
import { createVideoSink, probeDuration } from '@/lib/editor-media'

const visible = defineModel<boolean>({ default: false })
const props = defineProps<{ work: WorkItem }>()
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()

type TabKey = 'assets' | 'final' | 'project' | 'upload'
const tab = ref<TabKey>('assets')
const tabOptions = computed(() => [
  { label: t('works.coverTabAssets'), value: 'assets' },
  { label: t('works.coverTabFinal'), value: 'final' },
  { label: t('works.coverTabProject'), value: 'project' },
  { label: t('works.coverTabUpload'), value: 'upload' },
])

const selectedUrl = ref('')
const saving = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// ① 素材库（范围：本作品挂靠素材 / 全部我的素材——历史素材多为未归属，选全部时可顺手挂靠）
const assetImages = ref<Array<{ id: number; url: string; workId: number | null }>>([])
const assetsLoading = ref(false)
const assetScope = ref<'work' | 'all'>('work')

// ②③ 剪辑工程
const projects = ref<EditingProjectBrief[]>([])
const finalProjects = computed(() => projects.value.filter((p) => p.final_url))
const coveredProjects = computed(() => projects.value.filter((p) => p.cover_url))
const finalUid = ref('')
const frameT = ref(0)
const frameDuration = ref(0)
const frameSrc = ref('')

async function onOpen(): Promise<void> {
  tab.value = 'assets'
  selectedUrl.value = ''
  finalUid.value = ''
  frameSrc.value = ''
  assetsLoading.value = true
  try {
    const [assets, editorProjects] = await Promise.all([
      listAssets({
        media_type: 'image',
        work_id: assetScope.value === 'work' ? props.work.id : undefined,
        page: 1, page_size: 60,
      }),
      listEditorProjects(props.work.id),
    ])
    assetImages.value = assets.items
      .filter((a) => a.thumb_url || a.asset_url)
      .map((a) => ({ id: a.id, url: (a.thumb_url || a.asset_url) as string, workId: a.work_id }))
    projects.value = editorProjects.items
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    assetsLoading.value = false
  }
}

/** 选定成片工程：探测时长 + 抽首帧 */
async function onFinalChange(): Promise<void> {
  frameSrc.value = ''
  frameDuration.value = 0
  frameT.value = 0
  const project = finalProjects.value.find((p) => p.uid === finalUid.value)
  if (!project?.final_url) return
  frameDuration.value = await probeDuration(project.final_url)
  await grabFinalFrame()
}

async function grabFinalFrame(): Promise<void> {
  const project = finalProjects.value.find((p) => p.uid === finalUid.value)
  if (!project?.final_url) return
  const sink = await createVideoSink(project.final_url)
  if (!sink) return
  try {
    // t=0 起始帧可能落在关键帧前（同画布首帧 #t=0.1 惯例），钳 0.05s
    const frame = await sink.getCanvas(Math.max(frameT.value, 0.05))
    if (!frame) return
    const out = document.createElement('canvas')
    out.width = frame.canvas.width
    out.height = frame.canvas.height
    out.getContext('2d')?.drawImage(frame.canvas, 0, 0)
    frameSrc.value = out.toDataURL('image/jpeg', 0.85)
  } catch {
    /* 抽帧失败保持旧预览 */
  }
}

/** 素材范围切换：重拉列表 */
async function switchAssetScope(scope: unknown): Promise<void> {
  if (scope !== 'work' && scope !== 'all') return
  assetScope.value = scope
  assetsLoading.value = true
  try {
    const assets = await listAssets({
      media_type: 'image',
      work_id: scope === 'work' ? props.work.id : undefined,
      page: 1, page_size: 60,
    })
    assetImages.value = assets.items
      .filter((a) => a.thumb_url || a.asset_url)
      .map((a) => ({ id: a.id, url: (a.thumb_url || a.asset_url) as string, workId: a.work_id }))
    selectedUrl.value = ''
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    assetsLoading.value = false
  }
}

async function onPickFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  try {
    const { url } = await uploadWorkCover(file)
    selectedUrl.value = url
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    uploading.value = false
  }
}

/** 成片选帧的确认：帧 dataURL 先上传再引用 */
async function resolveCoverUrl(): Promise<string | null> {
  if (tab.value === 'final' && frameSrc.value.startsWith('data:')) {
    const blob = await (await fetch(frameSrc.value)).blob()
    const file = new File([blob], 'work-cover.jpg', { type: 'image/jpeg' })
    const { url } = await uploadWorkCover(file)
    return url
  }
  return selectedUrl.value || null
}

async function save(): Promise<void> {
  const url = await resolveCoverUrl()
  if (!url) return
  saving.value = true
  try {
    // 从「全部素材」选的未归属图：顺手挂到本作品（下次就在「本作品素材」里了）
    const picked = assetImages.value.find((a) => a.url === selectedUrl.value)
    if (picked && picked.workId !== props.work.id) {
      await updateAsset(picked.id, { work_id: props.work.id })
    }
    await updateWork(props.work.id, { cover_url: url })
    ElMessage.success(t('works.coverUpdated'))
    visible.value = false
    emit('saved')
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.cover-tabs {
  width: 100%;
  margin-bottom: 12px;
}
.scope-tabs {
  margin-bottom: 10px;
}
.pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
  min-height: 120px;
}
.pick-card {
  position: relative;
  aspect-ratio: 16 / 9;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-light);
  padding: 0;
}
.pick-card.active {
  border-color: var(--el-color-primary);
}
.pick-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.pick-empty {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.final-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.final-preview {
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.final-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 120px;
}
.upload-done {
  font-size: 12px;
  color: var(--el-color-success);
  word-break: break-all;
}
</style>

<!-- =====================================================
     作品详情页（/works/:id）
     集画布管理：每集一张画布（canvas_workspaces.work_id），可进入/删除
     剪辑工程与实体库为后续子批次挂载位
     ===================================================== -->

<template>
  <div class="work-detail">
    <div class="detail-head">
      <el-button text :icon="ArrowLeft" @click="router.push('/works')">{{ t('works.backToWorks') }}</el-button>
      <div class="head-meta">
        <h2>{{ work?.title || '...' }}</h2>
        <span v-if="work?.description" class="desc">{{ work.description }}</span>
      </div>
      <el-button type="primary" :icon="Plus" :disabled="!work" @click="createEpisode">{{ t('works.newEpisode') }}</el-button>
    </div>

    <h3 class="section-title">{{ t('works.editorProjects') }}</h3>
    <div class="canvas-grid">
      <div v-for="p in projects" :key="p.uid" class="canvas-card" @click="openProject(p.uid)">
        <div class="canvas-name" :title="p.title">{{ p.title }}</div>
        <div class="canvas-time">
          {{ t(`editor.renderStates.${p.render_status}`) }} · {{ formatDate(p.updated_at) }}
        </div>
        <div class="canvas-ops" @click.stop>
          <el-button size="small" text type="primary" @click="openProject(p.uid)">{{ t('works.openProject') }}</el-button>
          <a v-if="p.final_url" :href="p.final_url" target="_blank">
            <el-button size="small" text type="success">{{ t('works.projectFinal') }}</el-button>
          </a>
        </div>
      </div>
      <div class="canvas-card new-card" @click="createProject">
        <el-icon><Plus /></el-icon>
        <span>{{ t('works.newProject') }}</span>
      </div>
    </div>

    <h3 class="section-title">{{ t('works.canvases') }}</h3>
    <el-empty v-if="!loading && canvases.length === 0" :description="t('works.canvasEmpty')" />
    <div v-else v-loading="loading" class="canvas-grid">
      <div v-for="c in canvases" :key="c.id" class="canvas-card" @click="enterCanvas(c.id)">
        <div class="canvas-name" :title="c.name">{{ c.name }}</div>
        <div class="canvas-time">{{ formatDate(c.updated_at) }}</div>
        <div class="canvas-ops" @click.stop>
          <el-button size="small" text type="primary" @click="enterCanvas(c.id)">{{ t('works.enterCanvas') }}</el-button>
          <el-button size="small" text @click="renameCanvas(c)">{{ t('common.rename') }}</el-button>
          <el-button size="small" text type="danger" @click="removeCanvas(c)">{{ t('common.delete') }}</el-button>
        </div>
      </div>
    </div>

    <h3 class="section-title">{{ t('entityLib.title') }}</h3>
    <div class="lib-toolbar">
      <el-segmented v-model="kindFilter" :options="kindFilterOptions" />
      <el-button type="primary" plain :icon="Plus" @click="openCreateEntity">{{ t('entityLib.newEntity') }}</el-button>
    </div>
    <el-empty v-if="!loading && filteredEntities.length === 0" :description="t('entityLib.empty')" />
    <div v-else class="canvas-grid entity-grid">
      <div v-for="e in filteredEntities" :key="e.id" class="entity-card" @click="openEntityDetail(e)">
        <div class="entity-thumb">
          <img v-if="e.active_image_url" :src="e.active_image_url" loading="lazy" alt="" />
          <div v-else class="thumb-ph"><el-icon><ImageIcon /></el-icon></div>
          <span class="kind-badge">{{ kindLabel(e.kind) }}</span>
        </div>
        <div class="entity-name" :title="e.name">{{ e.name }}</div>
        <div class="entity-sub">{{ t('entityLib.versionN').replace('{n}', String(e.versions.length)) }}</div>
      </div>
    </div>

    <el-dialog v-model="createVisible" :title="t('entityLib.newEntity')" width="440px">
      <el-form label-width="72px">
        <el-form-item :label="t('entityLib.kind')">
          <el-segmented v-model="createForm.kind" :options="kindCreateOptions" />
        </el-form-item>
        <el-form-item :label="t('entityLib.name')">
          <el-input v-model="createForm.name" :placeholder="t('entityLib.namePh')" maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('entityLib.desc')">
          <el-input v-model="createForm.description" type="textarea" :rows="3" :placeholder="t('entityLib.descPh')" />
        </el-form-item>
        <el-form-item :label="t('entityLib.firstImage')">
          <div class="first-image">
            <label class="upload-box">
              <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="onFirstImage" />
              <ImagePlus :size="18" v-if="!createForm.previewUrl" />
              <img v-else :src="createForm.previewUrl" alt="" />
            </label>
            <span class="upload-hint">{{ t('entityLib.firstImageHint') }}</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!createForm.name.trim()" @click="submitCreateEntity">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" :title="detailEntity?.name || ''" width="520px">
      <template v-if="detailEntity">
        <el-form label-width="72px" @submit.prevent>
          <el-form-item :label="t('entityLib.name')">
            <el-input v-model="detailEntity.name" maxlength="64" />
          </el-form-item>
          <el-form-item :label="t('entityLib.desc')">
            <el-input v-model="detailEntity.description" type="textarea" :rows="2" :placeholder="t('entityLib.descPh')" />
          </el-form-item>
        </el-form>
        <EntityVersionList :versions="detailEntity.versions" @adopt="onAdopt" />
        <div class="detail-actions">
          <el-button size="small" :disabled="!detailDirty" @click="saveEntityDetail">{{ t('common.save') }}</el-button>
          <el-button size="small" type="danger" plain @click="removeEntity(detailEntity)">{{ t('common.delete') }}</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Image as ImageIcon, ImagePlus, Plus } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import { createEditorProject, listEditorProjects, type EditingProjectBrief } from '@/api/editor'
import { getWork, type WorkItem } from '@/api/works'
import { listWorkspaces, createWorkspace, deleteWorkspace, renameWorkspace, type WorkspaceBrief } from '@/api/canvasWorkspace'
import { useRename } from '@/composables/useRename'
import { createAsset } from '@/api/assets'
import {
  createWorkEntity, deleteWorkEntity, listWorkEntities, updateWorkEntity, uploadEntityImage, adoptEntityVersion,
  type EntityKind, type WorkEntityItem,
} from '@/api/workEntities'
import EntityVersionList from '@/components/works/EntityVersionList.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { confirm } = useConfirm()
const { rename } = useRename()

const workId = Number(route.params.id)
const work = ref<WorkItem | null>(null)
const canvases = ref<WorkspaceBrief[]>([])
const projects = ref<EditingProjectBrief[]>([])
const entities = ref<WorkEntityItem[]>([])
const loading = ref(false)

// ===== 实体库 =====
const kindFilter = ref<'all' | EntityKind>('all')
const kindFilterOptions = computed(() => [
  { label: t('entityLib.kindAll'), value: 'all' },
  { label: t('entityLib.kindCharacter'), value: 'character' },
  { label: t('entityLib.kindScene'), value: 'scene' },
  { label: t('entityLib.kindProp'), value: 'prop' },
])
const kindCreateOptions = computed(() => [
  { label: t('entityLib.kindCharacter'), value: 'character' },
  { label: t('entityLib.kindScene'), value: 'scene' },
  { label: t('entityLib.kindProp'), value: 'prop' },
])
const filteredEntities = computed(() =>
  kindFilter.value === 'all' ? entities.value : entities.value.filter((e) => e.kind === kindFilter.value),
)

const createVisible = ref(false)
const createForm = ref<{ kind: EntityKind; name: string; description: string; previewUrl: string; file: File | null }>({
  kind: 'character', name: '', description: '', previewUrl: '', file: null,
})
const detailVisible = ref(false)
const detailEntity = ref<WorkEntityItem | null>(null)
const detailSnapshot = ref('')

function kindLabel(kind: string): string {
  return kind === 'character' ? t('entityLib.kindCharacter') : kind === 'scene' ? t('entityLib.kindScene') : t('entityLib.kindProp')
}

const detailDirty = computed(() => {
  if (!detailEntity.value) return false
  return JSON.stringify([detailEntity.value.name, detailEntity.value.description]) !== detailSnapshot.value
})

async function fetchEntities(): Promise<void> {
  entities.value = (await listWorkEntities(workId)).items
}

function openCreateEntity(): void {
  createForm.value = { kind: 'character', name: '', description: '', previewUrl: '', file: null }
  createVisible.value = true
}

async function onFirstImage(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  createForm.value.file = file
  createForm.value.previewUrl = URL.createObjectURL(file)
}

async function submitCreateEntity(): Promise<void> {
  const form = createForm.value
  let assetId: number | undefined
  if (form.file) {
    const { url } = await uploadEntityImage(form.file)
    const asset = await createAsset({ url, media_type: 'image', name: form.name.trim(), work_id: workId })
    assetId = asset.id
  }
  await createWorkEntity(workId, { kind: form.kind, name: form.name.trim(), description: form.description || undefined, asset_id: assetId })
  ElMessage.success(t('entityLib.createdMsg'))
  createVisible.value = false
  await fetchEntities()
}

function openEntityDetail(e: WorkEntityItem): void {
  detailEntity.value = { ...e, versions: e.versions.map((v) => ({ ...v })) }
  detailSnapshot.value = JSON.stringify([detailEntity.value.name, detailEntity.value.description])
  detailVisible.value = true
}

async function saveEntityDetail(): Promise<void> {
  if (!detailEntity.value) return
  const updated = await updateWorkEntity(detailEntity.value.id, { name: detailEntity.value.name, description: detailEntity.value.description || undefined })
  Object.assign(detailEntity.value, updated)
  detailSnapshot.value = JSON.stringify([detailEntity.value.name, detailEntity.value.description])
  ElMessage.success(t('entityLib.updatedMsg'))
  await fetchEntities()
}

async function onAdopt(versionId: number): Promise<void> {
  if (!detailEntity.value) return
  const updated = await adoptEntityVersion(detailEntity.value.id, versionId)
  Object.assign(detailEntity.value, updated)
  ElMessage.success(t('entityLib.adoptDone'))
  await fetchEntities()
}

async function removeEntity(e: WorkEntityItem): Promise<void> {
  await confirm(t('entityLib.deleteConfirm').replace('{name}', e.name), t('common.delete'))
  await deleteWorkEntity(e.id)
  ElMessage.success(t('entityLib.deletedMsg'))
  detailVisible.value = false
  await fetchEntities()
}

function formatDate(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 10) : '-'
}

async function fetchAll(): Promise<void> {
  loading.value = true
  try {
    work.value = await getWork(workId)
    canvases.value = await listWorkspaces({ work_id: workId })
    projects.value = (await listEditorProjects(workId)).items
    entities.value = (await listWorkEntities(workId)).items
  } finally {
    loading.value = false
  }
}

async function createEpisode(): Promise<void> {
  const name = t('works.episodeN').replace('{n}', String(canvases.value.length + 1))
  await createWorkspace({ name, work_id: workId })
  ElMessage.success(t('works.episodeCreated'))
  await fetchAll()
}

async function createProject(): Promise<void> {
  const detail = await createEditorProject({
    title: t('works.projectN').replace('{n}', String(projects.value.length + 1)),
    work_id: workId,
  })
  await openProject(detail.uid)
}

async function openProject(uid: string): Promise<void> {
  await router.push(`/editor/${uid}`)
}

function enterCanvas(id: string): void {
  router.push({ path: '/canvas', query: { workspace: id } })
}

async function removeCanvas(canvas: WorkspaceBrief): Promise<void> {
  await confirm(`${t('common.delete')}: ${canvas.name}?`, t('common.delete'))
  await deleteWorkspace(canvas.id)
  await fetchAll()
}

async function renameCanvas(canvas: WorkspaceBrief): Promise<void> {
  const name = await rename(canvas.name)
  if (!name) return
  await renameWorkspace(canvas.id, name)
  ElMessage.success(t('common.renameDone'))
  await fetchAll()
}

onMounted(() => {
  void fetchAll()
})
</script>

<style scoped>
.work-detail {
  padding: 20px 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.head-meta {
  flex: 1;
  min-width: 0;
}

.head-meta h2 {
  margin: 0;
  font-size: 20px;
}

.desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.section-title {
  font-size: 15px;
  margin: 8px 0 12px;
}

.canvas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.canvas-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 12px 14px;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s;
}

.canvas-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.new-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  border-style: dashed;
  min-height: 96px;
}

.canvas-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.canvas-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin: 6px 0 8px;
}

.canvas-ops {
  display: flex;
  gap: 4px;
}

.lib-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.entity-grid {
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}

.entity-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s;
}

.entity-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.entity-thumb {
  position: relative;
  aspect-ratio: 1 / 1;
  background: var(--el-fill-color-light);
}

.entity-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
}

.kind-badge {
  position: absolute;
  left: 6px;
  top: 6px;
  font-size: 11px;
  line-height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
}

.entity-name {
  font-weight: 600;
  font-size: 13px;
  padding: 8px 10px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-sub {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding: 2px 10px 8px;
}

.first-image {
  display: flex;
  align-items: center;
  gap: 10px;
}

.upload-box {
  width: 64px;
  height: 64px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  overflow: hidden;
}

.upload-box img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.upload-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>

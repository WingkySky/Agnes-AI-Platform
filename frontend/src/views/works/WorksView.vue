<!-- =====================================================
     作品列表页（/works）
     作品 = 创作顶层容器：聚合集画布 / 剪辑工程 / 实体库
     ===================================================== -->

<template>
  <div class="works-page">
    <div class="works-head">
      <h2>{{ t('works.title') }}</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">{{ t('works.create') }}</el-button>
    </div>

    <el-empty v-if="!loading && works.length === 0" :description="t('works.empty')" />
    <div v-else v-loading="loading" class="works-grid">
      <div v-for="w in works" :key="w.id" class="work-card" @click="router.push(`/works/${w.id}`)">
        <div class="cover">
          <img v-if="w.cover_url" :src="w.cover_url" alt="" />
          <span v-else class="cover-ph">{{ w.title.slice(0, 1) }}</span>
          <label class="cover-change" :title="t('works.changeCover')" @click.stop>
            <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="(e) => changeCover(w, e)" />
            <ImagePlus :size="14" />
          </label>
        </div>
        <div class="meta">
          <div class="name" :title="w.title">{{ w.title }}</div>
          <div class="desc">{{ w.description || t('works.noDesc') }}</div>
          <div class="time">{{ formatDate(w.updated_at) }}</div>
        </div>
        <div class="ops" @click.stop>
          <el-button size="small" text @click="renameWork(w)">{{ t('common.rename') }}</el-button>
          <el-button size="small" text type="danger" @click="removeWork(w)">{{ t('common.delete') }}</el-button>
        </div>
      </div>
    </div>

    <!-- 未挂靠画布（收敛入口：在此挂到作品或进入） -->
    <template v-if="freeCanvases.length > 0">
      <h3 class="free-title">{{ t('works.freeCanvases') }}</h3>
      <div class="free-list">
        <div v-for="c in freeCanvases" :key="c.id" class="free-row">
          <span class="free-name" :title="c.name" @click="router.push(`/canvas?workspace=${c.id}`)">{{ c.name }}</span>
          <span class="free-time">{{ formatDate(c.updated_at) }}</span>
          <div class="free-ops">
            <el-button size="small" text type="primary" @click="router.push(`/canvas?workspace=${c.id}`)">{{ t('works.enterCanvas') }}</el-button>
            <el-button size="small" text @click="openBind(c)">{{ t('canvas.work.bindWork') }}</el-button>
            <el-button size="small" text type="danger" @click="removeFree(c)">{{ t('common.delete') }}</el-button>
          </div>
        </div>
      </div>
    </template>

    <el-dialog v-model="createVisible" :title="t('works.create')" width="440">
      <el-form label-width="64px">
        <el-form-item :label="t('works.name')">
          <el-input v-model="newTitle" maxlength="50" :placeholder="t('works.namePh')" />
        </el-form-item>
        <el-form-item :label="t('works.desc')">
          <el-input v-model="newDesc" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!newTitle.trim()" @click="submitCreate">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 挂到作品对话框（未挂靠画布 → 选择归属） -->
    <el-dialog v-model="bindVisible" :title="t('canvas.work.bindWork')" width="380">
      <el-select v-model="bindTarget" style="width: 100%">
        <el-option v-for="w in works" :key="w.id" :label="w.title" :value="w.id" />
      </el-select>
      <template #footer>
        <el-button @click="bindVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!bindTarget" @click="submitBind">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ImagePlus } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import { listWorks, createWork, deleteWork, updateWork, uploadWorkCover, type WorkItem } from '@/api/works'
import { useRename } from '@/composables/useRename'
import { listWorkspaces, deleteWorkspace, setWorkspaceWork, type WorkspaceBrief } from '@/api/canvasWorkspace'

const { t } = useI18n()
const { rename } = useRename()
const router = useRouter()
const { confirm } = useConfirm()

const works = ref<WorkItem[]>([])
const loading = ref(false)
const createVisible = ref(false)
const newTitle = ref('')
const newDesc = ref('')
const freeCanvases = ref<WorkspaceBrief[]>([])
const bindVisible = ref(false)
const bindCanvasId = ref<string | null>(null)
const bindTarget = ref<number | null>(null)

function formatDate(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 10) : '-'
}

async function fetchWorks(): Promise<void> {
  loading.value = true
  try {
    works.value = (await listWorks()).items
    const all = await listWorkspaces()
    freeCanvases.value = all.filter((w) => !w.work_id)
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  newTitle.value = ''
  newDesc.value = ''
  createVisible.value = true
}

async function submitCreate(): Promise<void> {
  const work = await createWork({ title: newTitle.value.trim(), description: newDesc.value.trim() || undefined })
  createVisible.value = false
  ElMessage.success(t('works.createdMsg'))
  router.push(`/works/${work.id}`)
}

async function removeWork(work: WorkItem): Promise<void> {
  await confirm(t('works.deleteConfirm').replace('{title}', work.title), t('common.delete'))
  await deleteWork(work.id)
  ElMessage.success(t('works.deletedMsg'))
  await fetchWorks()
}

function openBind(canvas: WorkspaceBrief): void {
  bindCanvasId.value = canvas.id
  bindTarget.value = works.value[0]?.id ?? null
  bindVisible.value = true
}

async function submitBind(): Promise<void> {
  if (!bindCanvasId.value || !bindTarget.value) return
  await setWorkspaceWork(bindCanvasId.value, bindTarget.value)
  bindVisible.value = false
  ElMessage.success(t('works.bindDone'))
  await fetchWorks()
}

async function removeFree(canvas: WorkspaceBrief): Promise<void> {
  await confirm(`${t('common.delete')}: ${canvas.name}?`, t('common.delete'))
  await deleteWorkspace(canvas.id)
  await fetchWorks()
}

async function changeCover(work: WorkItem, event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const { url } = await uploadWorkCover(file)
  await updateWork(work.id, { cover_url: url })
  ElMessage.success(t('works.coverUpdated'))
  await fetchWorks()
}

async function renameWork(work: WorkItem): Promise<void> {
  const name = await rename(work.title)
  if (!name) return
  await updateWork(work.id, { title: name })
  ElMessage.success(t('common.renameDone'))
  await fetchWorks()
}

onMounted(() => {
  void fetchWorks()
})
</script>

<style scoped>
.works-page {
  padding: 20px 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.works-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.works-head h2 {
  margin: 0;
  font-size: 20px;
}

.works-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.work-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s;
}

.work-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.cover {
  position: relative;
  height: 120px;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-change {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: none;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
}

.work-card:hover .cover-change {
  display: flex;
}

.cover-ph {
  font-size: 40px;
  color: var(--el-text-color-secondary);
}

.meta {
  padding: 10px 12px 4px;
}

.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}

.ops {
  padding: 4px 8px 8px;
  text-align: right;
}

/* 未挂靠画布（收敛入口区） */
.free-title {
  font-size: 15px;
  margin: 26px 0 12px;
  color: var(--el-text-color-secondary);
}

.free-list {
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  overflow: hidden;
}

.free-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--el-bg-color);
}

.free-row + .free-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

.free-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.free-name:hover {
  color: var(--el-color-primary);
}

.free-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.free-ops {
  display: flex;
  gap: 2px;
}
</style>

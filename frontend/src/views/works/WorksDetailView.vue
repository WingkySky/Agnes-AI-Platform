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

    <h3 class="section-title">{{ t('works.canvases') }}</h3>
    <el-empty v-if="!loading && canvases.length === 0" :description="t('works.canvasEmpty')" />
    <div v-else v-loading="loading" class="canvas-grid">
      <div v-for="c in canvases" :key="c.id" class="canvas-card" @click="enterCanvas(c.id)">
        <div class="canvas-name" :title="c.name">{{ c.name }}</div>
        <div class="canvas-time">{{ formatDate(c.updated_at) }}</div>
        <div class="canvas-ops" @click.stop>
          <el-button size="small" text type="primary" @click="enterCanvas(c.id)">{{ t('works.enterCanvas') }}</el-button>
          <el-button size="small" text type="danger" @click="removeCanvas(c)">{{ t('common.delete') }}</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Plus } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import { getWork, type WorkItem } from '@/api/works'
import { listWorkspaces, createWorkspace, deleteWorkspace, type WorkspaceBrief } from '@/api/canvasWorkspace'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { confirm } = useConfirm()

const workId = Number(route.params.id)
const work = ref<WorkItem | null>(null)
const canvases = ref<WorkspaceBrief[]>([])
const loading = ref(false)

function formatDate(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 10) : '-'
}

async function fetchAll(): Promise<void> {
  loading.value = true
  try {
    work.value = await getWork(workId)
    canvases.value = await listWorkspaces({ work_id: workId })
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

function enterCanvas(id: string): void {
  router.push({ path: '/canvas', query: { workspace: id } })
}

async function removeCanvas(canvas: WorkspaceBrief): Promise<void> {
  await confirm(`${t('common.delete')}: ${canvas.name}?`, t('common.delete'))
  await deleteWorkspace(canvas.id)
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
</style>

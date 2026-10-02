<!-- =====================================================
  画布版本历史弹窗
  - 两段列表：自动快照（节流时间线）/ 手动与保护快照（manual 命名版 + pre_danger 危险操作前）
  - 操作：还原（确认 → pre_danger 快照兜底 → 拉快照 data → store 覆盖当前工作区 → 正常保存链路）、
          删除、手动「存一版」（可命名）
  - 数据源：激活工作区（store.activeWorkspaceId）；anon（未落库）打开时提示不可用
====================================================== -->

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { History, RotateCcw, Trash2 } from 'lucide-vue-next'
import { useCanvasStore } from '@/stores/canvas'
import { t } from '@/i18n'
import {
  createSnapshot, deleteSnapshot, getSnapshot, listSnapshots,
  type SnapshotBrief,
} from '@/api/canvasWorkspace'
import { isCloudChannel } from '@/lib/canvas-storage'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const store = useCanvasStore()
const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const loading = ref(false)
const autoSnaps = ref<SnapshotBrief[]>([])
const manualSnaps = ref<SnapshotBrief[]>([])
const newVersionName = ref('')
const restoring = ref(false)

/** 手动段 = manual 命名版 + pre_danger 保护快照 */
function splitItems(items: SnapshotBrief[]): void {
  autoSnaps.value = items.filter((s) => s.kind === 'auto')
  manualSnaps.value = items.filter((s) => s.kind !== 'auto')
}

async function reload(): Promise<void> {
  const wsId = store.activeWorkspaceId
  if (!wsId) return
  loading.value = true
  try {
    const resp = await listSnapshots(wsId)
    splitItems(resp.items ?? [])
  } finally {
    loading.value = false
  }
}

watch(visible, (v) => {
  if (v) {
    autoSnaps.value = []
    manualSnaps.value = []
    newVersionName.value = ''
    if (isCloudChannel() && store.activeWorkspaceId) void reload()
  }
})

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function handleSaveVersion(): Promise<void> {
  const wsId = store.activeWorkspaceId
  if (!wsId) return
  const name = newVersionName.value.trim() || t('canvas.history.unnamedVersion')
  await createSnapshot(wsId, 'manual', name)
  newVersionName.value = ''
  ElMessage.success(t('canvas.history.versionSaved'))
  await reload()
}

async function handleRestore(snap: SnapshotBrief): Promise<void> {
  const wsId = store.activeWorkspaceId
  if (!wsId || restoring.value) return
  try {
    await ElMessageBox.confirm(t('canvas.history.restoreConfirm'), t('canvas.history.restore'), {
      confirmButtonText: t('canvas.history.restore'),
      cancelButtonText: t('canvas.templates.cancel'),
      type: 'warning',
    })
  } catch {
    return
  }
  restoring.value = true
  try {
    // 还原前先拍保护快照：当前现场可随时找回
    await createSnapshot(wsId, 'pre_danger')
    const detail = await getSnapshot(wsId, snap.id)
    store.applyWorkspaceData(detail.data ?? {})
    ElMessage.success(t('canvas.history.restoreDone'))
    visible.value = false
  } finally {
    restoring.value = false
  }
}

async function handleDelete(snap: SnapshotBrief): Promise<void> {
  const wsId = store.activeWorkspaceId
  if (!wsId) return
  try {
    await ElMessageBox.confirm(t('canvas.history.deleteConfirm'), t('canvas.history.delete'), {
      confirmButtonText: t('canvas.history.delete'),
      cancelButtonText: t('canvas.templates.cancel'),
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteSnapshot(wsId, snap.id)
  await reload()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('canvas.history.title')"
    width="520px"
    :append-to-body="true"
  >
    <template v-if="!isCloudChannel() || !store.activeWorkspaceId">
      <p class="history-empty">{{ t('canvas.history.unavailable') }}</p>
    </template>
    <template v-else>
      <div class="history-save-version">
        <el-input
          v-model="newVersionName"
          :placeholder="t('canvas.history.namePlaceholder')"
          size="default"
          maxlength="60"
          @keydown.enter="handleSaveVersion"
        />
        <el-button type="primary" :loading="loading" @click="handleSaveVersion">
          {{ t('canvas.history.saveVersion') }}
        </el-button>
      </div>

      <div v-loading="loading" class="history-body">
        <section class="history-section">
          <h4>{{ t('canvas.history.manualGroup') }}</h4>
          <p v-if="!manualSnaps.length" class="history-empty">{{ t('canvas.history.emptyManual') }}</p>
          <div v-for="snap in manualSnaps" :key="snap.id" class="history-item">
            <div class="history-info">
              <span class="history-name">
                {{ snap.kind === 'pre_danger' ? t('canvas.history.preDangerLabel') : snap.name }}
              </span>
              <span class="history-time">{{ fmtTime(snap.created_at) }}</span>
            </div>
            <div class="history-actions">
              <el-button size="small" :icon="RotateCcw" :loading="restoring" @click="handleRestore(snap)">
                {{ t('canvas.history.restore') }}
              </el-button>
              <el-button size="small" :icon="Trash2" type="danger" plain @click="handleDelete(snap)" />
            </div>
          </div>
        </section>

        <section class="history-section">
          <h4>{{ t('canvas.history.autoGroup') }}</h4>
          <p v-if="!autoSnaps.length" class="history-empty">{{ t('canvas.history.emptyAuto') }}</p>
          <div v-for="snap in autoSnaps" :key="snap.id" class="history-item">
            <div class="history-info">
              <span class="history-time">{{ fmtTime(snap.created_at) }}</span>
            </div>
            <div class="history-actions">
              <el-button size="small" :icon="RotateCcw" :loading="restoring" @click="handleRestore(snap)">
                {{ t('canvas.history.restore') }}
              </el-button>
              <el-button size="small" :icon="Trash2" type="danger" plain @click="handleDelete(snap)" />
            </div>
          </div>
        </section>
      </div>
    </template>
    <template #footer>
      <span class="history-hint"><History :size="13" /> {{ t('canvas.history.autoHint') }}</span>
    </template>
  </el-dialog>
</template>

<style scoped>
.history-save-version {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.history-body {
  max-height: 46vh;
  overflow-y: auto;
  min-height: 80px;
}
.history-section h4 {
  margin: 8px 0 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
}
.history-item:hover {
  background: var(--el-fill-color-light);
}
.history-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.history-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.history-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.history-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 8px;
}
.history-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

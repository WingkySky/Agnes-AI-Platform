<template>
  <el-dialog :model-value="open" :title="t('editor.historyTitle')" width="520px" append-to-body @update:model-value="emit('close')">
    <div v-if="loading" class="his-loading"><el-icon class="is-loading"><Loading /></el-icon></div>
    <template v-else>
      <p v-if="!items.length" class="his-empty">{{ t('editor.historyEmpty') }}</p>
      <ul v-else class="his-list">
        <li v-for="s in items" :key="s.id">
          <button type="button" class="his-row" @click="restore(s)">
            <el-tag size="small" :type="s.reason === 'agent_edit' ? 'primary' : 'info'">{{ reasonLabel(s.reason) }}</el-tag>
            <span class="his-time">{{ (s.created_at || '').slice(0, 19).replace('T', ' ') }}</span>
            <span class="his-rev">rev {{ s.revision }}</span>
            <span class="his-restore">{{ t('editor.historyRestore') }}</span>
          </button>
        </li>
      </ul>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/* 版本历史还原（快照 API 已有，纯界面）：列表 → 确认 → 拉 data 走正常保存链路 */
import { ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getEditorSnapshot, listEditorSnapshots, saveEditorDocument, type EditorSnapshotBrief } from '@/api/editor'
import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
const store = useEditorStore()
const loading = ref(false)
const items = ref<EditorSnapshotBrief[]>([])

watch(() => props.open, (open) => {
  if (!open) return
  void loadList()
})

async function loadList(): Promise<void> {
  if (!store.uid) return
  loading.value = true
  try {
    const resp = await listEditorSnapshots(store.uid)
    items.value = resp.items
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function reasonLabel(reason: string | null): string {
  const map: Record<string, string> = {
    agent_edit: t('editor.historyReasonAgent'),
    ai_rough_cut: t('editor.historyReasonRoughCut'),
    agent_subtitles: t('editor.historyReasonSubtitles'),
  }
  return (reason && map[reason]) || t('editor.historyReasonManual')
}

async function restore(s: EditorSnapshotBrief): Promise<void> {
  const time = (s.created_at || '').slice(0, 19).replace('T', ' ')
  try {
    await ElMessageBox.confirm(
      t('editor.historyConfirm', { time }),
      t('editor.historyRestore'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const snap = await getEditorSnapshot(store.uid, s.id)
    await saveEditorDocument(store.uid, snap.data, store.revision)
    await store.load(store.uid)
    ElMessage.success(t('editor.historyRestored'))
    emit('close')
  } catch (e) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('editor.historyFailed'))
  }
}
</script>

<style scoped>
.his-loading { padding: 24px; text-align: center; }
.his-empty { margin: 0; font-size: 13px; color: var(--el-text-color-secondary); }
.his-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; max-height: 420px; overflow-y: auto; }
.his-row {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 7px 8px; border: none; border-radius: 6px; background: transparent;
  cursor: pointer; text-align: left; color: inherit; font-size: 13px;
}
.his-row:hover { background: var(--el-fill-color-light); }
.his-time { font-family: ui-monospace, monospace; }
.his-rev { font-size: 12px; color: var(--el-text-color-secondary); }
.his-restore { margin-left: auto; font-size: 12px; color: var(--el-color-primary); }
</style>

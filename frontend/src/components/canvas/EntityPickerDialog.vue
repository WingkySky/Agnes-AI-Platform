<!-- =====================================================
     实体选择器：从作品实体库选实体落画布卡（跨集复用入口）
     快捷菜单「实体库」动作打开；选中后由父级落挂链图片节点
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('entityLib.title')" width="560px" @open="fetchEntities">
    <div class="picker-toolbar">
      <el-segmented v-model="kind" :options="kindOptions" />
    </div>
    <el-empty v-if="!loading && filtered.length === 0" :description="t('entityLib.empty')" />
    <div v-else v-loading="loading" class="picker-grid">
      <div v-for="e in filtered" :key="e.id" class="picker-card" @click="emit('select', e)">
        <div class="picker-thumb">
          <img v-if="e.active_image_url" :src="e.active_image_url" loading="lazy" alt="" />
          <span v-else class="picker-ph">{{ e.name.slice(0, 1) }}</span>
        </div>
        <div class="picker-name" :title="e.name">{{ e.name }}</div>
        <div class="picker-kind">{{ kindLabel(e.kind) }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { listWorkEntities, type EntityKind, type WorkEntityItem } from '@/api/workEntities'
import { useCanvasStore } from '@/stores/canvas'

const visible = defineModel<boolean>({ default: false })
const emit = defineEmits<{ select: [entity: WorkEntityItem] }>()
const { t } = useI18n()
const store = useCanvasStore()

const kind = ref<'all' | EntityKind>('all')
const entities = ref<WorkEntityItem[]>([])
const loading = ref(false)

const kindOptions = computed(() => [
  { label: t('entityLib.kindAll'), value: 'all' },
  { label: t('entityLib.kindCharacter'), value: 'character' },
  { label: t('entityLib.kindScene'), value: 'scene' },
  { label: t('entityLib.kindProp'), value: 'prop' },
])
const filtered = computed(() =>
  kind.value === 'all' ? entities.value : entities.value.filter((e) => e.kind === kind.value),
)

watch(kind, () => { void fetchEntities() })

function kindLabel(k: string): string {
  return k === 'character' ? t('entityLib.kindCharacter') : k === 'scene' ? t('entityLib.kindScene') : t('entityLib.kindProp')
}

async function fetchEntities(): Promise<void> {
  const workId = store.activeWorkspace?.work_id
  if (!workId) return
  loading.value = true
  try {
    entities.value = (await listWorkEntities(workId)).items
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.picker-toolbar {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  max-height: 380px;
  overflow-y: auto;
}

.picker-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s;
}

.picker-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.picker-thumb {
  aspect-ratio: 1 / 1;
  background: var(--el-fill-color-light);
}

.picker-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.picker-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--el-text-color-placeholder);
}

.picker-name {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 8px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-kind {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  padding: 0 8px 6px;
}
</style>

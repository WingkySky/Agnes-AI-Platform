<!-- =====================================================
     实体版本切换器 EntityVersionSwitcher
     - 展示某实体的所有版本（自动生成的 + 手动上传的）
     - 点击切换为采用版本（is_active）
     - 支持删除非采用版本
     - 弹出方式：el-popover 或 el-dialog
     ===================================================== -->

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom"
    :width="420"
    trigger="click"
  >
    <template #reference>
      <el-button link :icon="Switch" @click.stop="onOpen">
        <span v-if="activeVersion">v{{ activeVersion.version }}</span>
        <span v-else>版本</span>
      </el-button>
    </template>

    <div class="version-switcher" v-loading="loading">
      <div class="header">
        <span class="title">版本历史</span>
        <el-button link :icon="Refresh" @click="loadVersions" />
      </div>

      <div v-if="!loading && versions.length === 0" class="empty">
        暂无版本
      </div>

      <div v-else class="version-list">
        <div
          v-for="ver in versions"
          :key="ver.id"
          class="version-item"
          :class="{ active: ver.is_active }"
        >
          <div class="version-thumb">
            <img v-if="ver.thumbnail_url" :src="ver.thumbnail_url" :alt="`v${ver.version}`" />
            <el-icon v-else><Picture /></el-icon>
          </div>
          <div class="version-info">
            <div class="version-no">
              v{{ ver.version }}
              <el-tag v-if="ver.is_active" type="success" size="small">采用中</el-tag>
              <el-tag v-if="ver.is_manual" type="warning" size="small">手动上传</el-tag>
            </div>
            <div class="version-meta">
              <span>{{ formatDate(ver.created_at) }}</span>
              <span v-if="ver.model">· {{ ver.model }}</span>
            </div>
          </div>
          <div class="version-actions">
            <el-button
              v-if="!ver.is_active"
              link
              type="primary"
              size="small"
              @click="onSetActive(ver)"
            >采用</el-button>
            <el-button
              v-if="!ver.is_active"
              link
              type="danger"
              size="small"
              :icon="Delete"
              @click="onDelete(ver)"
            />
          </div>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Switch, Refresh, Picture, Delete } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { EntityType, ProjectEntityAsset } from '@/types/project'

const props = defineProps<{
  entityType: EntityType
  entityId: number
  /** 当前采用版本（来自父组件） */
  activeVersion?: ProjectEntityAsset | null
}>()

const emit = defineEmits<{
  /** 切换/删除后通知父组件刷新 */
  (e: 'change'): void
}>()

const projectStore = useProjectStore()

const visible = ref(false)
const loading = ref(false)
const versions = ref<ProjectEntityAsset[]>([])

const activeVersion = computed(() =>
  versions.value.find(v => v.is_active) || props.activeVersion,
)

async function loadVersions() {
  loading.value = true
  try {
    versions.value = await projectStore.fetchEntityVersions(props.entityType, props.entityId)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载版本失败')
  } finally {
    loading.value = false
  }
}

function formatDate(s?: string | null): string {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function onOpen() {
  if (versions.value.length === 0) {
    loadVersions()
  }
}

async function onSetActive(ver: ProjectEntityAsset) {
  try {
    await projectStore.setEntityActiveVersion(props.entityType, props.entityId, ver.id)
    ElMessage.success(`已切换到 v${ver.version}`)
    emit('change')
    await loadVersions()
  } catch (e: any) {
    ElMessage.error(e?.message || '切换失败')
  }
}

async function onDelete(ver: ProjectEntityAsset) {
  try {
    await ElMessageBox.confirm(
      `确定删除 v${ver.version}？此操作不可撤销。`,
      '删除版本',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  try {
    await projectStore.deleteEntityVersion(props.entityType, props.entityId, ver.id)
    ElMessage.success('版本已删除')
    emit('change')
    await loadVersions()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// 弹窗打开时自动加载
watch(visible, (val) => {
  if (val) loadVersions()
})
</script>

<style scoped>
.version-switcher { padding: 4px 0; }

.header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.title { font-size: 14px; font-weight: 600; }

.empty {
  text-align: center; padding: 24px 0;
  color: var(--el-text-color-secondary); font-size: 13px;
}

.version-list {
  display: flex; flex-direction: column; gap: 8px;
  max-height: 360px; overflow-y: auto;
}

.version-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px; border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.version-item.active {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.version-thumb {
  width: 56px; height: 56px; flex-shrink: 0;
  border-radius: 4px; overflow: hidden;
  background: var(--el-fill-color);
  display: flex; align-items: center; justify-content: center;
  color: var(--el-text-color-secondary);
}
.version-thumb img { width: 100%; height: 100%; object-fit: cover; }

.version-info { flex: 1; min-width: 0; }
.version-no {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600;
}
.version-meta {
  margin-top: 4px; font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex; gap: 4px;
}

.version-actions {
  display: flex; gap: 4px;
}
</style>

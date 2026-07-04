<!-- =====================================================
     道具 Tab PropsTab
     - 展示道具卡片网格（CharacterCard 通用组件 + entityType=prop）
     - 多选批量生成图像
     - 新建道具（弹出 EntityEditDialog）
     - 从剧本提取道具
     ===================================================== -->

<template>
  <div class="props-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Plus" @click="onCreate">新建道具</el-button>
        <el-button
          v-if="selectedIds.length > 0"
          :icon="MagicStick"
          :loading="batchGenerating"
          @click="onBatchGenerate"
        >
          批量生成 ({{ selectedIds.length }})
        </el-button>
        <el-button
          v-if="projectStore.scripts.length > 0"
          :icon="Document"
          :loading="extracting"
          @click="onExtractFromScript"
        >从剧本提取</el-button>
      </div>
      <div class="toolbar-right">
        <el-button :icon="Refresh" link @click="onRefresh">刷新</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && props.length === 0" class="empty-state">
      <el-icon :size="48"><Box /></el-icon>
      <p class="empty-text">还没有道具，点击「新建道具」或「从剧本提取」开始</p>
    </div>

    <!-- 道具卡片网格 -->
    <div v-else class="card-grid">
      <CharacterCard
        v-for="prop in props"
        :key="prop.id"
        entity-type="prop"
        :entity="prop"
        :active-image="prop.active_image"
        :selected="selectedIds.includes(prop.id)"
        :generating="generatingIds.includes(prop.id)"
        @toggle-select="onToggleSelect"
        @edit="onEdit"
        @refresh="onRefresh"
      />
    </div>

    <!-- 编辑对话框 -->
    <EntityEditDialog
      v-model="editDialogVisible"
      entity-type="prop"
      :entity="editingEntity"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, MagicStick, Document, Box } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import CharacterCard from './CharacterCard.vue'
import EntityEditDialog from './EntityEditDialog.vue'

const projectStore = useProjectStore()

const loading = ref(false)
const props = computed(() => projectStore.props)

// 选中状态
const selectedIds = ref<number[]>([])
function onToggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

// 生成中状态
const generatingIds = ref<number[]>([])
const batchGenerating = ref(false)

// 编辑对话框
const editDialogVisible = ref(false)
const editingEntity = ref<any | null>(null)

function onCreate() {
  editingEntity.value = null
  editDialogVisible.value = true
}

function onEdit(entity: any) {
  editingEntity.value = entity
  editDialogVisible.value = true
}

function onSaved() {
  onRefresh()
}

// 批量生成
async function onBatchGenerate() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `将为选中的 ${selectedIds.value.length} 个道具批量生成图像，是否继续？`,
      '批量生成',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  batchGenerating.value = true
  generatingIds.value.push(...selectedIds.value)
  try {
    await Promise.all(
      selectedIds.value.map(id =>
        projectStore.generateEntityImage('prop', id, {}).catch(() => {/* 忽略单个失败 */}),
      ),
    )
    ElMessage.success('批量生成任务已启动')
  } catch (e: any) {
    ElMessage.error(e?.message || '批量生成失败')
  } finally {
    batchGenerating.value = false
    setTimeout(() => { generatingIds.value = [] }, 5000)
  }
}

// 从剧本提取
const extracting = ref(false)
async function onExtractFromScript() {
  if (projectStore.scripts.length === 0) {
    ElMessage.warning('当前项目没有剧本')
    return
  }
  const script = projectStore.scripts[0]
  try {
    await ElMessageBox.confirm(
      `将从剧本「${script.title || '第 ' + script.episode_no + ' 集'}」中提取道具，是否继续？`,
      '提取道具',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  extracting.value = true
  try {
    await projectStore.extractEntitiesFromScript('prop', script.id)
    ElMessage.success('已提取道具')
  } catch (e: any) {
    ElMessage.error(e?.message || '提取失败')
  } finally {
    extracting.value = false
  }
}

function onRefresh() {
  loading.value = true
  projectStore.fetchEntities('prop').finally(() => {
    loading.value = false
  })
}

onMounted(() => {
  if (props.value.length === 0) onRefresh()
})
</script>

<style scoped>
.props-tab { padding: 4px 0; }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.toolbar-left { display: flex; gap: 8px; flex-wrap: wrap; }

.empty-state {
  text-align: center; padding: 60px 0; color: var(--el-text-color-secondary);
}
.empty-text { margin-top: 12px; font-size: 13px; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
</style>

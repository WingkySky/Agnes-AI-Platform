<!-- =====================================================
     角色 Tab CharactersTab
     - 展示角色卡片网格（CharacterCard）
     - 多选批量生成图像
     - 新建角色（弹出 EntityEditDialog）
     - 从剧本提取角色
     ===================================================== -->

<template>
  <div class="characters-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Plus" @click="onCreate">新建角色</el-button>
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
    <div v-if="!loading && characters.length === 0" class="empty-state">
      <el-icon :size="48"><User /></el-icon>
      <p class="empty-text">还没有角色，点击「新建角色」或「从剧本提取」开始</p>
    </div>

    <!-- 角色卡片网格 -->
    <div v-else class="card-grid">
      <CharacterCard
        v-for="char in characters"
        :key="char.id"
        entity-type="character"
        :entity="char"
        :active-image="char.active_image"
        :selected="selectedIds.includes(char.id)"
        :generating="generatingIds.includes(char.id)"
        @toggle-select="onToggleSelect"
        @edit="onEdit"
        @refresh="onRefresh"
      />
    </div>

    <!-- 编辑对话框 -->
    <EntityEditDialog
      v-model="editDialogVisible"
      entity-type="character"
      :entity="editingEntity"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, MagicStick, Document, User } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import CharacterCard from './CharacterCard.vue'
import EntityEditDialog from './EntityEditDialog.vue'
import type { ProjectCharacter } from '@/types/project'

const projectStore = useProjectStore()

const loading = ref(false)
const characters = computed(() => projectStore.characters)

// 选中状态
const selectedIds = ref<number[]>([])
function onToggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

// 生成中状态（外部触发后由 SSE 推送结束，这里仅做短期本地标记）
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
      `将为选中的 ${selectedIds.value.length} 个角色批量生成图像，是否继续？`,
      '批量生成',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  batchGenerating.value = true
  // 标记为生成中
  generatingIds.value.push(...selectedIds.value)
  try {
    await projectStore.batchGenerateCharacters({ ids: selectedIds.value })
    ElMessage.success('批量生成任务已启动')
  } catch (e: any) {
    ElMessage.error(e?.message || '批量生成失败')
  } finally {
    batchGenerating.value = false
    // 5 秒后清除本地生成中标记（实际状态由 SSE 推送更新）
    setTimeout(() => {
      generatingIds.value = []
    }, 5000)
  }
}

// 从剧本提取
const extracting = ref(false)
async function onExtractFromScript() {
  if (projectStore.scripts.length === 0) {
    ElMessage.warning('当前项目没有剧本，请先创建剧本')
    return
  }
  // 简单选择第一个剧本（如有多集，用户可先在剧本 Tab 选定后再来此）
  const script = projectStore.scripts[0]
  try {
    await ElMessageBox.confirm(
      `将从剧本「${script.title || '第 ' + script.episode_no + ' 集'}」中提取角色，是否继续？`,
      '提取角色',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  extracting.value = true
  try {
    await projectStore.extractEntitiesFromScript('character', script.id)
    ElMessage.success('已提取角色')
  } catch (e: any) {
    ElMessage.error(e?.message || '提取失败')
  } finally {
    extracting.value = false
  }
}

function onRefresh() {
  loading.value = true
  projectStore.fetchEntities('character').finally(() => {
    loading.value = false
  })
}

onMounted(() => {
  if (characters.value.length === 0) onRefresh()
})
</script>

<style scoped>
.characters-tab { padding: 4px 0; }

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

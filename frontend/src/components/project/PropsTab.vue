<!-- =====================================================
     道具 Tab PropsTab
     - 展示道具卡片网格（CharacterCard 通用组件 + entityType=prop）
     - 多选批量生成图像
     - 新建道具（弹出 EntityEditDialog）
     - 从剧本提取道具
     - 集数隔离：全部集视图按集分组，单集视图直接展示
     - 跨集复制：复制道具到其他集
     ===================================================== -->

<template>
  <div class="props-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 新建道具：全部集视图下禁用（需先选定集数） -->
        <el-button type="primary" :icon="Plus" :disabled="!canCreate" @click="onCreate">新建道具</el-button>
        <el-tooltip v-if="!canCreate" :content="t('project.selectEpisodeFirst')" placement="top">
          <el-icon class="disabled-hint"><InfoFilled /></el-icon>
        </el-tooltip>
        <el-button
          v-if="selectedIds.length > 0"
          :icon="MagicStick"
          :loading="batchGenerating"
          @click="onBatchGenerate"
        >
          批量生成 ({{ selectedIds.length }})
        </el-button>
        <!-- 从剧本提取：全部集视图下禁用（需先选定集数） -->
        <el-button
          v-if="projectStore.scripts.length > 0"
          :icon="Document"
          :loading="extracting"
          :disabled="!canCreate"
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
    <!-- 全部集视图：按集折叠分组展示 -->
    <template v-else-if="isAllEpisodeView">
      <el-collapse v-for="(epProps, ep) in propsByEpisode" :key="ep">
        <el-collapse-item :title="`第${ep}集（${epProps.length} 个道具）`">
          <div class="card-grid">
            <div v-for="prop in epProps" :key="prop.id" class="card-cell">
              <CharacterCard
                entity-type="prop"
                :entity="prop"
                :active-image="prop.active_image"
                :selected="selectedIds.includes(prop.id)"
                :generating="generatingIds.includes(prop.id)"
                @toggle-select="onToggleSelect"
                @edit="onEdit"
                @refresh="onRefresh"
              />
              <!-- 跨集复制：复制到其他集 -->
              <div v-if="otherScripts.length > 0" class="card-copy-action" @click.stop>
                <el-dropdown @command="(cmd: number) => onCopyTo(prop.id, cmd)">
                  <el-button size="small" text>
                    <el-icon><CopyDocument /></el-icon>
                    {{ t('project.copyToEpisode') }}
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="script in otherScripts"
                        :key="script.id"
                        :command="script.id"
                      >
                        第{{ script.episode_no }}集：{{ script.title }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>

    <!-- 单集视图：直接展示当前集道具 -->
    <div v-else class="card-grid">
      <div v-for="prop in props" :key="prop.id" class="card-cell">
        <CharacterCard
          entity-type="prop"
          :entity="prop"
          :active-image="prop.active_image"
          :selected="selectedIds.includes(prop.id)"
          :generating="generatingIds.includes(prop.id)"
          @toggle-select="onToggleSelect"
          @edit="onEdit"
          @refresh="onRefresh"
        />
        <!-- 跨集复制：复制到其他集 -->
        <div v-if="otherScripts.length > 0" class="card-copy-action" @click.stop>
          <el-dropdown @command="(cmd: number) => onCopyTo(prop.id, cmd)">
            <el-button size="small" text>
              <el-icon><CopyDocument /></el-icon>
              {{ t('project.copyToEpisode') }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="script in otherScripts"
                  :key="script.id"
                  :command="script.id"
                >
                  第{{ script.episode_no }}集：{{ script.title }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
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
import { Plus, Refresh, MagicStick, Document, Box, CopyDocument, InfoFilled } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useI18n } from '@/i18n'
import CharacterCard from './CharacterCard.vue'
import EntityEditDialog from './EntityEditDialog.vue'

const projectStore = useProjectStore()
const { t } = useI18n()

const loading = ref(false)
const props = computed(() => projectStore.props)
/* 集数隔离：全部集视图按 episode_no 分组；单集视图直接展示当前集 */
const isAllEpisodeView = computed(() => projectStore.currentScriptId === null)
const propsByEpisode = computed(() => projectStore.propsByEpisode)
const canCreate = computed(() => projectStore.currentScriptId !== null)
/* 跨集复制目标候选：排除当前集，避免复制到自身 */
const otherScripts = computed(() =>
  projectStore.scripts.filter(s => s.id !== projectStore.currentScriptId),
)

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

// 从剧本提取（使用当前选中的集 currentScriptId，移除原 scripts[0] 硬编码）
const extracting = ref(false)
async function onExtractFromScript() {
  if (!projectStore.currentScriptId) {
    ElMessage.warning(t('project.selectEpisodeFirst'))
    return
  }
  // 查找当前集对应的剧本对象，仅用于弹窗展示标题
  const script = projectStore.scripts.find(s => s.id === projectStore.currentScriptId)
  try {
    await ElMessageBox.confirm(
      `将从剧本「${script?.title || (script ? '第 ' + script.episode_no + ' 集' : '当前集数')}」中提取道具，是否继续？`,
      '提取道具',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  extracting.value = true
  try {
    await projectStore.extractEntitiesFromScript('prop', projectStore.currentScriptId)
    ElMessage.success('已提取道具')
  } catch (e: any) {
    ElMessage.error(e?.message || '提取失败')
  } finally {
    extracting.value = false
  }
}

// 跨集复制：把当前道具复制到其他集（不自动切换集数，留在当前集）
async function onCopyTo(entityId: number, targetScriptId: number) {
  if (!projectStore.currentScriptId) return
  try {
    await projectStore.copyEntityTo('prop', entityId, targetScriptId)
    ElMessage.success(t('project.copiedToEpisode'))
  } catch (e: any) {
    ElMessage.error(e?.message || '复制失败')
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
.toolbar-left { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

/* 禁用提示图标：与按钮垂直对齐 */
.disabled-hint {
  color: var(--el-text-color-secondary);
  font-size: 16px;
  cursor: help;
}

.empty-state {
  text-align: center; padding: 60px 0; color: var(--el-text-color-secondary);
}
.empty-text { margin-top: 12px; font-size: 13px; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

/* 卡片单元格：卡片 + 跨集复制按钮 */
.card-cell {
  display: flex;
  flex-direction: column;
}
.card-copy-action {
  display: flex;
  justify-content: center;
  padding-top: 4px;
}
</style>

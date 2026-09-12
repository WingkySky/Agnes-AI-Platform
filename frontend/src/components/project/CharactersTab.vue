<!-- =====================================================
     角色 Tab CharactersTab
     - 展示角色卡片网格（CharacterCard）
     - 多选批量生成图像
     - 新建角色（弹出 EntityEditDialog）
     - 从剧本提取角色
     - 集数隔离：全部集视图按集分组，单集视图直接展示
     - 跨集复制：复制角色到其他集
     ===================================================== -->

<template>
  <div class="characters-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 新建角色：全部集视图下禁用（需先选定集数） -->
        <el-button type="primary" :icon="Plus" :disabled="!canCreate" @click="onCreate">新建角色</el-button>
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
    <div v-if="!loading && characters.length === 0" class="empty-state">
      <el-icon :size="48"><User /></el-icon>
      <p class="empty-text">还没有角色，点击「新建角色」或「从剧本提取」开始</p>
    </div>

    <!-- 角色卡片网格 -->
    <!-- 全部集视图：按集折叠分组展示 -->
    <template v-else-if="isAllEpisodeView">
      <el-collapse v-for="(epChars, ep) in charactersByEpisode" :key="ep">
        <el-collapse-item :title="`第${ep}集（${epChars.length} 个角色）`">
          <div class="card-grid">
            <div v-for="char in epChars" :key="char.id" class="card-cell">
              <CharacterCard
                entity-type="character"
                :entity="char"
                :active-image="char.active_image"
                :selected="selectedIds.includes(char.id)"
                :generating="generatingIds.includes(char.id)"
                @toggle-select="onToggleSelect"
                @edit="onEdit"
                @refresh="onRefresh"
              />
              <!-- 跨集复制：复制到其他集 -->
              <div v-if="otherScripts.length > 0" class="card-copy-action" @click.stop>
                <el-dropdown @command="(cmd: number) => onCopyTo(char.id, cmd)">
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

    <!-- 单集视图：直接展示当前集角色 -->
    <div v-else class="card-grid">
      <div v-for="char in characters" :key="char.id" class="card-cell">
        <CharacterCard
          entity-type="character"
          :entity="char"
          :active-image="char.active_image"
          :selected="selectedIds.includes(char.id)"
          :generating="generatingIds.includes(char.id)"
          @toggle-select="onToggleSelect"
          @edit="onEdit"
          @refresh="onRefresh"
        />
        <!-- 跨集复制：复制到其他集 -->
        <div v-if="otherScripts.length > 0" class="card-copy-action" @click.stop>
          <el-dropdown @command="(cmd: number) => onCopyTo(char.id, cmd)">
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
      entity-type="character"
      :entity="editingEntity"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, MagicStick, Document, User, CopyDocument, InfoFilled } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useI18n } from '@/i18n'
import CharacterCard from './CharacterCard.vue'
import EntityEditDialog from './EntityEditDialog.vue'
import type { ProjectCharacter } from '@/types/project'

const projectStore = useProjectStore()
const { t } = useI18n()

const loading = ref(false)
const characters = computed(() => projectStore.characters)
/* 集数隔离：全部集视图按 episode_no 分组；单集视图直接展示当前集 */
const isAllEpisodeView = computed(() => projectStore.currentScriptId === null)
const charactersByEpisode = computed(() => projectStore.charactersByEpisode)
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
      `将从剧本「${script?.title || (script ? '第 ' + script.episode_no + ' 集' : '当前集数')}」中提取角色，是否继续？`,
      '提取角色',
      { type: 'info', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch (_) { return }

  extracting.value = true
  try {
    await projectStore.extractEntitiesFromScript('character', projectStore.currentScriptId)
    ElMessage.success('已提取角色')
  } catch (e: any) {
    ElMessage.error(e?.message || '提取失败')
  } finally {
    extracting.value = false
  }
}

// 跨集复制：把当前角色复制到其他集（不自动切换集数，留在当前集）
async function onCopyTo(entityId: number, targetScriptId: number) {
  if (!projectStore.currentScriptId) return
  try {
    await projectStore.copyEntityTo('character', entityId, targetScriptId)
    ElMessage.success(t('project.copiedToEpisode'))
  } catch (e: any) {
    ElMessage.error(e?.message || '复制失败')
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

<!-- =====================================================
     SceneEditorView —— 3D 场景导演台页面
     功能：
       - 3D 编辑器（拖动相机/主体/灯光）
       - 场景列表：加载/保存/删除/新建
       - 实时预览翻译后的镜头语言 prompt
       - 各维度明细（视角/焦段/构图/光位）
     路由：/scene-editor
     ===================================================== -->

<template>
  <div class="scene-editor-view">
    <h2 class="page-title">{{ t('scene3d.title') }}</h2>
    <p class="page-desc">{{ t('scene3d.desc') }}</p>

    <!-- 顶部工具栏：场景名称 + 操作按钮 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-input
          v-model="currentName"
          :placeholder="t('scene3d.namePlaceholder')"
          style="width: 240px"
        />
        <el-input
          v-model="currentDesc"
          :placeholder="t('scene3d.descPlaceholder')"
          style="width: 280px"
        />
        <el-switch
          v-model="currentIsPublic"
          :active-text="t('scene3d.isPublic')"
        />
        <div class="toolbar-actions">
          <el-button type="primary" :loading="saving" @click="onSave">
            {{ currentId ? t('common.save') : t('scene3d.create') }}
          </el-button>
          <el-button plain @click="onNew">{{ t('scene3d.newScene') }}</el-button>
          <el-button
            v-if="currentId"
            type="danger"
            plain
            :loading="deleting"
            @click="onDelete"
          >
            {{ t('common.delete') }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="main-row">
      <!-- 左侧：3D 编辑器 -->
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="editor-card">
          <Scene3DEditor v-model="sceneData" />
        </el-card>
      </el-col>

      <!-- 右侧：场景列表 + prompt 预览 -->
      <el-col :xs="24" :lg="8">
        <!-- prompt 预览 -->
        <el-card shadow="never" class="preview-card">
          <template #header>
            <span>{{ t('scene3d.promptPreview') }}</span>
          </template>
          <div v-if="promptSuffix" class="prompt-suffix">
            {{ promptSuffix }}
          </div>
          <el-empty v-else :description="t('scene3d.noPrompt')" :image-size="60" />

          <!-- 各维度明细 -->
          <div v-if="promptDetails && Object.keys(promptDetails).length" class="details-list">
            <div class="details-title">{{ t('scene3d.details') }}</div>
            <div v-for="(val, key) in promptDetails" :key="key" class="detail-item">
              <span class="detail-key">{{ detailLabel(String(key)) }}</span>
              <span class="detail-val">{{ val }}</span>
            </div>
          </div>
        </el-card>

        <!-- 场景列表 -->
        <el-card shadow="never" class="list-card">
          <template #header>
            <div class="list-header">
              <span>{{ t('scene3d.sceneList') }}</span>
              <el-input
                v-model="searchKeyword"
                :placeholder="t('common.search')"
                size="small"
                style="width: 140px"
                clearable
                @change="loadScenes"
                @clear="loadScenes"
              />
            </div>
          </template>
          <div v-loading="listLoading" class="scene-list">
            <div
              v-for="s in scenes"
              :key="s.id"
              :class="['scene-item', { active: s.id === currentId }]"
              @click="onSelectScene(s)"
            >
              <div class="scene-item-name">
                {{ s.name }}
                <el-tag v-if="s.is_public" size="small" type="success">
                  {{ t('scene3d.publicTag') }}
                </el-tag>
                <el-tag v-if="s.user_id !== userId && s.is_public" size="small" type="info">
                  {{ t('scene3d.sharedTag') }}
                </el-tag>
              </div>
              <div class="scene-item-desc">{{ s.description || '—' }}</div>
            </div>
            <el-empty v-if="!listLoading && scenes.length === 0" :description="t('common.empty')" :image-size="60" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
/**
 * SceneEditorView —— 3D 场景导演台页面
 * 管理场景 CRUD，并通过 3D 编辑器实时预览翻译后的 prompt。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import Scene3DEditor from '@/components/scene/Scene3DEditor.vue'
import {
  getScenes,
  createScene,
  updateScene,
  deleteScene,
  previewScenePrompt,
} from '@/api/scenes'
import type { Scene3D, SceneData } from '@/types/scene'

const { t } = useI18n()
const userStore = useUserStore()

// ---------- 默认场景数据 ----------
function defaultSceneData(): SceneData {
  return {
    subject: { x: 0, y: 0, z: 0, label: '主体' },
    camera: {
      position: { x: 0, y: 1.6, z: 5 },
      lookAt: { x: 0, y: 0, z: 0 },
      fov: 50,
    },
    lights: [{ type: 'directional', x: 5, y: 8, z: 5, intensity: 1.0 }],
  }
}

// ---------- 当前编辑状态 ----------
const currentId = ref<number | null>(null)
const currentName = ref('')
const currentDesc = ref('')
const currentIsPublic = ref(false)
const sceneData = ref<SceneData>(defaultSceneData())
const saving = ref(false)
const deleting = ref(false)

const userId = computed(() => userStore.user?.id ?? 0)

// ---------- 场景列表 ----------
const scenes = ref<Scene3D[]>([])
const listLoading = ref(false)
const searchKeyword = ref('')

async function loadScenes() {
  listLoading.value = true
  try {
    const res = await getScenes({ page: 1, page_size: 50, search: searchKeyword.value || undefined })
    scenes.value = res.items || []
  } catch (e) {
    // 错误已由 client 统一提示
  } finally {
    listLoading.value = false
  }
}

// ---------- prompt 预览（防抖）----------
const promptSuffix = ref('')
const promptDetails = ref<Record<string, unknown>>({})
let previewTimer: ReturnType<typeof setTimeout> | null = null

async function fetchPreview() {
  try {
    const res = await previewScenePrompt(sceneData.value)
    promptSuffix.value = res.prompt_suffix || ''
    promptDetails.value = res.details || {}
  } catch (e) {
    // 静默失败
  }
}

watch(
  () => sceneData.value,
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(fetchPreview, 300)
  },
  { deep: true },
)

// ---------- 操作：新建/选择/保存/删除 ----------
function onNew() {
  currentId.value = null
  currentName.value = ''
  currentDesc.value = ''
  currentIsPublic.value = false
  sceneData.value = defaultSceneData()
}

async function onSelectScene(s: Scene3D) {
  currentId.value = s.id
  currentName.value = s.name
  currentDesc.value = s.description || ''
  currentIsPublic.value = s.is_public
  // 深拷贝避免直接改列表数据
  sceneData.value = JSON.parse(JSON.stringify(s.scene_data || defaultSceneData()))
}

async function onSave() {
  if (!currentName.value.trim()) {
    ElMessage.warning(t('scene3d.nameRequired'))
    return
  }
  saving.value = true
  try {
    if (currentId.value) {
      await updateScene(currentId.value, {
        name: currentName.value,
        description: currentDesc.value,
        scene_data: sceneData.value,
        is_public: currentIsPublic.value,
      })
      ElMessage.success(t('scene3d.saveSuccess'))
    } else {
      const created = await createScene({
        name: currentName.value,
        description: currentDesc.value,
        scene_data: sceneData.value,
        is_public: currentIsPublic.value,
      })
      currentId.value = created.id
      ElMessage.success(t('scene3d.createSuccess'))
    }
    await loadScenes()
  } catch (e) {
    // 错误已由 client 统一提示
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!currentId.value) return
  try {
    await ElMessageBox.confirm(t('scene3d.deleteConfirm'), t('common.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  deleting.value = true
  try {
    await deleteScene(currentId.value)
    ElMessage.success(t('scene3d.deleteSuccess'))
    onNew()
    await loadScenes()
  } catch (e) {
    // 错误已由 client 统一提示
  } finally {
    deleting.value = false
  }
}

// ---------- 维度明细标签 ----------
function detailLabel(key: string): string {
  const map: Record<string, string> = {
    distance: t('scene3d.detailDistance'),
    angle: t('scene3d.detailAngle'),
    focal: t('scene3d.detailFocal'),
    fov_desc: t('scene3d.detailFov'),
    composition: t('scene3d.detailComposition'),
    light: t('scene3d.detailLight'),
  }
  return map[key] || key
}

onMounted(() => {
  loadScenes()
  fetchPreview()
})
</script>

<style scoped>
.scene-editor-view {
  padding: 16px 24px;
}

.page-title {
  margin: 0 0 4px;
  font-size: 20px;
}

.page-desc {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 13px;
}

.toolbar-card {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.main-row {
  margin-top: 0;
}

.editor-card :deep(.el-card__body) {
  padding: 0;
}

.editor-card {
  height: 560px;
}

.editor-card :deep(.scene3d-editor) {
  height: 560px;
  border: none;
  border-radius: 0;
}

.preview-card,
.list-card {
  margin-bottom: 16px;
}

.prompt-suffix {
  padding: 12px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary, #303133);
  word-break: break-all;
}

.details-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color, #dcdfe6);
}

.details-title {
  font-size: 13px;
  color: var(--el-text-color-secondary, #909399);
  margin-bottom: 8px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 3px 0;
}

.detail-key {
  color: var(--el-text-color-secondary, #909399);
}

.detail-val {
  color: var(--el-text-color-primary, #303133);
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.scene-list {
  max-height: 320px;
  overflow-y: auto;
}

.scene-item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.scene-item:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}

.scene-item.active {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.scene-item-name {
  font-size: 14px;
  color: var(--el-text-color-primary, #303133);
  display: flex;
  align-items: center;
  gap: 6px;
}

.scene-item-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-top: 2px;
}
</style>

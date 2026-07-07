<!-- =====================================================
     项目管理视图 ProjectManagerView
     - 顶部集数切换器（currentScriptId 驱动四类资源过滤）
     - Tab 容器：剧本 / 角色 / 场景 / 道具 / 分镜 / 时间线
     - 每个 Tab 内部由对应 Tab 组件实现
     - 顶部展示批量操作工具栏（透传给子 Tab）
     ===================================================== -->

<template>
  <div class="project-manager-view">
    <!-- 集数切换器：切换后由 store.setCurrentScript 自动拉取四类资源 -->
    <div class="episode-switcher-bar">
      <span class="label">{{ t('project.currentEpisode') }}</span>
      <el-select
        v-model="currentScriptId"
        :placeholder="t('project.selectEpisode')"
        @change="onScriptChange"
        style="width: 260px"
      >
        <el-option :label="t('project.allEpisodes')" :value="null" />
        <el-option
          v-for="script in projectStore.scripts"
          :key="script.id"
          :label="`第${script.episode_no}集：${script.title || ''}`"
          :value="script.id"
        />
      </el-select>
    </div>

    <el-tabs v-model="activeTab" class="manager-tabs" type="border-card">
      <el-tab-pane name="script">
        <template #label>
          <span class="tab-label">
            <el-icon><Document /></el-icon> 剧本
            <el-badge v-if="scriptCount > 0" :value="scriptCount" class="tab-badge" />
          </span>
        </template>
        <ScriptTab />
      </el-tab-pane>

      <el-tab-pane name="character">
        <template #label>
          <span class="tab-label">
            <el-icon><User /></el-icon> 角色
            <el-badge v-if="characterCount > 0" :value="characterCount" class="tab-badge" />
          </span>
        </template>
        <CharactersTab />
      </el-tab-pane>

      <el-tab-pane name="scene">
        <template #label>
          <span class="tab-label">
            <el-icon><Picture /></el-icon> 场景
            <el-badge v-if="sceneCount > 0" :value="sceneCount" class="tab-badge" />
          </span>
        </template>
        <ScenesTab />
      </el-tab-pane>

      <el-tab-pane name="prop">
        <template #label>
          <span class="tab-label">
            <el-icon><Box /></el-icon> 道具
            <el-badge v-if="propCount > 0" :value="propCount" class="tab-badge" />
          </span>
        </template>
        <PropsTab />
      </el-tab-pane>

      <el-tab-pane name="shot">
        <template #label>
          <span class="tab-label">
            <el-icon><Film /></el-icon> 分镜
            <el-badge v-if="shotCount > 0" :value="shotCount" class="tab-badge" />
          </span>
        </template>
        <ShotsTab />
      </el-tab-pane>

      <el-tab-pane name="timeline">
        <template #label>
          <span class="tab-label">
            <el-icon><VideoCamera /></el-icon> 时间线
          </span>
        </template>
        <TimelineTab />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Document, User, Picture, Box, Film, VideoCamera } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useProjectStore } from '@/stores/project'
import ScriptTab from './ScriptTab.vue'
import CharactersTab from './CharactersTab.vue'
import ScenesTab from './ScenesTab.vue'
import PropsTab from './PropsTab.vue'
import ShotsTab from './ShotsTab.vue'
import TimelineTab from './timeline/TimelineTab.vue'

const projectStore = useProjectStore()
const { t } = useI18n()

// 默认展示剧本 Tab
const activeTab = ref<'script' | 'character' | 'scene' | 'prop' | 'shot' | 'timeline'>('script')

// 集数切换器：本地 ref 与 store.currentScriptId 同步
// 用本地 ref 而非直接绑定 store state，是因为 el-select v-model 需要可写引用
const currentScriptId = ref<number | null>(projectStore.currentScriptId)

// 切换集数：交给 store.setCurrentScript 拉取四类资源
async function onScriptChange(val: number | null) {
  await projectStore.setCurrentScript(val)
}

// 首次进入默认选中第一集，避免一进来就拉全量
onMounted(async () => {
  if (projectStore.currentScriptId === null && projectStore.scripts.length > 0) {
    currentScriptId.value = projectStore.scripts[0].id
    await projectStore.setCurrentScript(projectStore.scripts[0].id)
  }
})

// 各实体数量
const scriptCount = computed(() => projectStore.scripts.length)
const characterCount = computed(() => projectStore.characters.length)
const sceneCount = computed(() => projectStore.scenes.length)
const propCount = computed(() => projectStore.props.length)
const shotCount = computed(() => projectStore.shots.length)
</script>

<style scoped>
.project-manager-view {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 20px;
}

/* 集数切换器条 */
.episode-switcher-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.episode-switcher-bar .label {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.manager-tabs {
  height: 100%;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-badge {
  margin-left: 4px;
}

/* 让 Tab 内容铺满剩余高度 */
:deep(.el-tabs__content) {
  padding: 16px;
}

:deep(.el-tab-pane) {
  min-height: 320px;
}
</style>

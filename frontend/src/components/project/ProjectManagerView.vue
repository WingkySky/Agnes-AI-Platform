<!-- =====================================================
     项目管理视图 ProjectManagerView
     - Tab 容器：剧本 / 角色 / 场景 / 道具 / 分镜
     - 每个 Tab 内部由对应 Tab 组件实现
     - 顶部展示批量操作工具栏（透传给子 Tab）
     ===================================================== -->

<template>
  <div class="project-manager-view">
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
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Document, User, Picture, Box, Film } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import ScriptTab from './ScriptTab.vue'
import CharactersTab from './CharactersTab.vue'
import ScenesTab from './ScenesTab.vue'
import PropsTab from './PropsTab.vue'
import ShotsTab from './ShotsTab.vue'

const projectStore = useProjectStore()

// 默认展示剧本 Tab
const activeTab = ref<'script' | 'character' | 'scene' | 'prop' | 'shot'>('script')

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

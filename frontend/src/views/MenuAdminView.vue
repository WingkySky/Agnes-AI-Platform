<!--
  菜单管理页面
  - 完全用户友好，不需要填写代码字段
  - 所有可用菜单项已预设好（名称、图标、路径固定）
  - 管理员只需配置：是否在顶部显示、是否在侧边栏显示、侧边栏分组、排序
  - 带实时预览
-->

<template>
  <div class="menu-admin-page">
    <div class="page-header">
      <div>
        <h1>{{ t('menuAdmin.pageTitle') }}</h1>
        <p class="page-desc">{{ t('menuAdmin.pageDesc') }}</p>
      </div>
      <div class="header-actions">
        <el-button @click="handleReset">
          <el-icon><RefreshRight /></el-icon>
          {{ t('menuAdmin.reset') }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          <el-icon><Check /></el-icon>
          {{ t('common.save') }}
        </el-button>
      </div>
    </div>

    <el-table
      :data="menuStore.allMenuItems"
      stripe
      border
      style="width: 100%"
      :row-key="'key'"
    >
      <el-table-column :label="t('menuAdmin.itemName')" min-width="220">
        <template #default="{ row }">
          <div class="menu-item-preview">
            <el-icon v-if="row.icon" class="menu-icon">
              <component :is="getIcon(row.icon)" />
            </el-icon>
            <div class="menu-info">
              <div class="menu-name">{{ currentLang === 'zh' ? row.label_zh : row.label_en }}</div>
              <div class="menu-path">{{ row.path }}</div>
            </div>
            <el-tag v-if="row.require_admin" type="warning" size="small">
              {{ t('menuAdmin.adminOnly') }}
            </el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.showInTop')" width="120" align="center">
        <template #default="{ row }">
          <el-switch v-model="configMap[row.key].show_in_top" />
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.topGroup')" width="140">
        <template #default="{ row }">
          <el-select
            v-model="configMap[row.key].top_group_key"
            style="width: 100%"
            :disabled="!configMap[row.key].show_in_top"
            :placeholder="t('menuAdmin.selectTopGroup')"
          >
            <el-option
              v-for="group in topNavGroups"
              :key="group.key"
              :label="currentLang === 'zh' ? group.label_zh : group.label_en"
              :value="group.key"
            />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.topSort')" width="110" align="center">
        <template #default="{ row }">
          <el-input-number
            v-model="configMap[row.key].top_sort_order"
            :min="1"
            :max="100"
            size="small"
            controls-position="right"
            style="width: 100px"
            :disabled="!configMap[row.key].show_in_top"
          />
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.showInSidebar')" width="120" align="center">
        <template #default="{ row }">
          <el-switch v-model="configMap[row.key].show_in_sidebar" />
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.sidebarGroup')" width="160">
        <template #default="{ row }">
          <el-select
            v-model="configMap[row.key].sidebar_group_key"
            style="width: 100%"
            :disabled="!configMap[row.key].show_in_sidebar"
            :placeholder="t('menuAdmin.selectGroup')"
          >
            <el-option
              v-for="group in sidebarGroups"
              :key="group.key"
              :label="currentLang === 'zh' ? group.label_zh : group.label_en"
              :value="group.key"
            />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column :label="t('menuAdmin.sidebarSort')" width="110" align="center">
        <template #default="{ row }">
          <el-input-number
            v-model="configMap[row.key].sidebar_sort_order"
            :min="1"
            :max="100"
            size="small"
            controls-position="right"
            style="width: 100px"
            :disabled="!configMap[row.key].show_in_sidebar"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 预览区域 -->
    <div class="preview-section">
      <h2>{{ t('menuAdmin.preview') }}</h2>
      
      <div class="preview-box">
        <div class="preview-header">
          <div class="preview-nav">
            <span class="preview-brand">Agnes AI</span>
            <div class="preview-nav-items">
              <template v-for="group in previewTopNav" :key="group.key">
                <!-- 单菜单项：直接显示标签 -->
                <el-tag
                  v-if="group.items.length === 1"
                  size="small"
                  type="primary"
                  effect="plain"
                  class="preview-tag"
                >
                  <el-icon v-if="group.items[0].icon"><component :is="getIcon(group.items[0].icon)" /></el-icon>
                  {{ group.items[0].label }}
                </el-tag>

                <!-- 多菜单项：下拉分组 -->
                <el-dropdown
                  v-else
                  trigger="hover"
                  placement="bottom"
                >
                  <span class="preview-nav-group">
                    <el-icon v-if="group.icon"><component :is="getIcon(group.icon)" /></el-icon>
                    {{ group.label }}
                    <el-icon class="preview-arrow"><ArrowDown /></el-icon>
                  </span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="item in group.items"
                        :key="item.key"
                      >
                        <el-icon v-if="item.icon"><component :is="getIcon(item.icon)" /></el-icon>
                        {{ item.label }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </div>
          </div>
        </div>
        <div class="preview-body">
          <div class="preview-sidebar">
            <el-menu
              class="preview-menu"
              background-color="#fafafa"
              text-color="#606266"
              active-text-color="#409eff"
              :unique-opened="false"
            >
              <el-sub-menu
                v-for="groupData in previewSidebarGroups"
                :key="groupData.key"
                :index="`preview-group-${groupData.key}`"
                v-show="groupData.items.length > 0"
              >
                <template #title>
                  <el-icon v-if="groupData.icon"><component :is="getIcon(groupData.icon)" /></el-icon>
                  <span>{{ groupData.label }}</span>
                </template>
                <el-menu-item
                  v-for="item in groupData.items"
                  :key="item.key"
                  :index="item.key"
                >
                  <el-icon v-if="item.icon"><component :is="getIcon(item.icon)" /></el-icon>
                  <template #title>{{ item.label }}</template>
                </el-menu-item>
              </el-sub-menu>
            </el-menu>
          </div>
          <div class="preview-content">
            <el-empty :description="t('menuAdmin.previewArea')" :image-size="80" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshRight, Check, ArrowDown } from '@element-plus/icons-vue'
import * as ElementPlusIcons from '@element-plus/icons-vue'
import { useMenuStore } from '@/stores/menu'
import {
  SIDEBAR_GROUPS,
  TOP_NAV_GROUPS,
  resolveMenus,
  type MenuItemConfig,
  type AdminMenuItem,
} from '@/config/menus'

const { t, locale } = useI18n()
const menuStore = useMenuStore()

const saving = ref(false)

// 配置映射（key -> config），本地编辑用
const configMap = reactive<Record<string, MenuItemConfig>>({})

// 侧边栏分组
const sidebarGroups = SIDEBAR_GROUPS

// 顶部导航分组
const topNavGroups = TOP_NAV_GROUPS

const currentLang = computed(() => locale.value.startsWith('zh') ? 'zh' : 'en')

function getIcon(iconName: string | null) {
  if (!iconName) return null
  return (ElementPlusIcons as any)[iconName]
}

// 初始化配置映射
function initConfigMap() {
  for (const item of menuStore.allMenuItems) {
    configMap[item.key] = {
      key: item.key,
      show_in_top: item.show_in_top,
      show_in_sidebar: item.show_in_sidebar,
      top_group_key: item.top_group_key,
      sidebar_group_key: item.sidebar_group_key,
      top_sort_order: item.top_sort_order,
      sidebar_sort_order: item.sidebar_sort_order,
    }
  }
}

// 保存配置
async function handleSave() {
  try {
    await ElMessageBox.confirm(
      t('menuAdmin.confirmSave'),
      t('common.tip'),
      { type: 'info' }
    )

    saving.value = true
    const configs = Object.values(configMap)
    await menuStore.saveConfigs(configs)
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || t('menuAdmin.saveFailed'))
    }
  } finally {
    saving.value = false
  }
}

// 重置为默认
async function handleReset() {
  try {
    await ElMessageBox.confirm(
      t('menuAdmin.confirmReset'),
      t('common.tip'),
      { type: 'warning' }
    )
    await menuStore.resetToDefault()
    initConfigMap()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || t('menuAdmin.resetFailed'))
    }
  }
}

// 预览数据
const previewConfigs = computed<MenuItemConfig[]>(() => Object.values(configMap))

const previewTopNav = computed(() => {
  const { topNav } = resolveMenus(previewConfigs.value, true, locale.value)
  return topNav
})

const previewSidebarGroups = computed(() => {
  const { sidebar } = resolveMenus(previewConfigs.value, true, locale.value)
  return Object.values(sidebar).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
})

onMounted(() => {
  initConfigMap()
})
</script>

<style scoped>
.menu-admin-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.page-desc {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.menu-item-preview {
  display: flex;
  align-items: center;
  gap: 12px;
}

.menu-icon {
  font-size: 18px;
  color: #409eff;
}

.menu-info {
  flex: 1;
}

.menu-name {
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.menu-path {
  font-size: 12px;
  color: #909399;
  font-family: monospace;
}

/* 预览区域 */
.preview-section {
  margin-top: 24px;
}

.preview-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.preview-box {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
}

.preview-header {
  background: #f5f7fa;
  border-bottom: 1px solid #dcdfe6;
  padding: 0 16px;
}

.preview-nav {
  display: flex;
  align-items: center;
  height: 56px;
  gap: 24px;
}

.preview-brand {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

.preview-nav-items {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preview-nav-group {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
}

.preview-nav-group .el-icon {
  font-size: 14px;
}

.preview-arrow {
  font-size: 10px;
  opacity: 0.7;
}

.preview-tag {
  display: flex;
  align-items: center;
  gap: 4px;
}

.preview-body {
  display: flex;
  min-height: 400px;
}

.preview-sidebar {
  width: 220px;
  background: #fafafa;
  border-right: 1px solid #dcdfe6;
  padding: 8px 0;
}

.preview-menu {
  border-right: none !important;
}

.preview-menu :deep(.el-sub-menu__title) {
  height: 38px;
  line-height: 38px;
  border-radius: 6px;
  margin: 0 4px;
  font-weight: 500;
}

.preview-menu :deep(.el-menu-item) {
  height: 34px;
  line-height: 34px;
  border-radius: 6px;
  margin: 0 8px 2px 8px;
  font-size: 13px;
}

.preview-menu :deep(.el-menu-item .el-icon),
.preview-menu :deep(.el-sub-menu__title .el-icon) {
  font-size: 16px;
  margin-right: 8px;
}

.preview-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
}
</style>

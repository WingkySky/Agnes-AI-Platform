<!--
  菜单管理页面
  - 完全用户友好，不需要填写代码字段
  - 所有可用菜单项已预设好（名称、图标、路径固定）
  - 管理员只需配置：是否在顶部显示、是否在侧边栏显示、分组、排序
  - 支持自定义顶部导航和侧边栏分组名称、图标
  - 带实时预览
  - 使用标签页+分组切换布局，避免页面过长
-->

<template>
  <div class="menu-admin-wrap">
    <!-- 页面头部：标题+描述在左，操作按钮在右 -->
    <header class="page-head">
      <div>
        <h2>{{ t('nav.menuAdmin') }}</h2>
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
    </header>

    <el-card class="content-card" shadow="never">
      <el-tabs v-model="activeTab" class="menu-admin-tabs">
        <!-- 分组配置标签页 -->
        <el-tab-pane :label="t('menuAdmin.tabGroups')" name="groups">
          <!-- 分组类型切换：顶部导航/侧边栏 -->
          <div class="group-type-switch">
            <el-radio-group v-model="activeGroupType" size="large">
              <el-radio-button label="top">
                <el-icon><Menu /></el-icon>
                <span>{{ t('menuAdmin.topNavGroups') }}</span>
              </el-radio-button>
              <el-radio-button label="sidebar">
                <el-icon><Grid /></el-icon>
                <span>{{ t('menuAdmin.sidebarGroups') }}</span>
              </el-radio-button>
            </el-radio-group>
            <p class="switch-desc">{{ activeGroupType === 'top' ? t('menuAdmin.topNavGroupsDesc') : t('menuAdmin.sidebarGroupsDesc') }}</p>
          </div>

          <!-- 分组卡片网格 -->
          <div class="group-config-grid">
            <template v-for="group in activeGroups" :key="group.key">
              <div class="group-config-card">
                <div class="group-config-header">
                  <el-icon class="group-icon" :size="18">
                    <component :is="getIcon(group.custom_icon || group.icon)" />
                  </el-icon>
                  <span class="group-key">{{ group.key }}</span>
                </div>
                <el-form :model="group" label-position="top" size="small" class="group-form">
                  <div class="form-row">
                    <el-form-item :label="t('menuAdmin.groupNameZh')" class="form-item-compact">
                      <el-input
                        v-model="group.custom_label_zh"
                        :placeholder="group.label_zh"
                        clearable
                      />
                    </el-form-item>
                    <el-form-item :label="t('menuAdmin.groupNameEn')" class="form-item-compact">
                      <el-input
                        v-model="group.custom_label_en"
                        :placeholder="group.label_en"
                        clearable
                      />
                    </el-form-item>
                  </div>
                  <el-form-item :label="t('menuAdmin.groupIcon')" class="form-item-compact">
                    <el-select
                      v-model="group.custom_icon"
                      filterable
                      allow-create
                      default-first-option
                      :placeholder="group.icon"
                      clearable
                      style="width: 100%"
                    >
                      <el-option
                        v-for="iconName in availableIcons"
                        :key="iconName"
                        :label="iconName"
                        :value="iconName"
                      >
                        <div class="icon-option">
                          <el-icon><component :is="getIcon(iconName)" /></el-icon>
                          <span>{{ iconName }}</span>
                        </div>
                      </el-option>
                    </el-select>
                  </el-form-item>
                  <div class="group-preview-name">
                    {{ t('menuAdmin.previewName') }}:
                    <strong>{{ getGroupDisplayName(group) }}</strong>
                  </div>
                </el-form>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <!-- 菜单项配置标签页 -->
        <el-tab-pane :label="t('menuAdmin.tabItems')" name="items">
          <el-table
            :data="menuStore.allMenuItems"
            stripe
            border
            style="width: 100%"
            :row-key="'key'"
            size="small"
            :max-height="tableMaxHeight"
          >
            <el-table-column :label="t('menuAdmin.itemName')" min-width="200">
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

            <el-table-column :label="t('menuAdmin.showInTop')" width="90" align="center">
              <template #default="{ row }">
                <el-switch v-model="configMap[row.key].show_in_top" size="small" />
              </template>
            </el-table-column>

            <el-table-column :label="t('menuAdmin.topGroup')" width="140">
              <template #default="{ row }">
                <el-select
                  v-model="configMap[row.key].top_group_key"
                  size="small"
                  style="width: 100%"
                  :disabled="!configMap[row.key].show_in_top"
                  :placeholder="t('menuAdmin.selectTopGroup')"
                >
                  <el-option
                    v-for="group in topGroupConfigs"
                    :key="group.key"
                    :label="getGroupDisplayName(group)"
                    :value="group.key"
                  />
                </el-select>
              </template>
            </el-table-column>

            <el-table-column :label="t('menuAdmin.topSort')" width="90" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-model="configMap[row.key].top_sort_order"
                  :min="1"
                  :max="100"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                  :disabled="!configMap[row.key].show_in_top"
                />
              </template>
            </el-table-column>

            <el-table-column :label="t('menuAdmin.showInSidebar')" width="90" align="center">
              <template #default="{ row }">
                <el-switch v-model="configMap[row.key].show_in_sidebar" size="small" />
              </template>
            </el-table-column>

            <el-table-column :label="t('menuAdmin.sidebarGroup')" width="140">
              <template #default="{ row }">
                <el-select
                  v-model="configMap[row.key].sidebar_group_key"
                  size="small"
                  style="width: 100%"
                  :disabled="!configMap[row.key].show_in_sidebar"
                  :placeholder="t('menuAdmin.selectGroup')"
                >
                  <el-option
                    v-for="group in sidebarGroupConfigs"
                    :key="group.key"
                    :label="getGroupDisplayName(group)"
                    :value="group.key"
                  />
                </el-select>
              </template>
            </el-table-column>

            <el-table-column :label="t('menuAdmin.sidebarSort')" width="90" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-model="configMap[row.key].sidebar_sort_order"
                  :min="1"
                  :max="100"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                  :disabled="!configMap[row.key].show_in_sidebar"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 实时预览标签页 -->
        <el-tab-pane :label="t('menuAdmin.tabPreview')" name="preview">
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
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  RefreshRight, Check, ArrowDown, Menu, Grid,
  EditPen, User, Connection, Setting, Picture, VideoPlay,
  ChatDotRound, Clock, Coin, StarFilled, Histogram, Message,
  UserFilled, MoreFilled,
} from '@element-plus/icons-vue'
import * as ElementPlusIcons from '@element-plus/icons-vue'
import { useMenuStore } from '@/stores/menu'
import {
  resolveMenus,
  type MenuItemConfig,
  type MenuGroupConfig,
  type AdminMenuGroup,
} from '@/config/menus'

const { t, locale } = useI18n()
const menuStore = useMenuStore()

const saving = ref(false)

// 当前标签页
const activeTab = ref<'groups' | 'items' | 'preview'>('groups')
// 当前显示的分组类型（顶部导航/侧边栏）
const activeGroupType = ref<'top' | 'sidebar'>('top')
// 表格最大高度
const tableMaxHeight = ref(500)

// 可用图标列表（常用图标）
const availableIcons = [
  'EditPen', 'Picture', 'VideoPlay', 'ChatDotRound', 'Grid',
  'User', 'UserFilled', 'Setting', 'Coin', 'StarFilled',
  'Histogram', 'Clock', 'Connection', 'Message', 'Menu',
  'MoreFilled', 'HomeFilled', 'Document', 'Folder', 'DataAnalysis',
  'Platform', 'MagicStick', 'Compass', 'Medal', 'Trophy',
]

// 分组本地编辑状态
interface EditableGroupConfig extends AdminMenuGroup {
  custom_label_zh: string | null
  custom_label_en: string | null
  custom_icon: string | null
}

const topGroupConfigs = ref<EditableGroupConfig[]>([])
const sidebarGroupConfigs = ref<EditableGroupConfig[]>([])

/** 当前激活的分组列表（根据activeGroupType切换） */
const activeGroups = computed(() => {
  return activeGroupType.value === 'top' ? topGroupConfigs.value : sidebarGroupConfigs.value
})

// 菜单项配置映射（key -> config），本地编辑用
const configMap = reactive<Record<string, MenuItemConfig>>({})

const currentLang = computed(() => locale.value.startsWith('zh') ? 'zh' : 'en')

function getIcon(iconName: string | null | undefined) {
  if (!iconName) return null
  return (ElementPlusIcons as any)[iconName] || null
}

/** 获取分组显示名称（考虑自定义名称） */
function getGroupDisplayName(group: EditableGroupConfig | AdminMenuGroup): string {
  if (currentLang.value === 'zh') {
    return (group as any).custom_label_zh || group.label_zh
  }
  return (group as any).custom_label_en || group.label_en
}

/** 计算表格最大高度 */
function updateTableHeight() {
  const viewportHeight = window.innerHeight
  tableMaxHeight.value = Math.max(400, viewportHeight - 320)
}

/** 初始化分组配置编辑状态 */
function initGroupConfigs() {
  topGroupConfigs.value = menuStore.allTopNavGroups.map(g => ({
    ...g,
    custom_label_zh: g.custom_label_zh,
    custom_label_en: g.custom_label_en,
    custom_icon: g.custom_icon,
  }))
  sidebarGroupConfigs.value = menuStore.allSidebarGroups.map(g => ({
    ...g,
    custom_label_zh: g.custom_label_zh,
    custom_label_en: g.custom_label_en,
    custom_icon: g.custom_icon,
  }))
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

/** 从编辑状态构建分组配置数组 */
function buildGroupConfigs(): MenuGroupConfig[] {
  const groups: MenuGroupConfig[] = []

  for (const g of topGroupConfigs.value) {
    if (g.custom_label_zh || g.custom_label_en || g.custom_icon) {
      groups.push({
        key: g.key,
        type: 'top',
        label_zh: g.custom_label_zh || null,
        label_en: g.custom_label_en || null,
        icon: g.custom_icon || null,
      })
    }
  }

  for (const g of sidebarGroupConfigs.value) {
    if (g.custom_label_zh || g.custom_label_en || g.custom_icon) {
      groups.push({
        key: g.key,
        type: 'sidebar',
        label_zh: g.custom_label_zh || null,
        label_en: g.custom_label_en || null,
        icon: g.custom_icon || null,
      })
    }
  }

  return groups
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
    const itemConfigs = Object.values(configMap)
    const groupConfigs = buildGroupConfigs()
    await menuStore.saveConfigs(itemConfigs, groupConfigs)
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
    initGroupConfigs()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || t('menuAdmin.resetFailed'))
    }
  }
}

// 预览数据：构建临时配置用于预览
const previewConfigs = computed(() => {
  const items: MenuItemConfig[] = Object.values(configMap)
  const groups: MenuGroupConfig[] = buildGroupConfigs()
  return { items, groups }
})

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
  initGroupConfigs()
  updateTableHeight()
  window.addEventListener('resize', updateTableHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateTableHeight)
})
</script>

<style scoped>
/* 参照其他管理页面的标准布局 */
.menu-admin-wrap {
  max-width: 100%;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.page-head h2 {
  margin: 0 0 6px 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.page-desc {
  margin: 0;
  color: var(--agnes-text-secondary);
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.content-card {
  border-radius: 10px;
}

/* 分组配置区域 */
.group-type-switch {
  margin-bottom: 20px;
}

.switch-desc {
  margin: 10px 0 0 0;
  color: var(--agnes-text-secondary);
  font-size: 13px;
}

.group-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.group-config-card {
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  padding: 14px;
  background: var(--agnes-bg-base);
  transition: all 0.2s ease;
}

.group-config-card:hover {
  border-color: var(--agnes-accent);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.group-config-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.group-icon {
  color: var(--agnes-accent);
}

.group-key {
  font-size: 11px;
  font-family: monospace;
  color: var(--agnes-text-muted);
  background: var(--agnes-bg-elevated);
  padding: 2px 8px;
  border-radius: 4px;
}

.group-form {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.form-item-compact {
  margin-bottom: 12px;
}

.form-item-compact:last-child {
  margin-bottom: 8px;
}

.group-preview-name {
  margin-top: 4px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
}

.group-preview-name strong {
  color: var(--agnes-text-primary);
  font-weight: 600;
}

.icon-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 菜单项预览 */
.menu-item-preview {
  display: flex;
  align-items: center;
  gap: 10px;
}

.menu-icon {
  font-size: 16px;
  color: var(--agnes-accent);
  flex-shrink: 0;
}

.menu-info {
  flex: 1;
  min-width: 0;
}

.menu-name {
  font-weight: 500;
  color: var(--agnes-text-primary);
  margin-bottom: 1px;
  font-size: 13px;
}

.menu-path {
  font-size: 11px;
  color: var(--agnes-text-muted);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 预览区域 */
.preview-box {
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  overflow: hidden;
}

.preview-header {
  background: var(--agnes-bg-elevated);
  border-bottom: 1px solid var(--agnes-border);
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
  color: var(--agnes-text-primary);
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
  background: var(--agnes-accent-light);
  color: var(--agnes-accent);
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
  background: var(--agnes-bg-base);
  border-right: 1px solid var(--agnes-border);
  padding: 8px 0;
}

.preview-menu {
  border-right: none !important;
  background: transparent !important;
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
  background: var(--agnes-bg-elevated);
}
</style>

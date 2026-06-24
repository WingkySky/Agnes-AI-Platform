<!-- =====================================================
     管理中心布局 AdminLayout
     - 左侧侧边栏：按分组展示管理菜单
     - 右侧内容区：<router-view> 渲染具体管理页面
     - 菜单项根据权限动态显示
     ===================================================== -->

<template>
  <div class="admin-layout">
    <!-- 左侧侧边栏 -->
    <aside class="admin-sidebar">
      <div class="sidebar-header">
        <el-icon class="sidebar-icon"><Setting /></el-icon>
        <span class="sidebar-title">{{ t('admin.center') }}</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu"
        :collapse="false"
        @select="handleMenuSelect">
        <!-- 内容审核组 -->
        <template v-if="showModerationGroup">
          <el-menu-item-group>
            <template #title>
              <span class="menu-group-title">{{ t('admin.groupModeration') }}</span>
            </template>
            <el-menu-item
              v-if="permissionStore.hasPermission('plaza:moderate')"
              index="/admin/moderation">
              <el-icon><View /></el-icon>
              <span>{{ t('nav.moderation') }}</span>
            </el-menu-item>
            <el-menu-item
              v-if="permissionStore.hasPermission('moderation:config')"
              index="/admin/sensitive-words">
              <el-icon><Warning /></el-icon>
              <span>{{ t('nav.sensitiveWords') }}</span>
            </el-menu-item>
          </el-menu-item-group>
        </template>

        <!-- 用户权限组 -->
        <template v-if="showUserGroup">
          <el-menu-item-group>
            <template #title>
              <span class="menu-group-title">{{ t('admin.groupUsers') }}</span>
            </template>
            <el-menu-item
              v-if="permissionStore.hasPermission('role:manage')"
              index="/admin/roles">
              <el-icon><UserFilled /></el-icon>
              <span>{{ t('nav.roleManage') }}</span>
            </el-menu-item>
            <el-menu-item
              v-if="userStore.isAdmin"
              index="/admin/users">
              <el-icon><User /></el-icon>
              <span>{{ t('nav.usersAdmin') }}</span>
            </el-menu-item>
          </el-menu-item-group>
        </template>

        <!-- 系统配置组 -->
        <template v-if="showConfigGroup">
          <el-menu-item-group>
            <template #title>
              <span class="menu-group-title">{{ t('admin.groupSystem') }}</span>
            </template>
            <el-menu-item
              v-if="permissionStore.hasPermission('watermark:manage')"
              index="/admin/watermark">
              <el-icon><Picture /></el-icon>
              <span>{{ t('nav.watermarkConfig') }}</span>
            </el-menu-item>
            <el-menu-item
              v-if="userStore.isAdmin"
              index="/admin/credit-rules">
              <el-icon><Coin /></el-icon>
              <span>{{ t('nav.creditRules') }}</span>
            </el-menu-item>
            <el-menu-item
              v-if="userStore.isAdmin"
              index="/admin/models">
              <el-icon><Cpu /></el-icon>
              <span>{{ t('admin.modelConfig') }}</span>
            </el-menu-item>
            <el-menu-item
              v-if="userStore.isAdmin"
              index="/admin/email">
              <el-icon><Message /></el-icon>
              <span>{{ t('admin.emailConfig') }}</span>
            </el-menu-item>
          </el-menu-item-group>
        </template>
      </el-menu>
    </aside>

    <!-- 右侧内容区 -->
    <main class="admin-content">
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Setting, View, Warning, UserFilled, User,
  Picture, Coin, Cpu, Message,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permission'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()

// 当前激活的菜单
const activeMenu = computed(() => route.path)

// 内容审核组是否显示
const showModerationGroup = computed(() => {
  return permissionStore.hasPermission('plaza:moderate') ||
    permissionStore.hasPermission('moderation:config')
})

// 用户权限组是否显示
const showUserGroup = computed(() => {
  return permissionStore.hasPermission('role:manage') || userStore.isAdmin
})

// 系统配置组是否显示
const showConfigGroup = computed(() => {
  return permissionStore.hasPermission('watermark:manage') || userStore.isAdmin
})

// keep-alive 缓存的管理页面
const cachedViews = [
  'ModerationView',
  'SensitiveWordsView',
  'RolesAdminView',
  'UsersAdminView',
  'WatermarkConfigView',
  'CreditRulesView',
  'SettingsView',
  'EmailConfigView',
]

// 菜单点击跳转
function handleMenuSelect(index: string) {
  if (route.path !== index) {
    router.push(index)
  }
}

// 初始化：如果当前就是 /admin 根路径，自动跳转到第一个有权限的页面
onMounted(() => {
  if (route.path === '/admin' || route.path === '/admin/') {
    const firstPage = firstAccessiblePage.value
    if (firstPage) {
      router.replace(firstPage)
    }
  }
})

// 计算第一个可访问的管理页面
const firstAccessiblePage = computed(() => {
  if (permissionStore.hasPermission('plaza:moderate')) return '/admin/moderation'
  if (permissionStore.hasPermission('moderation:config')) return '/admin/sensitive-words'
  if (permissionStore.hasPermission('role:manage')) return '/admin/roles'
  if (userStore.isAdmin) return '/admin/users'
  if (permissionStore.hasPermission('watermark:manage')) return '/admin/watermark'
  if (userStore.isAdmin) return '/admin/credit-rules'
  if (userStore.isAdmin) return '/admin/models'
  if (userStore.isAdmin) return '/admin/email'
  return null
})
</script>

<style scoped>
/* =====================================================
 * 管理中心布局样式
 * ===================================================== */
.admin-layout {
  display: flex;
  height: 100%;
  min-height: calc(100vh - 120px);
  gap: 24px;
}

/* ---- 左侧侧边栏 ---- */
.admin-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 12px;
  padding: 16px 0;
  box-sizing: border-box;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px 16px;
  border-bottom: 1px solid var(--agnes-border-faint);
  margin-bottom: 8px;
}

.sidebar-icon {
  font-size: 20px;
  color: var(--agnes-accent);
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.sidebar-menu {
  border-right: none;
  background: transparent;
}

/* 分组标题 */
.menu-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--agnes-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 菜单项样式覆盖 */
:deep(.el-menu) {
  background: transparent;
}

:deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin: 2px 8px;
  border-radius: 8px;
  color: var(--agnes-text-secondary);
}

:deep(.el-menu-item:hover) {
  background: var(--agnes-nav-hover-bg);
  color: var(--agnes-text-primary);
}

:deep(.el-menu-item.is-active) {
  background: var(--agnes-primary-bg-soft);
  color: var(--agnes-primary);
}

:deep(.el-menu-item .el-icon) {
  margin-right: 10px;
  font-size: 18px;
}

:deep(.el-menu-item-group__title) {
  padding: 12px 20px 6px;
}

/* ---- 右侧内容区 ---- */
.admin-content {
  flex: 1;
  min-width: 0;
  overflow: auto;
}

@media (max-width: 900px) {
  .admin-layout {
    flex-direction: column;
    gap: 16px;
  }

  .admin-sidebar {
    width: 100%;
  }
}
</style>

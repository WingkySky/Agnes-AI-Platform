/* =====================================================
 * 菜单配置 Store
 *
 * 负责：
 *   - 使用前端内置菜单配置作为默认（确保菜单一定能显示）
 *   - 从后端拉取用户自定义配置（显示/位置/排序/分组）覆盖默认
 *   - 本地缓存配置（localStorage，避免每次刷新都请求）
 *   - 管理员：菜单配置管理操作
 *
 * 设计理念：
 *   - 所有菜单项在前端固定定义（key、名称、图标、路径、权限）
 *   - 用户只需要配置：哪些显示、放顶部还是侧边栏、排序、分组
 *   - 完全没有代码化字段需要用户填写
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getMenuConfigs,
  saveMenuConfigs,
  resetMenuConfigs,
} from '@/api/menu'
import {
  DEFAULT_MENU_CONFIG,
  resolveMenus,
  getAllMenuItemsForAdmin,
  type MenuItemConfig,
  type AdminMenuItem,
} from '@/config/menus'
import { useUserStore } from './user'
import { useI18n } from '@/i18n'

// 缓存 key 和版本号
const MENU_CONFIG_CACHE_KEY = 'agnes.platform.menu.configs'
const MENU_CACHE_VERSION = 6

export const useMenuStore = defineStore('menu', () => {
  // ================ state ================
  const menuConfigs = ref<MenuItemConfig[]>([])
  const loading = ref(false)
  const initialized = ref(false)

  // ================ i18n ================
  const { locale } = useI18n()

  // ================ getters ================

  /** 是否为管理员 */
  const isAdmin = computed(() => {
    const userStore = useUserStore()
    return userStore.isAdmin
  })

  /** 解析后的顶部导航菜单 */
  const topNav = computed(() => {
    const { topNav } = resolveMenus(menuConfigs.value, isAdmin.value, locale.value)
    return topNav
  })

  /** 解析后的侧边栏菜单（已按分组整理） */
  const sidebar = computed(() => {
    const { sidebar } = resolveMenus(menuConfigs.value, isAdmin.value, locale.value)
    return sidebar
  })

  /** 侧边栏分组列表（已排序） */
  const sidebarGroups = computed(() => {
    return Object.values(sidebar.value).sort((a, b) => {
      return (a.sort_order || 0) - (b.sort_order || 0)
    })
  })

  /** 所有菜单项（管理界面用，包含配置） */
  const allMenuItems = computed<AdminMenuItem[]>(() => {
    return getAllMenuItemsForAdmin(menuConfigs.value)
  })

  // ================ actions ================

  /** 从 localStorage 加载缓存配置 */
  function loadFromCache(): boolean {
    try {
      const cached = localStorage.getItem(MENU_CONFIG_CACHE_KEY)
      if (cached) {
        const wrapper = JSON.parse(cached)
        if (wrapper.version === MENU_CACHE_VERSION && Array.isArray(wrapper.data)) {
          menuConfigs.value = wrapper.data
          initialized.value = true
          return true
        }
        // 版本不匹配，清除旧缓存
        localStorage.removeItem(MENU_CONFIG_CACHE_KEY)
      }
    } catch (e) {
      console.warn('[Menu] 缓存加载失败:', e)
    }
    return false
  }

  /** 保存配置到 localStorage 缓存 */
  function saveToCache() {
    try {
      localStorage.setItem(MENU_CONFIG_CACHE_KEY, JSON.stringify({
        version: MENU_CACHE_VERSION,
        data: menuConfigs.value,
      }))
    } catch (e) {
      console.warn('[Menu] 缓存保存失败:', e)
    }
  }

  /** 清除缓存 */
  function clearCache() {
    localStorage.removeItem(MENU_CONFIG_CACHE_KEY)
    menuConfigs.value = []
    initialized.value = false
  }

  /** 使用默认配置 */
  function loadDefaultConfigs() {
    menuConfigs.value = [...DEFAULT_MENU_CONFIG]
    initialized.value = true
    saveToCache()
  }

  /** 获取菜单配置 */
  async function fetchMenus(useCache = true) {
    // 优先使用缓存
    if (useCache && loadFromCache()) {
      return
    }

    // 没有缓存，先加载默认配置保证菜单立即显示
    loadDefaultConfigs()

    // 再异步从后端拉取用户配置覆盖
    loading.value = true
    try {
      const data = await getMenuConfigs()
      if (data.configs && Array.isArray(data.configs)) {
        menuConfigs.value = data.configs
        saveToCache()
      }
    } catch (e) {
      console.warn('[Menu] 从后端获取菜单配置失败，使用默认配置:', e)
      // 失败时保持默认配置，已经显示了
    } finally {
      loading.value = false
    }
  }

  // ---------- 管理员菜单配置操作 ----------

  /** 批量保存菜单配置 */
  async function saveConfigs(configs: MenuItemConfig[]) {
    try {
      await saveMenuConfigs({ configs })
      menuConfigs.value = configs
      saveToCache()
      ElMessage.success('菜单配置已保存')
    } catch (e: any) {
      ElMessage.error(e.message || '保存菜单配置失败')
      throw e
    }
  }

  /** 重置菜单为默认配置 */
  async function resetToDefault() {
    try {
      await resetMenuConfigs()
      loadDefaultConfigs()
      ElMessage.success('菜单已重置为默认配置')
    } catch (e: any) {
      ElMessage.error(e.message || '重置菜单失败')
      throw e
    }
  }

  /** 更新单个菜单项的配置 */
  async function updateItemConfig(key: string, updates: Partial<MenuItemConfig>) {
    const newConfigs = menuConfigs.value.map(cfg => {
      if (cfg.key === key) {
        return { ...cfg, ...updates }
      }
      return cfg
    })
    await saveConfigs(newConfigs)
  }

  return {
    // state
    menuConfigs,
    loading,
    initialized,
    // getters
    topNav,
    sidebar,
    sidebarGroups,
    allMenuItems,
    isAdmin,
    // actions
    fetchMenus,
    saveConfigs,
    resetToDefault,
    updateItemConfig,
    clearCache,
    loadDefaultConfigs,
  }
})

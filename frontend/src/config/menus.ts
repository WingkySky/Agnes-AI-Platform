/* =====================================================
 * 内置菜单配置
 * - 所有可用菜单项在这里统一定义
 * - 后端只存储用户配置（是否显示、位置、排序、分组）
 * - 用户不需要关心 label_key、icon、path 等代码字段
 * ===================================================== */

export interface BuiltInMenuItem {
  /** 菜单唯一标识（固定，不可修改） */
  key: string
  /** 中文名称 */
  label_zh: string
  /** 英文名称 */
  label_en: string
  /** 图标组件名（Element Plus Icons） */
  icon: string | null
  /** 路由路径 */
  path: string
  /** 是否仅管理员可见 */
  require_admin: boolean
  /** 是否为分组标题（侧边栏分组用，不可点击） */
  is_group: boolean
}

/**
 * 所有可用的菜单项（固定列表，不可新增/删除基础项）
 * 用户只能配置：是否显示、显示位置（顶部/侧边栏）、排序、分组
 */
export const BUILT_IN_MENUS: BuiltInMenuItem[] = [
  // ========== 创作工具类 ==========
  {
    key: 'chat',
    label_zh: 'AI 对话',
    label_en: 'AI Chat',
    icon: 'ChatDotRound',
    path: '/chat',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'images',
    label_zh: '图片生成',
    label_en: 'Image Generation',
    icon: 'Picture',
    path: '/images',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'videos',
    label_zh: '视频生成',
    label_en: 'Video Generation',
    icon: 'VideoPlay',
    path: '/videos',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'canvas',
    label_zh: '无限画布',
    label_en: 'Infinite Canvas',
    icon: 'Grid',
    path: '/canvas',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'workshop',
    label_zh: '创意工坊',
    label_en: 'Workshop',
    icon: 'MagicStick',
    path: '/workshop',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'assets',
    label_zh: '资产库',
    label_en: 'Asset Library',
    icon: 'FolderOpened',
    path: '/assets',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'presets',
    label_zh: '预设中心',
    label_en: 'Preset Center',
    icon: 'Collection',
    path: '/presets',
    require_admin: false,
    is_group: false,
  },

  // ========== 社区类 ==========
  {
    key: 'plaza',
    label_zh: '作品广场',
    label_en: 'Plaza',
    icon: 'Histogram',
    path: '/plaza',
    require_admin: false,
    is_group: false,
  },

  // ========== 个人中心类 ==========
  {
    key: 'history',
    label_zh: '生成历史',
    label_en: 'Generation History',
    icon: 'Clock',
    path: '/history',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'credits',
    label_zh: '积分明细',
    label_en: 'Credits',
    icon: 'Coin',
    path: '/credits',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'profile',
    label_zh: '个人资料',
    label_en: 'Profile',
    icon: 'UserFilled',
    path: '/profile',
    require_admin: false,
    is_group: false,
  },
  {
    key: 'preferences',
    label_zh: '偏好设置',
    label_en: 'Preferences',
    icon: 'StarFilled',
    path: '/preferences',
    require_admin: false,
    is_group: false,
  },

  // ========== 管理类（仅管理员可见） ==========
  {
    key: 'admin-models',
    label_zh: '模型配置',
    label_en: 'Model Config',
    icon: 'Setting',
    path: '/admin/models',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-users',
    label_zh: '用户管理',
    label_en: 'User Management',
    icon: 'User',
    path: '/admin/users',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-roles',
    label_zh: '角色管理',
    label_en: 'Role Management',
    icon: 'UserFilled',
    path: '/admin/roles',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-credit-rules',
    label_zh: '积分规则',
    label_en: 'Credit Rules',
    icon: 'Coin',
    path: '/admin/credit-rules',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-moderation',
    label_zh: '内容审核',
    label_en: 'Content Moderation',
    icon: 'Histogram',
    path: '/admin/moderation',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-sensitive-words',
    label_zh: '敏感词管理',
    label_en: 'Sensitive Words',
    icon: 'ChatDotRound',
    path: '/admin/sensitive-words',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-watermark',
    label_zh: '水印配置',
    label_en: 'Watermark Config',
    icon: 'Picture',
    path: '/admin/watermark',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-email',
    label_zh: '邮件配置',
    label_en: 'Email Config',
    icon: 'Message',
    path: '/admin/email',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-menus',
    label_zh: '菜单管理',
    label_en: 'Menu Management',
    icon: 'Grid',
    path: '/admin/menus',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-presets',
    label_zh: '预设管理',
    label_en: 'Preset Management',
    icon: 'Collection',
    path: '/admin/presets',
    require_admin: true,
    is_group: false,
  },
  {
    key: 'admin-presets-audit',
    label_zh: '预设审核',
    label_en: 'Preset Audit',
    icon: 'CircleCheck',
    path: '/admin/presets/audit',
    require_admin: true,
    is_group: false,
  },
]

/**
 * 侧边栏分组定义
 */
export interface SidebarGroup {
  key: string
  label_zh: string
  label_en: string
  /** 分组图标 */
  icon: string
  /** 分组排序 */
  sort_order: number
}

export const SIDEBAR_GROUPS: SidebarGroup[] = [
  { key: 'create', label_zh: '创作工具', label_en: 'Create', icon: 'EditPen', sort_order: 1 },
  { key: 'personal', label_zh: '个人中心', label_en: 'Personal', icon: 'User', sort_order: 2 },
  { key: 'community', label_zh: '社区', label_en: 'Community', icon: 'Connection', sort_order: 3 },
  { key: 'admin', label_zh: '系统管理', label_en: 'Administration', icon: 'Setting', sort_order: 4 },
  { key: 'group5', label_zh: '分组5', label_en: 'Group 5', icon: 'Menu', sort_order: 5 },
  { key: 'group6', label_zh: '分组6', label_en: 'Group 6', icon: 'More', sort_order: 6 },
]

/**
 * 顶部导航分组定义
 * - 顶部导航空间有限，仅设置少量核心分组
 * - 每个分组下拉显示其下的菜单项
 */
export interface TopNavGroup {
  key: string
  label_zh: string
  label_en: string
  /** 分组图标 */
  icon: string
  /** 分组排序 */
  sort_order: number
}

export const TOP_NAV_GROUPS: TopNavGroup[] = [
  { key: 'create', label_zh: '创作工具', label_en: 'Create', icon: 'EditPen', sort_order: 1 },
  { key: 'community', label_zh: '社区', label_en: 'Community', icon: 'Connection', sort_order: 2 },
  { key: 'personal', label_zh: '个人中心', label_en: 'Personal', icon: 'User', sort_order: 3 },
  { key: 'admin', label_zh: '系统管理', label_en: 'Administration', icon: 'Setting', sort_order: 4 },
  { key: 'group5', label_zh: '分组5', label_en: 'Group 5', icon: 'Menu', sort_order: 5 },
  { key: 'group6', label_zh: '分组6', label_en: 'Group 6', icon: 'More', sort_order: 6 },
]

/**
 * 分组自定义配置（允许管理员修改分组名称和图标）
 */
export interface MenuGroupConfig {
  key: string
  /** 分组类型：top 或 sidebar */
  type: 'top' | 'sidebar'
  /** 自定义中文名称（null 表示使用默认） */
  label_zh: string | null
  /** 自定义英文名称（null 表示使用默认） */
  label_en: string | null
  /** 自定义图标（null 表示使用默认） */
  icon: string | null
}

/**
 * 完整菜单配置（包含菜单项配置和分组配置）
 */
export interface MenuConfigData {
  /** 菜单项配置 */
  items: MenuItemConfig[]
  /** 分组自定义配置 */
  groups: MenuGroupConfig[]
}

/**
 * 菜单默认配置（首次使用时的默认显示/位置/分组/排序）
 * 支持菜单项同时显示在顶部导航和侧边栏
 */
export interface MenuItemConfig {
  key: string
  /** 是否在顶部导航显示 */
  show_in_top: boolean
  /** 是否在侧边栏显示 */
  show_in_sidebar: boolean
  /** 顶部导航分组 key（仅当 show_in_top=true 时生效） */
  top_group_key: string | null
  /** 侧边栏分组 key（仅当 show_in_sidebar=true 时生效） */
  sidebar_group_key: string | null
  /** 顶部导航排序序号 */
  top_sort_order: number
  /** 侧边栏排序序号 */
  sidebar_sort_order: number
}

/**
 * 默认菜单配置
 * - 顶部导航：核心分组下拉显示（创作工具、社区）
 * - 侧边栏：所有功能按分组显示
 */
export const DEFAULT_MENU_CONFIG: MenuItemConfig[] = [
  // ---------- 创作工具类：顶部 + 侧边栏都显示 ----------
  { key: 'chat', show_in_top: true, show_in_sidebar: true, top_group_key: 'create', sidebar_group_key: 'create', top_sort_order: 1, sidebar_sort_order: 1 },
  { key: 'images', show_in_top: true, show_in_sidebar: true, top_group_key: 'create', sidebar_group_key: 'create', top_sort_order: 2, sidebar_sort_order: 2 },
  { key: 'videos', show_in_top: true, show_in_sidebar: true, top_group_key: 'create', sidebar_group_key: 'create', top_sort_order: 3, sidebar_sort_order: 3 },
  { key: 'canvas', show_in_top: true, show_in_sidebar: true, top_group_key: 'create', sidebar_group_key: 'create', top_sort_order: 4, sidebar_sort_order: 4 },
  { key: 'workshop', show_in_top: true, show_in_sidebar: true, top_group_key: 'create', sidebar_group_key: 'create', top_sort_order: 5, sidebar_sort_order: 5 },
  { key: 'assets', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'personal', top_sort_order: 99, sidebar_sort_order: 5 },
  { key: 'presets', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'create', top_sort_order: 99, sidebar_sort_order: 6 },

  // ---------- 社区类：顶部 + 侧边栏都显示 ----------
  { key: 'plaza', show_in_top: true, show_in_sidebar: true, top_group_key: 'community', sidebar_group_key: 'community', top_sort_order: 1, sidebar_sort_order: 1 },

  // ---------- 个人中心类：只在侧边栏显示 ----------
  { key: 'history', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'personal', top_sort_order: 99, sidebar_sort_order: 1 },
  { key: 'credits', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'personal', top_sort_order: 99, sidebar_sort_order: 2 },
  { key: 'profile', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'personal', top_sort_order: 99, sidebar_sort_order: 3 },
  { key: 'preferences', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'personal', top_sort_order: 99, sidebar_sort_order: 4 },

  // ---------- 管理类：只在侧边栏显示（仅管理员可见） ----------
  { key: 'admin-models', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 1 },
  { key: 'admin-users', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 2 },
  { key: 'admin-roles', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 3 },
  { key: 'admin-credit-rules', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 4 },
  { key: 'admin-moderation', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 5 },
  { key: 'admin-sensitive-words', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 6 },
  { key: 'admin-watermark', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 7 },
  { key: 'admin-email', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 8 },
  { key: 'admin-menus', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 9 },
  { key: 'admin-presets', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 10 },
  { key: 'admin-presets-audit', show_in_top: false, show_in_sidebar: true, top_group_key: null, sidebar_group_key: 'admin', top_sort_order: 99, sidebar_sort_order: 11 },
]

/**
 * 解析后的菜单项（已包含当前语言的标签）
 */
export interface ResolvedMenuItem {
  key: string
  label: string
  icon: string | null
  path: string
  require_admin: boolean
  is_group: boolean
  is_visible: boolean
  position: 'top' | 'sidebar' | 'hidden'
  group_key: string | null
  sort_order: number
}

export interface ResolvedSidebarGroup {
  key: string
  label: string
  icon: string
  sort_order: number
  items: ResolvedMenuItem[]
}

export interface ResolvedTopNavGroup {
  key: string
  label: string
  icon: string
  sort_order: number
  items: ResolvedMenuItem[]
}

function getMenuLabel(menu: BuiltInMenuItem, locale: string): string {
  return locale.startsWith('zh') ? menu.label_zh : menu.label_en
}

/**
 * 应用分组自定义配置，返回最终的标签和图标
 */
function applyGroupCustomization<T extends { label_zh: string; label_en: string; icon: string }>(
  defaultGroup: T,
  customConfig: MenuGroupConfig | undefined,
  locale: string
): { label: string; icon: string } {
  const useZh = locale.startsWith('zh')
  let label = useZh ? defaultGroup.label_zh : defaultGroup.label_en
  let icon = defaultGroup.icon

  if (customConfig) {
    if (useZh && customConfig.label_zh) {
      label = customConfig.label_zh
    } else if (!useZh && customConfig.label_en) {
      label = customConfig.label_en
    }
    if (customConfig.icon) {
      icon = customConfig.icon
    }
  }

  return { label, icon }
}

/**
 * 兼容旧版配置数据：旧版只有菜单项数组，新版有 items 和 groups
 */
function normalizeConfigData(
  configs: MenuItemConfig[] | MenuConfigData | undefined
): { items: MenuItemConfig[]; groups: MenuGroupConfig[] } {
  if (!configs) {
    return { items: DEFAULT_MENU_CONFIG, groups: [] }
  }
  if (Array.isArray(configs)) {
    return { items: configs, groups: [] }
  }
  return {
    items: configs.items || DEFAULT_MENU_CONFIG,
    groups: configs.groups || [],
  }
}

/**
 * 获取带自定义配置的顶部导航分组列表
 */
export function getTopNavGroupsWithCustomization(
  customGroups: MenuGroupConfig[],
  locale: string
): Array<TopNavGroup & { display_label: string; display_icon: string }> {
  const customMap = new Map(
    customGroups.filter(g => g.type === 'top').map(g => [g.key, g])
  )
  return TOP_NAV_GROUPS.map(group => {
    const { label, icon } = applyGroupCustomization(group, customMap.get(group.key), locale)
    return {
      ...group,
      display_label: label,
      display_icon: icon,
    }
  })
}

/**
 * 获取带自定义配置的侧边栏分组列表
 */
export function getSidebarGroupsWithCustomization(
  customGroups: MenuGroupConfig[],
  locale: string
): Array<SidebarGroup & { display_label: string; display_icon: string }> {
  const customMap = new Map(
    customGroups.filter(g => g.type === 'sidebar').map(g => [g.key, g])
  )
  return SIDEBAR_GROUPS.map(group => {
    const { label, icon } = applyGroupCustomization(group, customMap.get(group.key), locale)
    return {
      ...group,
      display_label: label,
      display_icon: icon,
    }
  })
}

export function resolveMenus(
  configs: MenuItemConfig[] | MenuConfigData,
  isAdmin: boolean,
  locale: string = 'zh-CN'
): { topNav: ResolvedTopNavGroup[]; sidebar: Record<string, ResolvedSidebarGroup> } {
  const { items: itemConfigs, groups: groupConfigs } = normalizeConfigData(configs)

  // 构建分组自定义配置映射
  const topGroupCustomMap = new Map(
    groupConfigs.filter(g => g.type === 'top').map(g => [g.key, g])
  )
  const sidebarGroupCustomMap = new Map(
    groupConfigs.filter(g => g.type === 'sidebar').map(g => [g.key, g])
  )

  // 先构建 key -> config 的映射
  const configMap = new Map<string, MenuItemConfig>()
  for (const cfg of itemConfigs) {
    configMap.set(cfg.key, cfg)
  }

  // 合并内置菜单和用户配置
  function getConfig(menu: BuiltInMenuItem): MenuItemConfig {
    const cfg = configMap.get(menu.key)
    const defaultCfg = DEFAULT_MENU_CONFIG.find(d => d.key === menu.key)
    return {
      key: menu.key,
      show_in_top: cfg?.show_in_top ?? defaultCfg?.show_in_top ?? false,
      show_in_sidebar: cfg?.show_in_sidebar ?? defaultCfg?.show_in_sidebar ?? false,
      top_group_key: cfg?.top_group_key ?? defaultCfg?.top_group_key ?? 'create',
      sidebar_group_key: cfg?.sidebar_group_key ?? defaultCfg?.sidebar_group_key ?? 'create',
      top_sort_order: cfg?.top_sort_order ?? defaultCfg?.top_sort_order ?? 99,
      sidebar_sort_order: cfg?.sidebar_sort_order ?? defaultCfg?.sidebar_sort_order ?? 99,
    }
  }

  // 构建顶部导航（按分组）
  const topNav: ResolvedTopNavGroup[] = []
  const topNavMap: Record<string, ResolvedTopNavGroup> = {}
  // 先初始化所有顶部分组（应用自定义配置）
  for (const group of TOP_NAV_GROUPS) {
    const { label, icon } = applyGroupCustomization(group, topGroupCustomMap.get(group.key), locale)
    topNavMap[group.key] = {
      key: group.key,
      label,
      icon,
      sort_order: group.sort_order,
      items: [],
    }
  }

  // 构建侧边栏按分组整理
  const sidebar: Record<string, ResolvedSidebarGroup> = {}
  // 先初始化所有分组（应用自定义配置）
  for (const group of SIDEBAR_GROUPS) {
    const { label, icon } = applyGroupCustomization(group, sidebarGroupCustomMap.get(group.key), locale)
    sidebar[group.key] = {
      key: group.key,
      label,
      icon,
      sort_order: group.sort_order,
      items: [],
    }
  }

  for (const menu of BUILT_IN_MENUS) {
    // 非管理员看不到管理员菜单
    if (menu.require_admin && !isAdmin) continue

    const cfg = getConfig(menu)

    const baseItem: Omit<ResolvedMenuItem, 'position' | 'group_key' | 'sort_order'> = {
      key: menu.key,
      label: getMenuLabel(menu, locale),
      icon: menu.icon,
      path: menu.path,
      require_admin: menu.require_admin,
      is_group: menu.is_group,
      is_visible: true,
    }

    // 添加到顶部导航（按分组）
    if (cfg.show_in_top) {
      const gk = cfg.top_group_key || 'create'
      const item: ResolvedMenuItem = {
        ...baseItem,
        position: 'top',
        group_key: gk,
        sort_order: cfg.top_sort_order,
      }
      if (topNavMap[gk]) {
        topNavMap[gk].items.push(item)
      } else {
        // 未知分组，放入第一个分组
        topNavMap[TOP_NAV_GROUPS[0].key].items.push(item)
      }
    }

    // 添加到侧边栏
    if (cfg.show_in_sidebar) {
      const gk = cfg.sidebar_group_key || 'create'
      const item: ResolvedMenuItem = {
        ...baseItem,
        position: 'sidebar',
        group_key: gk,
        sort_order: cfg.sidebar_sort_order,
      }
      if (!sidebar[gk]) {
        // 未知分组，放入创作工具
        sidebar['create'].items.push(item)
      } else {
        sidebar[gk].items.push(item)
      }
    }
  }

  // 顶部导航：先筛选有子项的分组，再排序
  for (const key in topNavMap) {
    if (topNavMap[key].items.length > 0) {
      topNav.push(topNavMap[key])
    }
  }
  topNav.sort((a, b) => a.sort_order - b.sort_order)
  // 每个顶部分组内排序
  for (const group of topNav) {
    group.items.sort((a, b) => a.sort_order - b.sort_order)
  }

  // 每个侧边栏分组内排序
  for (const key in sidebar) {
    sidebar[key].items.sort((a, b) => a.sort_order - b.sort_order)
  }

  return { topNav, sidebar }
}

/**
 * 管理界面用的菜单项配置
 */
export interface AdminMenuItem extends BuiltInMenuItem {
  show_in_top: boolean
  show_in_sidebar: boolean
  top_group_key: string | null
  sidebar_group_key: string | null
  top_sort_order: number
  sidebar_sort_order: number
}

/**
 * 管理界面用的分组配置
 */
export interface AdminMenuGroup {
  key: string
  type: 'top' | 'sidebar'
  label_zh: string
  label_en: string
  icon: string
  custom_label_zh: string | null
  custom_label_en: string | null
  custom_icon: string | null
  sort_order: number
}

export function getAllMenuItemsForAdmin(configs: MenuItemConfig[] | MenuConfigData): AdminMenuItem[] {
  const { items } = normalizeConfigData(configs)
  const configMap = new Map<string, MenuItemConfig>()
  for (const cfg of items) {
    configMap.set(cfg.key, cfg)
  }

  return BUILT_IN_MENUS.map(menu => {
    const cfg = configMap.get(menu.key)
    const defaultCfg = DEFAULT_MENU_CONFIG.find(d => d.key === menu.key)
    return {
      ...menu,
      show_in_top: cfg?.show_in_top ?? defaultCfg?.show_in_top ?? false,
      show_in_sidebar: cfg?.show_in_sidebar ?? defaultCfg?.show_in_sidebar ?? false,
      top_group_key: cfg?.top_group_key ?? defaultCfg?.top_group_key ?? 'create',
      sidebar_group_key: cfg?.sidebar_group_key ?? defaultCfg?.sidebar_group_key ?? 'create',
      top_sort_order: cfg?.top_sort_order ?? defaultCfg?.top_sort_order ?? 99,
      sidebar_sort_order: cfg?.sidebar_sort_order ?? defaultCfg?.sidebar_sort_order ?? 99,
    }
  })
}

/**
 * 获取管理界面用的顶部分组列表（含自定义配置）
 */
export function getTopNavGroupsForAdmin(customGroups: MenuGroupConfig[]): AdminMenuGroup[] {
  const customMap = new Map(
    customGroups.filter(g => g.type === 'top').map(g => [g.key, g])
  )
  return TOP_NAV_GROUPS.map(group => {
    const custom = customMap.get(group.key)
    return {
      key: group.key,
      type: 'top' as const,
      label_zh: group.label_zh,
      label_en: group.label_en,
      icon: group.icon,
      custom_label_zh: custom?.label_zh ?? null,
      custom_label_en: custom?.label_en ?? null,
      custom_icon: custom?.icon ?? null,
      sort_order: group.sort_order,
    }
  })
}

/**
 * 获取管理界面用的侧边栏分组列表（含自定义配置）
 */
export function getSidebarGroupsForAdmin(customGroups: MenuGroupConfig[]): AdminMenuGroup[] {
  const customMap = new Map(
    customGroups.filter(g => g.type === 'sidebar').map(g => [g.key, g])
  )
  return SIDEBAR_GROUPS.map(group => {
    const custom = customMap.get(group.key)
    return {
      key: group.key,
      type: 'sidebar' as const,
      label_zh: group.label_zh,
      label_en: group.label_en,
      icon: group.icon,
      custom_label_zh: custom?.label_zh ?? null,
      custom_label_en: custom?.label_en ?? null,
      custom_icon: custom?.icon ?? null,
      sort_order: group.sort_order,
    }
  })
}

/* =====================================================
 * icons — 按名称解析 Element Plus 图标组件
 * 供菜单图标等「后端下发图标名 → 组件」的场景使用
 * ===================================================== */

import type { Component } from 'vue'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const iconMap = ElementPlusIconsVue as Record<string, Component>

/** 根据图标名称获取组件，空名 / 未知名返回 null */
export function getIconByName(name: string | null | undefined): Component | null {
  if (!name) return null
  return iconMap[name] || null
}

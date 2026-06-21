/* =====================================================
 * 全局主题 Store（深色 / 浅色切换）
 * 职责：
 *   - 持久化主题模式到 localStorage
 *   - 同步切换 <html> 上的 class（dark / light）
 *   - 提供全局切换入口，画布主题切换会联动调用
 *   - 应用启动时（main.ts）调用 init() 恢复上次主题
 * ===================================================== */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type ThemeMode = 'dark' | 'light'

const THEME_STORAGE_KEY = 'agnes.platform.theme'

export const useThemeStore = defineStore('theme', () => {
  // ================ state ================
  const mode = ref<ThemeMode>('dark')

  // ================ getters ================
  const isDark = computed(() => mode.value === 'dark')

  // ================ actions ================

  /** 应用主题到 <html>：dark 模式加 dark class，light 模式移除 */
  function applyToDocument() {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    if (mode.value === 'dark') {
      root.classList.add('dark')
      root.classList.remove('light')
    } else {
      root.classList.add('light')
      root.classList.remove('dark')
    }
  }

  /** 设置主题模式（同步到 DOM + 持久化） */
  function setMode(next: ThemeMode) {
    if (next !== 'dark' && next !== 'light') return
    mode.value = next
    applyToDocument()
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch (e) {
      // ignore storage errors
    }
  }

  /** 切换主题（深色 ↔ 浅色） */
  function toggle() {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  /** 初始化：从 localStorage 恢复上次主题 */
  function init() {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY)
      if (saved === 'light' || saved === 'dark') {
        mode.value = saved
      }
    } catch (e) {
      // ignore
    }
    applyToDocument()
  }

  return {
    // state
    mode,
    // getters
    isDark,
    // actions
    setMode,
    toggle,
    init,
  }
})

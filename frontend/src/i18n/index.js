/* =====================================================
 * Agnes AI Platform 国际化模块 (i18n)
 *
 * 轻量级国际化方案（不引入 vue-i18n，零额外依赖）
 * - 使用 reactive 驱动语言切换，自动刷新相关组件
 * - 支持语言持久化到 localStorage
 * - 同步设置 Element Plus 的语言包
 * - 提供 $t / t 全局访问，支持点分路径与简单插值
 *
 * 使用：
 *   import { t } from '@/i18n'
 *   t('nav.images')                    →  "图片生成"
 *   t('history.deletedCount', { count: 3 })  →  "已成功删除 3 条记录"
 *
 * 组件内（Composition API）：
 *   import { useI18n } from '@/i18n'
 *   const { t, locale } = useI18n()
 *   t('nav.images')
 *
 * 切语言：
 *   import { setLocale } from '@/i18n'
 *   setLocale('en-US')
 * ===================================================== */

import { reactive, computed, watch } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'

import zhCNPack from './zh-CN.js'
import enUSPack from './en-US.js'

// ------ 常量 ------
export const STORAGE_KEY = 'agnes_platform_locale'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']
export const FALLBACK_LOCALE = 'zh-CN'

// 语言 -> Element Plus locale 对象
const EP_LOCALE_MAP = {
  'zh-CN': zhCn,
  'en-US': en,
}

// 所有语言包
const MESSAGES = {
  'zh-CN': zhCNPack,
  'en-US': enUSPack,
}

// 语言展示名（用于切换器展示）
export const LOCALE_LABELS = {
  'zh-CN': '中文',
  'en-US': 'English',
}

// ------ 响应式状态 ------
export const state = reactive({
  locale: detectInitialLocale(),
})

// ------ 工具函数 ------

/**
 * 启动时检测初始语言：
 *  1) localStorage 中有记 → 使用
 *  2) 浏览器语言是英文系 → en-US
 *  3) 其他 → zh-CN
 */
function detectInitialLocale() {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && SUPPORTED_LOCALES.includes(saved)) return saved
  }
  if (typeof navigator !== 'undefined' && navigator.language) {
    const lang = navigator.language.toLowerCase()
    if (lang.startsWith('zh')) return 'zh-CN'
    if (lang.startsWith('en')) return 'en-US'
  }
  return FALLBACK_LOCALE
}

/**
 * 按点分路径从嵌套对象取值
 *  e.g. lookup({a:{b:'x'}}, 'a.b') → 'x'
 *       lookup({a:{b:'x'}}, 'a.missing', 'fallback') → 'fallback'
 */
function lookup(obj, path, fallback) {
  if (!obj || !path) return fallback
  const parts = String(path).split('.')
  let cur = obj
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return fallback
    cur = cur[p]
  }
  if (cur == null || cur === undefined) return fallback
  return cur
}

/**
 * 简单字符串插值：把 {key} 替换为 values[key]
 *  e.g. interpolate('Hello {name}!', { name: 'Agnes' }) → 'Hello Agnes!'
 */
function interpolate(tpl, values) {
  if (tpl == null) return ''
  if (!values || typeof values !== 'object') return String(tpl)
  return String(tpl).replace(/\{(\w+)\}/g, (m, k) => {
    return values[k] !== undefined ? String(values[k]) : m
  })
}

// ------ 核心 API ------

/**
 * 翻译函数。
 *  - key  点分路径，如 'nav.images'
 *  - values 可选，用于 {key} 占位符替换
 */
export function t(key, values) {
  const pack = MESSAGES[state.locale] || MESSAGES[FALLBACK_LOCALE]
  let value = lookup(pack, key, null)
  if (value == null) {
    // 回退到默认语言包
    const fbPack = MESSAGES[FALLBACK_LOCALE]
    value = lookup(fbPack, key, key)
  }
  return interpolate(value, values)
}

/**
 * 返回 Element Plus 当前语言对应的 locale 对象（用于 <el-config-provider>）
 */
export function getElementPlusLocale() {
  return EP_LOCALE_MAP[state.locale] || EP_LOCALE_MAP[FALLBACK_LOCALE]
}

/**
 * 切换语言，并持久化到 localStorage。同时更新 <html lang="...">
 */
export function setLocale(locale) {
  if (!SUPPORTED_LOCALES.includes(locale)) {
    console.warn('[i18n] 不支持的语言：', locale)
    return
  }
  state.locale = locale
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, locale)
    }
  } catch (_) {
    /* localStorage 可能因隐私模式写入失败 */
  }
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('lang', locale)
  }
}

/**
 * 切换到下一个支持的语言（用于简单的“点击切换”按钮）。
 */
export function toggleLocale() {
  const idx = SUPPORTED_LOCALES.indexOf(state.locale)
  const next = SUPPORTED_LOCALES[(idx + 1) % SUPPORTED_LOCALES.length]
  setLocale(next)
}

/**
 * Composition API 风格 hook：返回响应式 t / locale / setLocale
 *
 * 实现思路：返回的 t 函数在每次调用时都会读取 state.locale，
 * 因此当语言切换时，使用该 t 函数的 computed / 模板会自动重新计算。
 */
export function useI18n() {
  return {
    // 每次调用都读取 state.locale，使依赖项与 Vue 响应式系统关联
    t(key, values) {
      // eslint-disable-next-line no-unused-expressions
      state.locale
      return t(key, values)
    },
    locale: computed(() => state.locale),
    setLocale,
    toggleLocale,
    supportedLocales: SUPPORTED_LOCALES,
    localeLabels: LOCALE_LABELS,
  }
}

/**
 * 便捷：订阅语言变化（可用于非 Vue 组件的外部逻辑）
 */
export function onLocaleChange(callback) {
  if (typeof callback !== 'function') return () => {}
  return watch(
    () => state.locale,
    (val) => callback(val),
    { immediate: true },
  )
}

// 安装时同步一次 <html lang="...">
if (typeof document !== 'undefined' && document.documentElement) {
  document.documentElement.setAttribute('lang', state.locale)
}

// ------ Vue 插件形式（可选地通过 app.use(i18n) 注入全局属性 $t）------
export default {
  install(app) {
    app.config.globalProperties.$t = t
    app.provide('i18n-locale', state)
    app.provide('i18n-t', t)
  },
}

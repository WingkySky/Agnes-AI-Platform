/* =====================================================
 * 风格预设 + 剧本模板 Store
 * 从 pipeline store 拆分出来，独立管理
 * 修复：loadStylePresets 不再写死 is_builtin=true，支持加载用户自定义
 * ===================================================== */

import { defineStore } from 'pinia'
import { getStylePresets, getScriptTemplates } from '@/api/pipeline'
import type { StylePreset, ScriptTemplate, PipelineListParams, ListResult } from '@/types'

interface StylesState {
  stylePresets: StylePreset[]
  stylePresetsLoading: boolean
  stylePresetsLoaded: boolean

  scriptTemplates: ScriptTemplate[]
  scriptTemplatesLoading: boolean
  scriptTemplatesLoaded: boolean
}

export const useStylesStore = defineStore('pipelineStyles', {
  state: (): StylesState => ({
    stylePresets: [],
    stylePresetsLoading: false,
    stylePresetsLoaded: false,

    scriptTemplates: [],
    scriptTemplatesLoading: false,
    scriptTemplatesLoaded: false,
  }),

  getters: {
    /** 内置风格预设 */
    builtinStyles(state): StylePreset[] {
      return state.stylePresets.filter(s => s.is_builtin)
    },
    /** 用户自定义风格 */
    userStyles(state): StylePreset[] {
      return state.stylePresets.filter(s => !s.is_builtin)
    },
  },

  actions: {
    /**
     * 加载风格预设列表
     * @param includeUserCreated false 只加载内置，true 加载全部（含用户自定义）
     */
    async loadStylePresets(includeUserCreated = false) {
      if (this.stylePresetsLoading) return
      this.stylePresetsLoading = true
      try {
        const params: PipelineListParams = { page: 1, page_size: 50 }
        if (!includeUserCreated) {
          params.is_builtin = true
        }
        const result: ListResult<StylePreset> = await getStylePresets(params)
        this.stylePresets = result.items
        this.stylePresetsLoaded = true
      } catch (e) {
        console.error('加载风格预设失败:', e)
        throw e
      } finally {
        this.stylePresetsLoading = false
      }
    },

    /** 加载剧本模板列表 */
    async loadScriptTemplates() {
      if (this.scriptTemplatesLoading) return
      this.scriptTemplatesLoading = true
      try {
        const result: ListResult<ScriptTemplate> = await getScriptTemplates({ page: 1, page_size: 50 })
        this.scriptTemplates = result.items
        this.scriptTemplatesLoaded = true
      } catch (e) {
        console.error('加载剧本模板失败:', e)
        throw e
      } finally {
        this.scriptTemplatesLoading = false
      }
    },

    clearAll() {
      this.stylePresets = []
      this.stylePresetsLoading = false
      this.stylePresetsLoaded = false
      this.scriptTemplates = []
      this.scriptTemplatesLoading = false
      this.scriptTemplatesLoaded = false
    },
  },
})

// 用户登出时清理
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      useStylesStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}

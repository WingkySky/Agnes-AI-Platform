/* =====================================================
 * 风格预设 + 剧本模板 Store
 * 从 pipeline store 拆分出来，独立管理
 * 修复：loadStylePresets 不再写死 is_builtin=true，支持加载用户自定义
 * ===================================================== */

import { defineStore } from 'pinia'
import { getStylePresets } from '@/api/pipeline'
import type { StylePreset, PipelineListParams, ListResult } from '@/types'

interface StylesState {
  stylePresets: StylePreset[]
  stylePresetsLoading: boolean
  stylePresetsLoaded: boolean

}

export const useStylesStore = defineStore('pipelineStyles', {
  state: (): StylesState => ({
    stylePresets: [],
    stylePresetsLoading: false,
    stylePresetsLoaded: false,

  }),

  getters: {
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

    clearAll() {
      this.stylePresets = []
      this.stylePresetsLoading = false
      this.stylePresetsLoaded = false
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

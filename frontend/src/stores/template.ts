/* =====================================================
 * 模板管理 Store
 * 职责：管理模板市场列表 + 我的模板列表（轻量 store）
 * 替代旧 stores/pipeline.ts 中模板相关逻辑（PipelineRun 部分已废弃）
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getPipelineTemplates } from '@/api/pipeline'
import type { PipelineTemplate } from '@/types'

export const useTemplateStore = defineStore('template', () => {
  // 市场模板（公开 + 内置）
  const templates = ref<PipelineTemplate[]>([])
  const templatesTotal = ref(0)
  const templatesLoading = ref(false)
  const templatesLoaded = ref(false)

  // 我的模板（私有 + 审核中 + 已拒绝）
  const myTemplates = ref<PipelineTemplate[]>([])
  const myTemplatesTotal = ref(0)
  const myTemplatesLoading = ref(false)
  const myTemplatesLoaded = ref(false)

  /** 加载市场模板 */
  async function loadTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
    if (templatesLoading.value) return
    templatesLoading.value = true
    try {
      const result = await getPipelineTemplates({ page: 1, page_size: 50, scope: 'market', ...params })
      templates.value = result.items
      templatesTotal.value = result.total
      templatesLoaded.value = true
    } catch (e) {
      console.error('加载模板市场失败:', e)
      throw e
    } finally {
      templatesLoading.value = false
    }
  }

  /** 加载我的模板 */
  async function loadMyTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
    if (myTemplatesLoading.value) return
    myTemplatesLoading.value = true
    try {
      const result = await getPipelineTemplates({ page: 1, page_size: 100, scope: 'my', ...params })
      myTemplates.value = result.items
      myTemplatesTotal.value = result.total
      myTemplatesLoaded.value = true
    } catch (e) {
      console.error('加载我的模板失败:', e)
      throw e
    } finally {
      myTemplatesLoading.value = false
    }
  }

  /** 刷新我的模板（强制重新加载） */
  async function refreshMyTemplates() {
    myTemplatesLoaded.value = false
    return loadMyTemplates()
  }

  return {
    templates,
    templatesTotal,
    templatesLoading,
    templatesLoaded,
    myTemplates,
    myTemplatesTotal,
    myTemplatesLoading,
    myTemplatesLoaded,
    loadTemplates,
    loadMyTemplates,
    refreshMyTemplates,
  }
})

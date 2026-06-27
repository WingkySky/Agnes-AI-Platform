/* =====================================================
 * 创意流水线状态管理 Store
 * 职责：模板列表、当前运行实例、运行历史
 * 注意：styles/scriptTemplates 已迁移到 stores/styles.ts
 *       创意资产库在 stores/asset.ts（新建）
 * ===================================================== */

import { defineStore } from 'pinia'
import {
  getPipelineTemplates,
  getPipelineRuns,
  createPipelineRun as apiCreateRun,
  cancelPipelineRun as apiCancelRun,
  retryPipelineRun as apiRetryRun,
  retryPipelineStep as apiRetryStep,
  deletePipelineRun as apiDeleteRun,
  pausePipelineRun as apiPauseRun,
  updatePipelineRunInputs as apiUpdateRunInputs,
  exportRunToCanvas as apiExportRunToCanvas,
} from '@/api/pipeline'
import type {
  PipelineTemplate,
  PipelineRun,
  PipelineListParams,
  ListResult,
  CreateRunRequest,
} from '@/types'
import { useTaskQueueStore } from '@/stores/taskQueue'

interface PipelineState {
  /* 模板相关 */
  templates: PipelineTemplate[]
  templatesLoading: boolean
  templatesTotal: number
  templatesLoaded: boolean

  /* 当前流水线运行 */
  currentRunId: number | null
  currentRun: PipelineRun | null

  /* 历史运行记录 */
  runHistory: PipelineRun[]
  runHistoryLoading: boolean
  runHistoryTotal: number
}

export const usePipelineStore = defineStore('pipeline', {
  state: (): PipelineState => ({
    templates: [],
    templatesLoading: false,
    templatesTotal: 0,
    templatesLoaded: false,

    currentRunId: null,
    currentRun: null,

    runHistory: [],
    runHistoryLoading: false,
    runHistoryTotal: 0,
  }),

  getters: {
    /** 按分类分组的模板 */
    templatesByCategory(state): Record<string, PipelineTemplate[]> {
      const groups: Record<string, PipelineTemplate[]> = {}
      state.templates.forEach(tpl => {
        const cat = tpl.category || 'other'
        if (!groups[cat]) groups[cat] = []
        groups[cat].push(tpl)
      })
      return groups
    },

    /** 是否有正在运行的流水线 */
    hasRunningPipeline(state): boolean {
      return state.runHistory.some(r => r.status === 'running' || r.status === 'pending')
    },
  },

  actions: {
    /** 加载流水线模板列表 */
    async loadTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
      if (this.templatesLoading) return
      this.templatesLoading = true
      try {
        const result = await getPipelineTemplates({ page: 1, page_size: 50, ...params })
        this.templates = result.items
        this.templatesTotal = result.total
        this.templatesLoaded = true
      } catch (e) {
        console.error('加载流水线模板失败:', e)
        throw e
      } finally {
        this.templatesLoading = false
      }
    },

    /**
     * 创建并启动流水线运行
     * 内部会注册到 taskQueue，让全局任务面板展示进度
     */
    async createRun(templateId: number, inputs: Record<string, unknown>, name?: string) {
      const payload: CreateRunRequest = { template_id: templateId, inputs, name }
      const run = await apiCreateRun(payload)

      // 注册到全局任务队列
      const taskQueue = useTaskQueueStore()
      const templateName = this.templates.find(t => t.id === templateId)?.name || `运行 #${run.id}`
      taskQueue.registerPipelineTask({ runId: run.id, templateName })

      // 设置为当前运行
      this.currentRun = run
      this.currentRunId = run.id

      return run
    },

    /** 加载单个运行详情 */
    async loadRun(runId: number) {
      // 直接调 API，不缓存（run 详情由 SSE 实时更新）
      const { getPipelineRunDetail } = await import('@/api/pipeline')
      const run = await getPipelineRunDetail(runId)
      this.currentRun = run
      this.currentRunId = run.id
      return run
    },

    /** 取消运行 */
    async cancelRun(runId: number) {
      await apiCancelRun(runId)
      if (this.currentRun?.id === runId) {
        this.currentRun.status = 'cancelled'
      }
    },

    /** 删除运行记录 */
    async deleteRun(runId: number) {
      await apiDeleteRun(runId)
      // 从历史列表中移除
      this.runHistory = this.runHistory.filter(r => r.id !== runId)
      this.runHistoryTotal = Math.max(0, this.runHistoryTotal - 1)
      // 如果删除的是当前运行，清除
      if (this.currentRun?.id === runId) {
        this.currentRun = null
        this.currentRunId = null
      }
    },

    /** 重试整个运行 */
    async retryRun(runId: number) {
      await apiRetryRun(runId)
    },

    /** 重试单个失败步骤 */
    async retryStep(runId: number, stepKey: string) {
      await apiRetryStep(runId, stepKey)
    },

    /** 暂停正在运行的流水线 */
    async pauseRun(runId: number) {
      await apiPauseRun(runId)
      if (this.currentRun?.id === runId) {
        this.currentRun.status = 'paused'
      }
      const historyRun = this.runHistory.find(r => r.id === runId)
      if (historyRun) historyRun.status = 'paused'
    },

    /** 编辑流水线输入参数 */
    async updateRunInputs(runId: number, inputs: Record<string, any>) {
      const result = await apiUpdateRunInputs(runId, inputs)
      if (this.currentRun?.id === runId) {
        this.currentRun.inputs = result.inputs
      }
      return result
    },

    /** 导出流水线结果到画布 */
    async exportToCanvas(runId: number) {
      const result = await apiExportRunToCanvas(runId)
      return result.data
    },

    /** 加载我的流水线历史 */
    async loadRunHistory(params: { page?: number; page_size?: number; status?: string } = {}) {
      if (this.runHistoryLoading) return
      this.runHistoryLoading = true
      try {
        const result = await getPipelineRuns({ page: 1, page_size: 20, ...params })
        this.runHistory = result.items
        this.runHistoryTotal = result.total
      } catch (e) {
        console.error('加载流水线历史失败:', e)
        throw e
      } finally {
        this.runHistoryLoading = false
      }
    },

    /** 设置当前运行的流水线 */
    setCurrentRun(run: PipelineRun | null) {
      this.currentRun = run
      this.currentRunId = run?.id ?? null
    },

    /** 从 SSE 事件更新当前运行状态 */
    updateRunFromEvent(eventType: string, data: Record<string, any>) {
      if (!this.currentRun) return
      if (eventType === 'pipeline_completed' || eventType === 'pipeline_failed') {
        this.currentRun.status = data.status || this.currentRun.status
        if (data.error) this.currentRun.error_message = data.error
        if (data.output_summary) this.currentRun.output_summary = data.output_summary
        this.currentRun.finished_at = new Date().toISOString()
      } else if (eventType === 'pipeline_paused') {
        this.currentRun.status = 'paused'
      } else if (eventType === 'pipeline_started') {
        this.currentRun.status = 'running'
        this.currentRun.started_at = new Date().toISOString()
      }
    },

    clearAll() {
      this.templates = []
      this.templatesLoading = false
      this.templatesTotal = 0
      this.templatesLoaded = false
      this.currentRunId = null
      this.currentRun = null
      this.runHistory = []
      this.runHistoryLoading = false
      this.runHistoryTotal = 0
    },
  },
})

// 用户登出时清理流水线状态
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      usePipelineStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}

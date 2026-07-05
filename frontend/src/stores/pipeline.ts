/* =====================================================
 * 创意流水线状态管理 Store
 * 职责：模板列表、当前运行实例、运行历史
 * 注意：styles/scriptTemplates 已迁移到 stores/styles.ts
 *       创意资产库在 stores/asset.ts（新建）
 * ===================================================== */

import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
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
  // Task 21: 步骤确认 / 元素级重试 / 产物编辑 / 失效 / 编辑锁 / 版本历史 / 自动确认
  confirmStep as apiConfirmStep,
  retryStepItem as apiRetryStepItem,
  editStepOutput as apiEditStepOutput,
  uploadStepItem as apiUploadStepItem,
  applyStale as apiApplyStale,
  ignoreStale as apiIgnoreStale,
  acquireEditLock as apiAcquireEditLock,
  releaseEditLock as apiReleaseEditLock,
  listStepRevisions as apiListStepRevisions,
  rollbackStepRevision as apiRollbackStepRevision,
  setAutoConfirm as apiSetAutoConfirm,
} from '@/api/pipeline'
import type {
  PipelineTemplate,
  PipelineRun,
  PipelineListParams,
  ListResult,
  CreateRunRequest,
} from '@/types'
import type { StaleSummary } from '@/api/pipeline'
import { useTaskQueueStore } from '@/stores/taskQueue'

/** 编辑锁状态（run 级，5 分钟超时，惰性检查） */
interface EditLockState {
  userId: number
  expiresAt: string
}

interface PipelineState {
  /* 模板相关 */
  templates: PipelineTemplate[]
  templatesLoading: boolean
  templatesTotal: number
  templatesLoaded: boolean

  /* 我的模板 */
  myTemplates: PipelineTemplate[]
  myTemplatesLoading: boolean
  myTemplatesTotal: number
  myTemplatesLoaded: boolean

  /* 当前流水线运行 */
  currentRunId: number | null
  currentRun: PipelineRun | null

  /* 历史运行记录 */
  runHistory: PipelineRun[]
  runHistoryLoading: boolean
  runHistoryTotal: number

  /* ===== Task 22: 步骤确认 / 编辑锁 / 失效 / 版本历史相关 state ===== */
  /** 当前选中查看的步骤 key */
  currentStepKey: string | null
  /** 编辑锁状态（null 表示未持锁） */
  editingLock: EditLockState | null
  /** 下游失效摘要（stale_marked 事件 / apply-stale 接口返回） */
  staleSummary: StaleSummary | null
  /** 步骤版本历史缓存（key: stepKey, value: revisions 数组） */
  stepRevisions: Record<string, any[]>
}

export const usePipelineStore = defineStore('pipeline', {
  state: (): PipelineState => ({
    templates: [],
    templatesLoading: false,
    templatesTotal: 0,
    templatesLoaded: false,

    myTemplates: [],
    myTemplatesLoading: false,
    myTemplatesTotal: 0,
    myTemplatesLoaded: false,

    currentRunId: null,
    currentRun: null,

    runHistory: [],
    runHistoryLoading: false,
    runHistoryTotal: 0,

    /* Task 22: 步骤确认 / 编辑锁 / 失效 / 版本历史 */
    currentStepKey: null,
    editingLock: null,
    staleSummary: null,
    stepRevisions: {},
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
    /** 加载流水线模板列表（市场） */
    async loadTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
      if (this.templatesLoading) return
      this.templatesLoading = true
      try {
        const result = await getPipelineTemplates({ page: 1, page_size: 50, scope: 'market', ...params })
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

    /** 加载我的模板列表 */
    async loadMyTemplates(params: { page?: number; page_size?: number; category?: string; search?: string } = {}) {
      if (this.myTemplatesLoading) return
      this.myTemplatesLoading = true
      try {
        const result = await getPipelineTemplates({ page: 1, page_size: 100, scope: 'my', ...params })
        this.myTemplates = result.items
        this.myTemplatesTotal = result.total
        this.myTemplatesLoaded = true
      } catch (e) {
        console.error('加载我的模板失败:', e)
        throw e
      } finally {
        this.myTemplatesLoading = false
      }
    },

    /** 刷新我的模板（强制重新加载） */
    async refreshMyTemplates() {
      this.myTemplatesLoaded = false
      return this.loadMyTemplates()
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

    /* =====================================================
     * Task 22: 步骤确认 / 元素级重试 / 产物编辑 /
     * 下游失效 / 编辑锁 / 版本历史 / 自动确认
     * 对应后端 Task 11-16 路由，API 函数来自 Task 21
     * ===================================================== */

    /** Task 11: 确认 / 驳回步骤 */
    async confirmStep(stepKey: string, action: 'confirm' | 'reject', comment?: string, editedOutput?: any): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiConfirmStep(this.currentRunId, stepKey, {
          action,
          comment,
          edited_output: editedOutput,
        })
        ElMessage.success(action === 'confirm' ? '步骤已确认' : '步骤已驳回')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '确认步骤失败')
        return false
      }
    },

    /** Task 12: 元素级重试（重试步骤中单个失败的 item） */
    async retryStepItem(stepKey: string, itemId: string, promptOverride?: string, seed?: number): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiRetryStepItem(this.currentRunId, stepKey, {
          item_id: itemId,
          prompt_override: promptOverride,
          seed,
        })
        ElMessage.success('已提交元素重试')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '元素重试失败')
        return false
      }
    },

    /** Task 13: 编辑步骤产物（整体替换 / 删除 / 追加 items） */
    async editStepOutput(stepKey: string, data: { items?: any[], remove_item_ids?: string[], add_items?: any[] }): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiEditStepOutput(this.currentRunId, stepKey, data)
        ElMessage.success('步骤产物已更新')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '编辑步骤产物失败')
        return false
      }
    },

    /** Task 13: 上传图片替换步骤中某个 item 的图片 */
    async uploadStepItem(stepKey: string, itemId: string, file: File): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiUploadStepItem(this.currentRunId, stepKey, itemId, file)
        ElMessage.success('图片已上传')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '上传图片失败')
        return false
      }
    },

    /** Task 14: 应用下游失效（按 DAG 逆序重置 stale 步骤及下游） */
    async applyStale(): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiApplyStale(this.currentRunId)
        // 应用后失效标记已消费，清空摘要
        this.staleSummary = null
        ElMessage.success('已应用下游失效，将重新执行受影响步骤')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '应用下游失效失败')
        return false
      }
    },

    /** Task 14: 忽略 stale（清除所有步骤的 stale 标记） */
    async ignoreStale(): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiIgnoreStale(this.currentRunId)
        this.staleSummary = null
        ElMessage.success('已忽略下游失效标记')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '忽略 stale 失败')
        return false
      }
    },

    /** Task 15: 获取 run 级编辑锁（5 分钟超时，惰性检查） */
    async acquireEditLock(): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        const res = await apiAcquireEditLock(this.currentRunId)
        // 兼容后端返回 { user_id, expires_at } 或 { data: { user_id, expires_at } }
        const lockData = res.data ?? res
        this.editingLock = {
          userId: lockData.user_id ?? lockData.userId,
          expiresAt: lockData.expires_at ?? lockData.expiresAt,
        }
        ElMessage.success('已获取编辑锁')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '获取编辑锁失败')
        return false
      }
    },

    /** Task 15: 释放 run 级编辑锁 */
    async releaseEditLock(): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiReleaseEditLock(this.currentRunId)
        this.editingLock = null
        ElMessage.success('已释放编辑锁')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '释放编辑锁失败')
        return false
      }
    },

    /** Task 15: 查看步骤产物版本历史（按 revision 降序） */
    async listStepRevisions(stepKey: string): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        const res = await apiListStepRevisions(this.currentRunId, stepKey)
        // 兼容后端返回 { items: [...] } / { data: [...] } / { revisions: [...] }
        const revisions = res.items ?? res.data ?? res.revisions ?? []
        this.stepRevisions = { ...this.stepRevisions, [stepKey]: revisions }
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '获取版本历史失败')
        return false
      }
    },

    /** Task 15: 回滚步骤产物到指定版本 */
    async rollbackStepRevision(stepKey: string, revision: number): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiRollbackStepRevision(this.currentRunId, stepKey, revision)
        ElMessage.success(`已回滚到版本 ${revision}`)
        // 回滚后刷新该步骤的版本历史
        await this.listStepRevisions(stepKey)
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '回滚版本失败')
        return false
      }
    },

    /** Task 16: 切换 run.auto_confirm 标志 */
    async toggleAutoConfirm(enabled: boolean): Promise<boolean> {
      if (!this.currentRunId) {
        ElMessage.error('当前没有运行中的流水线')
        return false
      }
      try {
        await apiSetAutoConfirm(this.currentRunId, enabled)
        // PipelineRun 类型未声明 auto_confirm 字段，运行实例可能携带，做兼容处理
        if (this.currentRun) {
          (this.currentRun as any).auto_confirm = enabled
        }
        ElMessage.success(enabled ? '已开启自动确认' : '已关闭自动确认')
        return true
      } catch (e: any) {
        ElMessage.error(e.message || '切换自动确认失败')
        return false
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

/* =====================================================
 * 创意流水线相关 API 封装
 * - 模板列表/详情
 * - 流水线创建/启动/查询/取消/重试
 * - 步骤查询/单步重试
 * - 风格预设、剧本模板、资产库
 * - 积分预估
 * 类型定义已迁移到 @/types，本文件只保留请求函数
 * ===================================================== */

import client from './client'
import type {
  PipelineTemplate,
  PipelineTemplateRevision,
  PipelineRun,
  PipelineStep,
  StylePreset,
  ScriptTemplate,
  Asset,
  CreditEstimateResult,
  CreateRunRequest,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
} from '@/types'

// re-export 类型，方便使用方从 api 文件统一导入（向后兼容）
export type {
  PipelineTemplate,
  PipelineTemplateRevision,
  PipelineRun,
  PipelineStep,
  StylePreset,
  ScriptTemplate,
  Asset,
  CreditEstimateResult,
  CreateRunRequest,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
}

/** 流水线产物 */
export interface PipelineOutput {
  filename: string
  size: number
  modified_at: string
  url: string
}

/** 模板创建/更新请求 */
export interface TemplateCreateRequest {
  key: string
  name: string
  description?: string
  category: string
  thumbnail_url?: string
  inputs_config: Record<string, any>[]
  steps_config: Record<string, any>[]
  script_template_id?: number
  tags?: string[]
  is_public?: boolean
}

export interface TemplateUpdateRequest {
  name?: string
  description?: string
  category?: string
  thumbnail_url?: string
  inputs_config?: Record<string, any>[]
  steps_config?: Record<string, any>[]
  script_template_id?: number
  tags?: string[]
  is_public?: boolean
  output_mapping?: Record<string, any>
  estimated_credits?: number
  estimated_time_minutes?: number
}

// =====================================================
// 流水线模板 API
// =====================================================

/**
 * 获取流水线模板列表
 */
export function getPipelineTemplates(params: PipelineListParams = {}): Promise<ListResult<PipelineTemplate>> {
  return client.get('/api/pipeline/templates', { params })
}

/**
 * 获取流水线模板详情
 */
export function getPipelineTemplateDetail(id: number): Promise<PipelineTemplate> {
  return client.get(`/api/pipeline/templates/${id}`)
}

export function createTemplate(data: TemplateCreateRequest): Promise<PipelineTemplate> {
  return client.post('/api/pipeline/templates', data)
}

/** 下载示例模板 JSON（无需鉴权） */
export function getSampleTemplate(): Promise<{
  version: string
  exported_at: string
  templates: Record<string, any>[]
  script_templates: Record<string, any>[]
  style_presets: Record<string, any>[]
}> {
  return client.get('/api/pipeline/templates/sample')
}

/**
 * 无副作用校验模板结构（不落库、不启动运行）
 * @returns { is_valid: boolean, errors: [{step_key, field, reason}] }
 */
export function validateTemplate(data: Record<string, any>): Promise<{
  is_valid: boolean
  errors: { step_key: string | null; field: string; reason: string }[]
}> {
  return client.post('/api/pipeline/templates/validate', data)
}

export function updateTemplate(id: number, data: TemplateUpdateRequest): Promise<PipelineTemplate> {
  return client.put(`/api/pipeline/templates/${id}`, data)
}

export function deleteTemplate(id: number): Promise<{ message: string; template_id: number }> {
  return client.delete(`/api/pipeline/templates/${id}`)
}

/**
 * 获取模板场景预设列表
 */
export function getTemplateScenarios(): Promise<{ items: TemplateScenario[]; total: number }> {
  return client.get('/api/pipeline/template-scenarios')
}

/**
 * 获取可用的模型列表
 * @param modelType 可选过滤条件：image/video/chat
 */
export function getAvailableModels(modelType?: string): Promise<{ items: any[]; total: number }> {
  const params = modelType ? { model_type: modelType } : {}
  return client.get('/api/pipeline/available-models', { params })
}

/**
 * 从场景预设创建模板
 */
export function createTemplateFromScenario(data: TemplateFromScenarioRequest): Promise<PipelineTemplate> {
  return client.post('/api/pipeline/templates/from-scenario', data)
}

/** 提交模板到公开市场审核 */
export function submitTemplatePublic(id: number, reason?: string): Promise<{
  message: string
  template_id: number
  is_public: boolean
  is_approved: boolean
  rejected?: boolean
  hit_words?: string[]
}> {
  return client.post(`/api/pipeline/templates/${id}/submit-public`, { reason })
}

/** 取消模板公开 */
export function cancelTemplatePublic(id: number): Promise<{
  message: string
  template_id: number
  is_public: boolean
}> {
  return client.post(`/api/pipeline/templates/${id}/cancel-public`)
}

/** 获取模板的 pending 修订草稿（编辑器进入时拉取恢复未保存草稿） */
export function getTemplateRevision(id: number): Promise<PipelineTemplateRevision> {
  return client.get(`/api/pipeline/templates/${id}/revision`)
}

/** AI 生成模板缩略图（按 name+description+tags 调用 Agnes AI 生图） */
export function generateTemplateThumbnail(id: number): Promise<{
  thumbnail_url: string
  template_id: number
}> {
  return client.post(`/api/pipeline/templates/${id}/thumbnail/ai-generate`)
}

/**
 * 预估流水线积分消耗
 */
export function estimatePipelineCredits(
  templateId: number,
  inputs: Record<string, any>
): Promise<CreditEstimateResult> {
  return client.post(`/api/pipeline/templates/${templateId}/estimate-credits`, { inputs })
}

// =====================================================
// 流水线运行 API
// =====================================================

/**
 * 创建并启动流水线
 */
export function createPipelineRun(data: CreateRunRequest): Promise<PipelineRun> {
  return client.post('/api/pipeline/runs', data)
}

/**
 * 获取我的流水线列表
 */
export function getPipelineRuns(params: PipelineListParams & { status?: string; template_id?: number } = {}): Promise<ListResult<PipelineRun>> {
  return client.get('/api/pipeline/runs', { params })
}

/**
 * 获取流水线运行详情
 */
export function getPipelineRunDetail(runId: number): Promise<PipelineRun> {
  return client.get(`/api/pipeline/runs/${runId}`)
}

/**
 * 获取流水线步骤列表
 */
export function getPipelineRunSteps(runId: number): Promise<PipelineStep[]> {
  return client.get(`/api/pipeline/runs/${runId}/steps`)
}

/**
 * 重试失败的流水线
 */
export function retryPipelineRun(runId: number): Promise<PipelineRun> {
  return client.post(`/api/pipeline/runs/${runId}/retry`)
}

/**
 * 重试单个步骤
 */
export function retryPipelineStep(runId: number, stepKey: string): Promise<{ message: string; step_key: string }> {
  return client.post(`/api/pipeline/runs/${runId}/steps/${stepKey}/retry`)
}

/**
 * 取消流水线
 */
export function cancelPipelineRun(runId: number): Promise<{ message: string }> {
  return client.post(`/api/pipeline/runs/${runId}/cancel`)
}

/**
 * 删除流水线运行记录（软删除）
 */
export function deletePipelineRun(runId: number): Promise<{ message: string; run_id: number }> {
  return client.delete(`/api/pipeline/runs/${runId}`)
}

/**
 * 暂停正在运行的流水线
 */
export function pausePipelineRun(runId: number): Promise<{ message: string; run_id: number; status: string }> {
  return client.post(`/api/pipeline/runs/${runId}/pause`)
}

/**
 * 编辑流水线输入参数（paused 状态下）
 */
export function updatePipelineRunInputs(runId: number, inputs: Record<string, any>): Promise<{ message: string; run_id: number; inputs: Record<string, any> }> {
  return client.put(`/api/pipeline/runs/${runId}/inputs`, inputs)
}

/**
 * 导出流水线结果到画布
 */
export function exportRunToCanvas(runId: number): Promise<{ message: string; run_id: number; data: { video: string; scenes: string[] } }> {
  return client.post(`/api/pipeline/runs/${runId}/export-to-canvas`)
}

// ---------- 字幕编辑 ----------

/** 单条字幕结构（与后端 ffmpeg_composite 输出的 subtitles 字段一致） */
export interface SubtitleEntry {
  index: number
  scene_index?: number
  start: number
  end: number
  text: string
}

/** 保存字幕后的响应 */
export interface SaveSubtitlesResult {
  srt_url: string
  subtitles: SubtitleEntry[]
}

/**
 * 保存编辑后的字幕（后端会重新生成 SRT 文件并更新步骤输出）
 */
export function saveRunSubtitles(
  runId: number,
  subtitles: SubtitleEntry[]
): Promise<SaveSubtitlesResult> {
  return client.post(`/api/pipeline/runs/${runId}/subtitles`, { subtitles })
}

// ---------- SSE 端点 ----------

/** 构造 SSE 订阅 URL */
export function buildSSEUrl(runId: number): string {
  return `/api/pipeline/runs/${runId}/events`
}

// =====================================================
// 风格预设 API
// =====================================================

/**
 * 获取风格预设列表
 */
export function getStylePresets(params: PipelineListParams & { is_builtin?: boolean } = {}): Promise<ListResult<StylePreset>> {
  return client.get('/api/pipeline/styles', { params })
}

/**
 * 获取风格预设详情
 */
export function getStylePresetDetail(id: number): Promise<StylePreset> {
  return client.get(`/api/pipeline/styles/${id}`)
}

// =====================================================
// 剧本模板 API
// =====================================================

/**
 * 获取剧本模板列表
 */
export function getScriptTemplates(params: PipelineListParams = {}): Promise<ListResult<ScriptTemplate>> {
  return client.get('/api/pipeline/script-templates', { params })
}

/**
 * 获取剧本模板详情
 */
export function getScriptTemplateDetail(id: number): Promise<ScriptTemplate> {
  return client.get(`/api/pipeline/script-templates/${id}`)
}

// =====================================================
// 资产库 API
// =====================================================

/**
 * 获取资产库列表
 */
export function getAssets(params: PipelineListParams & { asset_type?: string; category?: string } = {}): Promise<ListResult<Asset>> {
  return client.get('/api/pipeline/assets', { params })
}

/**
 * 获取资产详情
 */
export function getAssetDetail(id: number): Promise<Asset> {
  return client.get(`/api/pipeline/assets/${id}`)
}

/**
 * 从生成记录保存为资产
 */
export function saveAssetFromGeneration(data: SaveAssetFromGenerationRequest): Promise<Asset> {
  return client.post('/api/pipeline/assets/save-from-generation', data)
}

// =====================================================
// 流水线产物 API
// =====================================================

/**
 * 获取流水线产物列表
 */
export function getPipelineOutputs(): Promise<{ items: PipelineOutput[]; total: number }> {
  return client.get('/api/pipeline/outputs')
}

// =====================================================
// 字幕重新烧录 / 视频下载
// =====================================================

/** 字幕样式配置 */
export interface SubtitleStyle {
  font_size?: number
  font_color?: string
  box_color?: string
  box_opacity?: number
  position?: 'top' | 'center' | 'bottom'
  margin?: number
}

/** 重新烧录请求 */
export interface RecomposeRequest {
  subtitles?: SubtitleEntry[]
  subtitle_style?: SubtitleStyle
}

/** 重新烧录响应 */
export interface RecomposeResult {
  message: string
  data: {
    final_video_url: string
    srt_url: string
    vtt_url: string
    subtitles: SubtitleEntry[]
    duration_seconds: number
    segments_count: number
  }
}

/**
 * 重新烧录字幕到视频（耗时操作，前端应显示 loading）
 */
export function recomposeVideo(
  runId: number,
  payload: RecomposeRequest
): Promise<RecomposeResult> {
  return client.post(`/api/pipeline/runs/${runId}/recompose`, payload)
}

/**
 * 构造下载视频 URL（带水印参数）
 *
 * 浏览器直接访问此 URL 触发下载（后端设置 Content-Disposition: attachment）
 */
export function buildDownloadUrl(runId: number, withWatermark: boolean = true): string {
  const watermark = withWatermark ? 1 : 0
  return `/api/pipeline/runs/${runId}/download?watermark=${watermark}`
}

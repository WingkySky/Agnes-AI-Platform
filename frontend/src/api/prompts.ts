/* =====================================================
 * 提示词优化 API 封装
 * ===================================================== */

import client from './client'

/** 优化结果（与后端 PromptOptimizeResult 对齐） */
export interface PromptOptimizeResult {
  positive: string
  negative: string
  changes: string[]
  assumptions: string[]
  variants: Array<{ label: string; prompt: string }>
}

export interface PromptOptimizeParams {
  prompt: string
  mode: 'expand' | 'refine' | 'style' | 'model-adapt' | 'reference'
  target: 'image' | 'video'
  context?: { model_id?: string; reference_asset_names?: string[] }
}

/** 优化提示词（结构化返回正负提示词）；响应信封由 client 拦截器解包，直接拿 data */
export function optimizePrompt(params: PromptOptimizeParams): Promise<PromptOptimizeResult> {
  return client.post('/api/prompts/optimize', params, { silent: true })
}

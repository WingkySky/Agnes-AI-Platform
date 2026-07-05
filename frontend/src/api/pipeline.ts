/* =====================================================
 * 风格预设 / 剧本模板 / 资产库 API 封装
 *
 * 说明：创意工坊（WorkshopView）已下线，相关入口归一到"我的项目"
 *       （/projects + ProjectLaunchDialog），本文件仅保留风格预设、
 *       剧本模板、资产库三类共享 API。
 * ===================================================== */

import client from './client'
import type {
  StylePreset,
  ScriptTemplate,
  Asset,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
} from '@/types'

// re-export 类型，方便使用方从 api 文件统一导入
export type {
  StylePreset,
  ScriptTemplate,
  Asset,
  SaveAssetFromGenerationRequest,
  PipelineListParams,
  ListResult,
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

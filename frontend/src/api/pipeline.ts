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
  AssetContainer,
  AssetContainersResponse,
  AssetContainerDetail,
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

// =====================================================
// 剧本模板 API
// =====================================================

/**
 * 获取剧本模板列表
 */
export function getScriptTemplates(params: PipelineListParams = {}): Promise<ListResult<ScriptTemplate>> {
  return client.get('/api/pipeline/script-templates', { params })
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

/**
 * 记录资产「用于生成」使用，递增 use_count
 */
export function useAsset(assetId: number): Promise<{ id: number; use_count: number }> {
  return client.post(`/api/pipeline/assets/${assetId}/use`)
}

// =====================================================
// 创作单元（容器）归组 API
// =====================================================

/**
 * 获取当前用户的创作单元分组列表（含我的资产数）
 */
export function getAssetContainers(): Promise<AssetContainersResponse> {
  return client.get('/api/pipeline/assets/containers')
}

/**
 * 获取某个创作单元内的全部资产
 */
export function getContainerAssets(containerType: string, containerId: string): Promise<AssetContainerDetail> {
  return client.get(`/api/pipeline/assets/container/${encodeURIComponent(containerType)}/${encodeURIComponent(containerId)}`)
}

/**
 * 切换资产分享状态（复用审核管道）
 */
export function updateAssetShare(assetId: number, isPublic: boolean): Promise<{ id: number; is_public: boolean }> {
  return client.patch(`/api/pipeline/assets/${assetId}/share`, { is_public: isPublic })
}

/**
 * 删除资产（含归档影子记录）
 */
export function deleteAsset(assetId: number): Promise<{ id: number }> {
  return client.delete(`/api/pipeline/assets/${assetId}`)
}

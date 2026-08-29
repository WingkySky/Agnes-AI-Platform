/* =====================================================
 * 创意资产库 Store
 * 管理可复用的角色/道具/场景/品牌资产（后端 API 数据）
 * 区别于 stores/canvasAsset.ts（画布媒体资源库，localforage）
 * ===================================================== */

import { defineStore } from 'pinia'
import { getAssets, saveAssetFromGeneration } from '@/api/pipeline'
import type {
  Asset,
  AssetType,
  PipelineListParams,
  ListResult,
  SaveAssetFromGenerationRequest,
} from '@/types'

interface AssetFilter {
  type: AssetType | ''
  search: string
  mine: boolean
}

interface AssetState {
  assets: Asset[]
  currentAsset: Asset | null
  filter: AssetFilter
  loading: boolean
  total: number
  // 「用于生成」待消费资产：资产卡点击「用于生成」写入，生图/视频页 onMounted 读取并清除
  pendingUse: Asset | null
}

export const useAssetStore = defineStore('pipelineAsset', {
  state: (): AssetState => ({
    assets: [],
    currentAsset: null,
    filter: { type: '', search: '', mine: false },
    loading: false,
    total: 0,
    pendingUse: null,
  }),

  actions: {
    /** 加载资产列表 */
    async loadAssets(params?: PipelineListParams) {
      this.loading = true
      try {
        const result: ListResult<Asset> = await getAssets(params || {})
        this.assets = result.items
        this.total = result.total
      } catch (e) {
        console.error('加载资产列表失败:', e)
        throw e
      } finally {
        this.loading = false
      }
    },

    /** 保存生成结果到资产库 */
    async saveFromGeneration(generationId: number, data: Omit<SaveAssetFromGenerationRequest, 'generation_id'>) {
      const payload: SaveAssetFromGenerationRequest = {
        generation_id: generationId,
        ...data,
      }
      return await saveAssetFromGeneration(payload)
    },

    /** 设置筛选条件 */
    setFilter(filter: Partial<AssetFilter>) {
      Object.assign(this.filter, filter)
    },

    clearAll() {
      this.assets = []
      this.currentAsset = null
      this.filter = { type: '', search: '', mine: false }
      this.loading = false
      this.total = 0
      this.pendingUse = null
    },

    /** 设置「用于生成」待消费资产 */
    setPendingUse(asset: Asset) {
      this.pendingUse = asset
    },

    /** 取出并清除「用于生成」待消费资产（生图/视频页 onMounted 调用） */
    consumePendingUse(): Asset | null {
      const a = this.pendingUse
      this.pendingUse = null
      return a
    },
  },
})

// 用户登出时清理
if (typeof window !== 'undefined') {
  window.addEventListener('agnes:user-logout', () => {
    try {
      useAssetStore().clearAll()
    } catch (_) { /* ignore */ }
  })
}

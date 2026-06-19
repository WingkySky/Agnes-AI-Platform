/* =====================================================
 * 统一资源库（assets）
 *  - 管理画布中已生成的图片/视频等可复用资源
 *  - 持久化到 localforage；运行时状态通过 Pinia store 维护
 *  - 资源条目：{ id, type, url, posterUrl, prompt, sourceNodeId, createdAt }
 *    · type: 'image' | 'video'
 *    · url: 资源在线/本地地址
 *    · posterUrl: 视频封面（可选）
 *    · prompt: 生成时使用的提示词（可选）
 *    · sourceNodeId: 来源画布节点 id（可选）
 * ===================================================== */

import { defineStore } from 'pinia'

// ---------- localforage 实例 ----------
// 优先使用动态 import，避免 SSR 场景下直接 require 报错
let assetStoreInstance = null

/**
 * 获取/懒初始化 localforage 实例
 * - key: `agnes_asset_index`，资源 id 的顺序数组
 * - 避免与画布 store 的 key 冲突
 */
async function getAssetStore() {
  if (assetStoreInstance) return assetStoreInstance
  try {
    const localforage = await import('localforage')
    assetStoreInstance = localforage.default.createInstance({
      name: 'agnes-platform',
      storeName: 'assets',
      version: 1.0,
      description: '资源库（图片 / 视频）',
    })
  } catch (e) {
    // 回退到内存 map，避免在不支持 IndexedDB 的环境抛错
    const memoryMap = new Map()
    assetStoreInstance = {
      async getItem(k) { return memoryMap.get(k) ?? null },
      async setItem(k, v) { memoryMap.set(k, v); return v },
      async removeItem(k) { memoryMap.delete(k) },
      async keys() { return Array.from(memoryMap.keys()) },
    }
  }
  return assetStoreInstance
}

const INDEX_KEY = 'agnes_asset_index'

/** 生成唯一 ID */
function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

export const useAssetStore = defineStore('asset', {
  state: () => ({
    /** 运行时的资源数组（持久化字段同步） */
    assets: [],
    /** localforage 是否已加载完成；避免重复 hydrate */
    _storageReady: false,
  }),

  getters: {
    /** 按类型过滤；不传类型时返回全部 */
    getAssetsByType: (state) => (type) => {
      if (!type) return state.assets
      return state.assets.filter((a) => a.type === type)
    },
    /** 按 id 精确查找；找不到时返回 null */
    getAssetById: (state) => (id) => state.assets.find((a) => a.id === id) ?? null,
    /** 按 sourceNodeId 查找（节点引用关系） */
    getAssetsBySourceNode: (state) => (sourceNodeId) =>
      state.assets.filter((a) => a.sourceNodeId === sourceNodeId),
    /** 资源总数 */
    totalCount(state) {
      return state.assets.length
    },
  },

  actions: {
    /**
     * 注册一条新资源
     * - data: { type, url, posterUrl?, prompt?, sourceNodeId?, name? }
     * - 自动补 id / createdAt / updatedAt
     * - 返回新增的完整资源对象
     */
    async registerAsset(data) {
      if (!data || !data.url) {
        // eslint-disable-next-line no-console
        console.warn('[asset] registerAsset 缺少 url')
        return null
      }
      const now = new Date().toISOString()
      const asset = {
        id: uid(),
        type: data.type ?? 'image',
        url: data.url,
        posterUrl: data.posterUrl ?? '',
        prompt: data.prompt ?? '',
        name: data.name ?? '',
        sourceNodeId: data.sourceNodeId ?? null,
        createdAt: now,
        updatedAt: now,
      }
      this.assets.unshift(asset)
      await this._persist()
      return asset
    },

    /** 按 id 删除资源 */
    async removeAsset(id) {
      const idx = this.assets.findIndex((a) => a.id === id)
      if (idx === -1) return false
      this.assets.splice(idx, 1)
      await this._persist()
      return true
    },

    /** 更新已存在的资源（部分字段，保留未更新字段） */
    async updateAsset(id, changes) {
      const asset = this.assets.find((a) => a.id === id)
      if (!asset) return null
      Object.assign(asset, changes, { updatedAt: new Date().toISOString() })
      await this._persist()
      return asset
    },

    /** 清空所有资源 */
    async clearAll() {
      this.assets = []
      await this._persist()
    },

    /** 从 localforage 加载资源到 state（仅执行一次；组件 onMounted 时调用） */
    async hydrate() {
      if (this._storageReady) return
      const store = await getAssetStore()
      try {
        const assets = await store.getItem(INDEX_KEY)
        if (Array.isArray(assets)) {
          this.assets = assets
        }
      } catch {
        // 持久化加载失败时保持空数组
      }
      this._storageReady = true
    },

    /** 写回 localforage（内部方法；外部增删改都会调用） */
    async _persist() {
      try {
        const store = await getAssetStore()
        // 关键：this.assets 是 Pinia Proxy 响应式数组，IndexedDB 无法结构化克隆 Proxy。
        // 必须先 JSON 序列化剥离 Proxy，转成纯数组后再写入，否则会抛 DataCloneError。
        const plain = JSON.parse(JSON.stringify(this.assets))
        await store.setItem(INDEX_KEY, plain)
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('[asset] 持久化失败:', e)
      }
    },
  },
})

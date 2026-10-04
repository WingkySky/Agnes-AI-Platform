/* =====================================================
 * 统一资源库（assets）
 *  - 管理画布中已生成的图片/视频等可复用资源
 *  - 持久化到 localforage；运行时状态通过 Pinia store 维护
 *  - 资源条目：{ id, type, url, posterUrl, prompt, sourceNodeId, hasBlob, createdAt }
 *    · type: 'image' | 'video'
 *    · url: 资源在线/本地地址（本地上传的为运行时 object URL，刷新后由 blob 重建）
 *    · posterUrl: 视频封面（可选）
 *    · prompt: 生成时使用的提示词（可选）
 *    · sourceNodeId: 来源画布节点 id（可选）
 *    · hasBlob: 是否有本地 blob 数据（本地上传的素材为 true）
 *  - 本地上传的文件 Blob 单独存到 localforage 的 `agnes_asset_blob_{id}` key
 *    刷新页面时从 IndexedDB 读取 Blob 重新创建 object URL，确保持久化
 * ===================================================== */

import { defineStore } from 'pinia'
import { uploadCanvasAsset } from '@/api/canvasWorkspace'
import { createAsset } from '@/api/assets'
import { isCloudChannel } from '@/lib/canvas-storage'

// ---------- 本地类型定义 ----------

/** 资源条目 */
interface AssetItem {
  id: string
  type: 'image' | 'video'
  url: string
  posterUrl: string
  prompt: string
  name: string
  sourceNodeId: string | null
  hasBlob: boolean
  createdAt: string
  updatedAt: string
}

/** 注册资源参数 */
interface RegisterAssetData {
  type?: 'image' | 'video'
  url?: string
  blob?: Blob
  posterUrl?: string
  prompt?: string
  sourceNodeId?: string | null
  name?: string
  /** 所属作品标记（统一资产层：入库时写入 assets.work_id） */
  work_id?: number
}

/** localforage 实例接口（用于类型标注） */
interface LocalForageInstance {
  getItem<T = unknown>(key: string): Promise<T | null>
  setItem<T = unknown>(key: string, value: T): Promise<T>
  removeItem(key: string): Promise<void>
  keys(): Promise<string[]>
}

// ---------- State 接口 ----------
interface AssetState {
  /** 运行时的资源数组（持久化字段同步） */
  assets: AssetItem[]
  /** localforage 是否已加载完成；避免重复 hydrate */
  _storageReady: boolean
}

// ---------- localforage 实例 ----------
// 优先使用动态 import，避免 SSR 场景下直接 require 报错
let assetStoreInstance: LocalForageInstance | null = null

/**
 * 获取/懒初始化 localforage 实例
 * - key: `agnes_asset_index`，资源 id 的顺序数组
 * - 避免与画布 store 的 key 冲突
 */
async function getAssetStore(): Promise<LocalForageInstance> {
  if (assetStoreInstance) return assetStoreInstance
  try {
    const localforage = await import('localforage')
    /** createInstance 返回类型是 LocalForage 超集，此处向上转型为接口子集，安全等价 */
    assetStoreInstance = localforage.default.createInstance({
      name: 'agnes-platform',
      storeName: 'assets',
      version: 1.0,
      description: '资源库（图片 / 视频）',
    }) as LocalForageInstance
  } catch (_e) {
    // 回退到内存 map，避免在不支持 IndexedDB 的环境抛错
    const memoryMap = new Map<string, unknown>()
    assetStoreInstance = {
      async getItem<T = unknown>(k: string): Promise<T | null> { return (memoryMap.get(k) ?? null) as T | null },
      async setItem<T = unknown>(k: string, v: T): Promise<T> { memoryMap.set(k, v); return v },
      async removeItem(k: string): Promise<void> { memoryMap.delete(k) },
      async keys(): Promise<string[]> { return Array.from(memoryMap.keys()) },
    }
  }
  return assetStoreInstance
}

const BASE_INDEX_KEY = 'agnes_asset_index'
const BASE_BLOB_KEY_PREFIX = 'agnes_asset_blob_'

/** 当前绑定的用户标识；空值为 "anon"（匿名） */
let _currentUserKey: string = 'anon'

/** 计算当前用户的资源索引 key */
function indexKey(): string {
  return `${BASE_INDEX_KEY}_${_currentUserKey}`
}

/** 计算当前用户下指定 id 的 Blob key */
function blobKey(id: string): string {
  return `${BASE_BLOB_KEY_PREFIX}${_currentUserKey}_${id}`
}

/** 强制切换用户数据空间；重置 _storageReady 以便重新 hydrate */
function switchAssetUser(userId: number | string | null): void {
  _currentUserKey = userId ? 'u_' + String(userId) : 'anon'
}

/** 生成唯一 ID */
function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

export const useAssetStore = defineStore('asset', {
  state: (): AssetState => ({
    /** 运行时的资源数组（持久化字段同步） */
    assets: [],
    /** localforage 是否已加载完成；避免重复 hydrate */
    _storageReady: false,
  }),

  getters: {
    /** 按类型过滤；不传类型时返回全部 */
    getAssetsByType: (state) => (type?: 'image' | 'video'): AssetItem[] => {
      if (!type) return state.assets
      return state.assets.filter((a) => a.type === type)
    },
    /** 按 id 精确查找；找不到时返回 null */
    getAssetById: (state) => (id: string): AssetItem | null => state.assets.find((a) => a.id === id) ?? null,
    /** 按 sourceNodeId 查找（节点引用关系） */
    getAssetsBySourceNode: (state) => (sourceNodeId: string): AssetItem[] =>
      state.assets.filter((a) => a.sourceNodeId === sourceNodeId),
    /** 资源总数 */
    totalCount(state): number {
      return state.assets.length
    },
  },

  actions: {
    /**
     * 注册一条新资源
     * - data: { type, url?, blob?, posterUrl?, prompt?, sourceNodeId?, name? }
     * - 如果传入 blob（本地上传的 File 对象），将 Blob 持久化到 IndexedDB，
     *   并创建运行时 object URL 作为 url
     * - 如果传入 url（如生成结果的在线 URL），直接使用
     * - 自动补 id / createdAt / updatedAt
     * - 返回新增的完整资源对象
     */
    async registerAsset(data: RegisterAssetData): Promise<AssetItem | null> {
      if (!data || (!data.url && !data.blob)) {
        // eslint-disable-next-line no-console
        console.warn('[asset] registerAsset 缺少 url 或 blob')
        return null
      }
      let id = uid()
      const now = new Date().toISOString()
      let url = data.url ?? ''
      let hasBlob = false

      // 本地上传的文件：Blob 持久化到 IndexedDB；登录态先传云端拿持久 URL
      // （节点直接引用远程 URL，换设备不依赖本地数据；上传失败降级 objectURL，行为同旧版）
      if (data.blob) {
        const store = await getAssetStore()
        await store.setItem(blobKey(id), data.blob)
        hasBlob = true
        if (isCloudChannel()) {
          try {
            const resp = await uploadCanvasAsset(data.blob, data.name || `${data.type ?? 'image'}.png`)
            url = resp.url
          } catch (err) {
            // eslint-disable-next-line no-console
            console.warn('[asset] 云端上传失败，降级为本地 blob', err)
          }
        }
        if (!url) url = URL.createObjectURL(data.blob)
      }

      // 统一资产层：云端素材入库，assetId 退役为数字 id（失败降级旧 uid 流程，懒迁移兜底）
      if (isCloudChannel() && url.startsWith('/uploads/')) {
        try {
          const resp = await createAsset({
            url,
            media_type: data.type ?? 'image',
            name: data.name || undefined,
            work_id: data.work_id,
          })
          id = String(resp.id)
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[asset] 资产入库失败，降级为本地 uid', err)
        }
      }

      const asset: AssetItem = {
        id,
        type: data.type ?? 'image',
        url,
        posterUrl: data.posterUrl ?? '',
        prompt: data.prompt ?? '',
        name: data.name ?? '',
        sourceNodeId: data.sourceNodeId ?? null,
        hasBlob,
        createdAt: now,
        updatedAt: now,
      }
      this.assets.unshift(asset)
      await this._persist()
      return asset
    },

    /** 按 id 删除资源 */
    async removeAsset(id: string): Promise<boolean> {
      const idx = this.assets.findIndex((a) => a.id === id)
      if (idx === -1) return false
      const asset = this.assets[idx]
      // 释放运行时 object URL
      if (asset.hasBlob && asset.url) {
        URL.revokeObjectURL(asset.url)
      }
      // 删除 IndexedDB 中的 Blob 数据
      const store = await getAssetStore()
      await store.removeItem(blobKey(id))
      this.assets.splice(idx, 1)
      await this._persist()
      return true
    },

    /** 清空所有资源 */
    async clearAll(): Promise<void> {
      // 释放所有 object URL 并删除 Blob 数据
      const store = await getAssetStore()
      for (const asset of this.assets) {
        if (asset.hasBlob && asset.url) {
          URL.revokeObjectURL(asset.url)
        }
        if (asset.hasBlob) {
          await store.removeItem(blobKey(asset.id))
        }
      }
      this.assets = []
      await this._persist()
    },

    /** 按 id 取本地缓存的 Blob（无 blob 或数据丢失返回 null；迁移时上传用） */
    async getAssetBlob(id: string): Promise<Blob | null> {
      const asset = this.getAssetById(id)
      if (!asset?.hasBlob) return null
      const store = await getAssetStore()
      return await store.getItem<Blob>(blobKey(id))
    },

    /**
     * 懒迁移：把旧 uid 素材入库为统一资产行，返回数字 id（失败/无需迁移返回 null）。
     * - 条目 url 为 /uploads/ 时直接建行（历史上传已落云端）
     * - 条目仅剩 blob（当年上传失败）时先补传云端再建行
     * - 幂等：索引中已存在同 url 的数字 id 条目直接复用
     */
    async migrateUidAsset(uidId: string): Promise<string | null> {
      const asset = this.getAssetById(uidId)
      if (!asset?.url) return null

      // 已迁移过：索引里找到同 url 的数字 id 条目直接复用
      const existing = this.assets.find((a) => /^\d+$/.test(a.id) && a.url === asset.url)
      if (existing) return existing.id

      try {
        let url = asset.url
        if (url.startsWith('blob:')) {
          const blob = await this.getAssetBlob(uidId)
          if (!blob) return null
          const resp = await uploadCanvasAsset(blob, asset.name || `${asset.type}.png`)
          url = resp.url
        }
        if (!url.startsWith('/uploads/')) return null // 远程 URL 的转收入库由后端 ingest 处理，v1 跳过
        const resp = await createAsset({
          url,
          media_type: asset.type,
          name: asset.name || undefined,
        })
        const numericId = String(resp.id)
        // 数字 id 条目进索引（remap 离线可用）；旧 uid 条目保留，其他节点可能仍引用
        this.assets.unshift({ ...asset, id: numericId, url, hasBlob: false })
        await this._persist()
        return numericId
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[asset] uid 懒迁移失败（下次重试）:', uidId, err)
        return null
      }
    },

    /** 从 localforage 加载资源到 state（仅执行一次；组件 onMounted 时调用） */
    async hydrate(): Promise<void> {
      if (this._storageReady) return
      const store = await getAssetStore()
      try {
        const assets = await store.getItem<AssetItem[]>(indexKey())
        if (Array.isArray(assets)) {
          // 为有 blob 的 asset 从 IndexedDB 读取 Blob，重新创建 object URL
          for (const asset of assets) {
            if (asset.hasBlob) {
              const blob = await store.getItem<Blob>(blobKey(asset.id))
              if (blob) {
                asset.url = URL.createObjectURL(blob)
              } else {
                // Blob 数据丢失，标记为不可用
                asset.hasBlob = false
                asset.url = ''
              }
            }
          }
          this.assets = assets
        }
      } catch (_e) {
        // 持久化加载失败时保持空数组
      }
      this._storageReady = true
    },

    /** 写回 localforage（内部方法；外部增删改都会调用） */
    async _persist(): Promise<void> {
      try {
        const store = await getAssetStore()
        // 关键：this.assets 是 Pinia Proxy 响应式数组，IndexedDB 无法结构化克隆 Proxy。
        // 必须先 JSON 序列化剥离 Proxy，转成纯数组后再写入，否则会抛 Data CloneError。
        // 注意：hasBlob 标记会保留，但 Blob 数据本身存在单独的 key 中，不在此数组内。
        const plain = JSON.parse(JSON.stringify(this.assets))
        await store.setItem(indexKey(), plain)
      } catch (e: unknown) {
        // eslint-disable-next-line no-console
        console.warn('[asset] 持久化失败:', e)
      }
    },

    /**
     * 用户切换时切换素材库数据空间
     * - 重置 _storageReady 并重新 hydrate
     */
    async _switchUserStorage(userId: number | string | null): Promise<void> {
      // 先释放当前用户所有资源的 object URL（避免内存泄漏）
      for (const asset of this.assets) {
        if (asset.hasBlob && asset.url) {
          try { URL.revokeObjectURL(asset.url) } catch (_e) { /* ignore */ }
        }
      }
      this.assets = []
      switchAssetUser(userId)
      this._storageReady = false
      await this.hydrate()
    },
  },
})

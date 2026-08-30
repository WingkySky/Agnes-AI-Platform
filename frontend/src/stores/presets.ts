/* =====================================================
 * 统一预设广场 Store — Pinia 状态管理
 * - 列表（tab/类型/分类/搜索/排序/分页）+ 收藏 + 使用记录
 * - 画廊组件（PresetGallery）与生成页弹窗共用本 store
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getPresets,
  createPreset as apiCreatePreset,
  updatePreset as apiUpdatePreset,
  deletePreset as apiDeletePreset,
  toggleFavorite as apiToggleFavorite,
  recordPresetUse,
} from '@/api/presets'
import type {
  PromptPreset,
  PresetCreate,
  PresetUpdate,
  PresetQueryParams,
  PresetTab,
  PresetSort,
  PresetContext,
} from '@/types/preset'
import { buildApplyPayload, type PresetApplyResult } from '@/utils/presetApply'

export const PAGE_SIZE = 24

export const usePresetStore = defineStore('presets', () => {
  /* ==== 状态 ==== */

  /** 当前列表 */
  const items = ref<PromptPreset[]>([])
  const total = ref(0)
  const loading = ref(false)

  /** 查询条件 */
  const tab = ref<PresetTab>('plaza')
  const presetType = ref<string | undefined>(undefined)
  const category = ref<string | undefined>(undefined)
  const q = ref('')
  const sort = ref<PresetSort>('new')
  const page = ref(1)

  const hasMore = computed(() => items.value.length < total.value)

  /* ==== 查询 ==== */

  async function fetchList() {
    loading.value = true
    try {
      const params: PresetQueryParams = {
        tab: tab.value,
        sort: sort.value,
        page: page.value,
        page_size: PAGE_SIZE,
      }
      if (presetType.value) params.type = presetType.value
      if (category.value) params.category = category.value
      if (q.value.trim()) params.q = q.value.trim()
      const result = await getPresets(params)
      if (page.value === 1) {
        items.value = result.items
      } else {
        items.value = [...items.value, ...result.items]
      }
      total.value = result.total
    } catch (e) {
      console.error('获取预设列表失败:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  /** 重置到第一页并刷新 */
  async function refresh() {
    page.value = 1
    await fetchList()
  }

  async function setTab(value: PresetTab) {
    tab.value = value
    category.value = undefined
    if (value === 'recent') sort.value = 'new'
    await refresh()
  }

  async function setType(value: string | undefined) {
    presetType.value = value
    category.value = undefined
    await refresh()
  }

  async function setCategory(value: string | undefined) {
    category.value = value
    await refresh()
  }

  async function setSearch(value: string) {
    q.value = value
    await refresh()
  }

  async function setSort(value: PresetSort) {
    sort.value = value
    await refresh()
  }

  async function loadMore() {
    if (!hasMore.value || loading.value) return
    page.value += 1
    await fetchList()
  }

  /* ==== 收藏 / 使用 / 挂载 ==== */

  /** 收藏/取消收藏（toggle，本地状态同步） */
  async function toggleFavorite(preset: PromptPreset): Promise<void> {
    const result = await apiToggleFavorite(preset.id)
    preset.is_favorite = result.is_favorite
    // 从"我的收藏"取消收藏时移除本地条目
    if (!result.is_favorite && tab.value === 'favorites') {
      items.value = items.value.filter((i) => i.id !== preset.id)
      total.value = Math.max(0, total.value - 1)
    }
  }

  /**
   * 已挂载预设——按生成模块上下文隔离（image / video 各自独立）。
   * 生图页挂的不会出现在生视频页；同一会话内回到原模块仍保留，刷新即清空。
   * 风格 / 运镜在各自上下文内互斥单选（新换旧），特效可叠加多选。
   */
  const mountedByContext = ref<Record<'image' | 'video', PromptPreset[]>>({
    image: [],
    video: [],
  })

  /** 当前上下文已挂载列表（admin 上下文不支持挂载，返回空） */
  function mountedFor(context: 'image' | 'video'): PromptPreset[] {
    return mountedByContext.value[context] || []
  }

  function isMountedIn(context: 'image' | 'video', id: number): boolean {
    return (mountedByContext.value[context] || []).some((p) => p.id === id)
  }

  function unmountPreset(context: 'image' | 'video', id: number): void {
    const list = mountedByContext.value[context] || []
    mountedByContext.value[context] = list.filter((p) => p.id !== id)
  }

  /**
   * 挂载/取消挂载（toggle）：挂载即记录一次使用（失败静默降级）。
   * 返回挂载后状态（true=已挂载 / false=已移除）。
   */
  async function mountPreset(preset: PromptPreset, context: 'image' | 'video'): Promise<boolean> {
    const list = mountedByContext.value[context] || []
    if (list.some((p) => p.id === preset.id)) {
      mountedByContext.value[context] = list.filter((p) => p.id !== preset.id)
      return false
    }
    // 风格 / 运镜互斥单选：替换同类型已挂载项
    const next = (preset.type === 'style' || preset.type === 'camera')
      ? list.filter((p) => p.type !== preset.type)
      : [...list]
    next.push(preset)
    mountedByContext.value[context] = next
    recordPresetUse(preset.id).catch((e) => {
      console.warn('预设使用记录上报失败:', e)
    })
    return true
  }

  /**
   * 应用预设：上报使用记录（失败静默降级，不阻塞应用动作），
   * 返回应用载荷供页面写入输入框/运镜标签。
   */
  async function applyPreset(preset: PromptPreset): Promise<PresetApplyResult> {
    recordPresetUse(preset.id).catch((e) => {
      console.warn('预设使用记录上报失败:', e)
    })
    return buildApplyPayload(preset)
  }

  /* ==== 管理（我的预设） ==== */

  async function createPreset(data: PresetCreate): Promise<PromptPreset> {
    const preset = await apiCreatePreset(data)
    if (tab.value === 'mine') await refresh()
    return preset
  }

  async function updatePreset(id: number, data: PresetUpdate): Promise<PromptPreset> {
    const preset = await apiUpdatePreset(id, data)
    const index = items.value.findIndex((p) => p.id === id)
    if (index !== -1) items.value[index] = preset
    return preset
  }

  async function deletePreset(id: number): Promise<void> {
    await apiDeletePreset(id)
    items.value = items.value.filter((p) => p.id !== id)
    total.value = Math.max(0, total.value - 1)
  }

  return {
    items,
    total,
    loading,
    tab,
    presetType,
    category,
    q,
    sort,
    page,
    hasMore,
    fetchList,
    refresh,
    setTab,
    setType,
    setCategory,
    setSearch,
    setSort,
    loadMore,
    toggleFavorite,
    mountedByContext,
    mountedFor,
    isMountedIn,
    mountPreset,
    unmountPreset,
    applyPreset,
    createPreset,
    updatePreset,
    deletePreset,
  }
})

/** 各上下文可见的预设类型与默认选中类型 */
export const CONTEXT_TYPES: Record<PresetContext, { types: string[]; defaultType: string }> = {
  image: { types: ['style', 'prompt', 'script'], defaultType: 'style' },
  video: { types: ['effect', 'style', 'camera', 'prompt', 'script'], defaultType: 'effect' },
  admin: { types: ['style', 'effect', 'camera', 'prompt', 'script'], defaultType: 'style' },
}

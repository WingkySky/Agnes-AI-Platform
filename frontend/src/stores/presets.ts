/* =====================================================
 * 提示词预设 Store — Pinia 状态管理
 * - presets 列表 / currentType / filters / loading
 * - fetchPresets / createPreset / updatePreset / deletePreset
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getPresets,
  createPreset as apiCreatePreset,
  updatePreset as apiUpdatePreset,
  deletePreset as apiDeletePreset,
} from '@/api/presets'
import type { PromptPreset, PresetCreate, PresetUpdate, PresetQueryParams, PresetType, PresetSort } from '@/types/preset'

export const usePresetStore = defineStore('presets', () => {
  /* ==== 状态 ==== */

  /** 预设列表 */
  const presets = ref<PromptPreset[]>([])

  /** 总数 */
  const total = ref(0)

  /** 当前选中的预设类型 Tab */
  const currentType = ref<PresetType | undefined>(undefined)

  /** 筛选条件 */
  const filters = ref<PresetQueryParams>({
    sort: 'new',
    limit: 100,
    offset: 0,
  })

  /** 加载中 */
  const loading = ref(false)

  /* ==== 计算属性 ==== */

  /** 是否有更多数据 */
  const hasMore = computed(() => presets.value.length < total.value)

  /* ==== Actions ==== */

  /** 获取预设列表 */
  async function fetchPresets(params?: Partial<PresetQueryParams>) {
    if (loading.value) return
    loading.value = true

    // 合并筛选条件
    const queryParams: PresetQueryParams = {
      ...filters.value,
      ...params,
    }

    try {
      const result = await getPresets(queryParams)
      presets.value = result.items
      total.value = result.total
      filters.value = queryParams
    } catch (e) {
      console.error('获取预设列表失败:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  /** 切换类型 Tab */
  function setType(type: PresetType | undefined) {
    currentType.value = type
    filters.value = {
      ...filters.value,
      type,
      offset: 0,
    }
    return fetchPresets()
  }

  /** 设置搜索关键词 */
  function setSearch(search: string | undefined) {
    filters.value = {
      ...filters.value,
      search,
      offset: 0,
    }
    return fetchPresets()
  }

  /** 设置排序 */
  function setSort(sort: PresetSort) {
    filters.value = {
      ...filters.value,
      sort,
      offset: 0,
    }
    return fetchPresets()
  }

  /** 创建预设 */
  async function createPreset(data: PresetCreate): Promise<PromptPreset> {
    const preset = await apiCreatePreset(data)
    // 刷新列表
    await fetchPresets()
    return preset
  }

  /** 更新预设 */
  async function updatePreset(id: number, data: PresetUpdate): Promise<PromptPreset> {
    const preset = await apiUpdatePreset(id, data)
    // 更新本地列表中的条目
    const index = presets.value.findIndex((p) => p.id === id)
    if (index !== -1) {
      presets.value[index] = preset
    }
    return preset
  }

  /** 删除预设 */
  async function deletePreset(id: number): Promise<void> {
    await apiDeletePreset(id)
    // 从本地列表中移除
    presets.value = presets.value.filter((p) => p.id !== id)
    total.value = Math.max(0, total.value - 1)
  }

  /* ==== 导出 ==== */
  return {
    presets,
    total,
    currentType,
    filters,
    loading,
    hasMore,
    fetchPresets,
    setType,
    setSearch,
    setSort,
    createPreset,
    updatePreset,
    deletePreset,
  }
})

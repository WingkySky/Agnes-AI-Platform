/* =====================================================
 * 时间线弹性布局状态管理 — Phase 2 增强
 * 职责：
 *   - 素材库宽度 / 隐藏状态 / 时间线高度
 *   - localforage 持久化（按 project_id 分键）
 * ===================================================== */

import { ref, watch, type Ref } from 'vue'
import localforage from 'localforage'
import type { TimelineLayoutState } from '@/types/project'

// 默认布局参数
const DEFAULT_LAYOUT: TimelineLayoutState = {
  libraryWidth: 240,
  libraryHidden: false,
  timelineHeight: 240,
}

// 素材库宽度限制
const MIN_LIBRARY_WIDTH = 180
const MAX_LIBRARY_WIDTH = 400
// 时间线高度限制
const MIN_TIMELINE_HEIGHT = 120
const MAX_TIMELINE_HEIGHT_RATIO = 0.6  // 占视口高度 60%

// localforage 实例：按项目 ID 分键存储布局状态
const layoutStore = localforage.createInstance({
  name: 'agnes-platform',
  storeName: 'timeline-layout',
})

function storageKey(projectId: number) {
  return `timeline_layout_${projectId}`
}

export function useTimelineLayout(projectId: Ref<number | null>) {
  const layout = ref<TimelineLayoutState>({ ...DEFAULT_LAYOUT })
  const loaded = ref(false)

  // 加载指定项目的布局配置
  async function loadLayout() {
    // projectId 可能为 null（如未选中项目时），此时跳过加载
    if (!projectId.value) return
    try {
      const saved = await layoutStore.getItem<TimelineLayoutState>(storageKey(projectId.value))
      if (saved) {
        layout.value = { ...DEFAULT_LAYOUT, ...saved }
      } else {
        layout.value = { ...DEFAULT_LAYOUT }
      }
    } catch (e) {
      console.warn('[useTimelineLayout] load failed', e)
      layout.value = { ...DEFAULT_LAYOUT }
    }
    loaded.value = true
  }

  // 保存当前布局到 localforage
  async function saveLayout() {
    if (!projectId.value) return
    try {
      await layoutStore.setItem(storageKey(projectId.value), layout.value)
    } catch (e) {
      console.warn('[useTimelineLayout] save failed', e)
    }
  }

  // 限制素材库宽度在合法范围内
  function clampLibraryWidth(v: number) {
    return Math.min(MAX_LIBRARY_WIDTH, Math.max(MIN_LIBRARY_WIDTH, v))
  }

  // 限制时间线高度在合法范围内（不超过视口 60%）
  function clampTimelineHeight(v: number) {
    const maxH = window.innerHeight * MAX_TIMELINE_HEIGHT_RATIO
    return Math.min(maxH, Math.max(MIN_TIMELINE_HEIGHT, v))
  }

  // 设置素材库宽度
  function setLibraryWidth(v: number) {
    layout.value.libraryWidth = clampLibraryWidth(v)
    saveLayout()
  }

  // 设置素材库隐藏状态
  function setLibraryHidden(hidden: boolean) {
    layout.value.libraryHidden = hidden
    saveLayout()
  }

  // 切换素材库显示/隐藏
  function toggleLibrary() {
    layout.value.libraryHidden = !layout.value.libraryHidden
    saveLayout()
  }

  // 设置时间线高度
  function setTimelineHeight(v: number) {
    layout.value.timelineHeight = clampTimelineHeight(v)
    saveLayout()
  }

  // projectId 变化时重新加载（immediate：初始化时也会触发，null 时内部跳过）
  watch(projectId, () => { loadLayout() }, { immediate: true })

  return {
    layout,
    loaded,
    setLibraryWidth,
    setLibraryHidden,
    toggleLibrary,
    setTimelineHeight,
    clampLibraryWidth,
    clampTimelineHeight,
    MIN_LIBRARY_WIDTH,
    MAX_LIBRARY_WIDTH,
    MIN_TIMELINE_HEIGHT,
  }
}

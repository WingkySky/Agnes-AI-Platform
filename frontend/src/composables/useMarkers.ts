/* =====================================================
 * 标记 Markers 管理 — Phase 2 增强
 * 职责：
 *   - 在播放头位置添加标记
 *   - 删除离播放头最近的标记
 *   - 跳到上一/下一标记
 * ===================================================== */

import { computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'

export function useMarkers(
  currentTime: Ref<number>,
  seekTo: (time: number) => void,
) {
  const projectStore = useProjectStore()
  const markers = computed(() => projectStore.markers)

  /** 在指定时间添加标记 */
  async function addMarker(time: number, name?: string) {
    try {
      await projectStore.addMarker({ time, name, color: '#4a9eff' })
      ElMessage.success('已添加标记')
    } catch (e: any) {
      ElMessage.error(e?.message || '添加标记失败')
    }
  }

  /** 在播放头位置添加标记（Ctrl+M） */
  async function addMarkerAtPlayhead() {
    await addMarker(currentTime.value)
  }

  /** 删除离播放头最近的标记（Shift+M） */
  async function deleteNearestMarker() {
    if (!markers.value.length) {
      ElMessage.warning('暂无标记')
      return
    }
    const nearest = markers.value.reduce((prev, cur) =>
      Math.abs(cur.time - currentTime.value) < Math.abs(prev.time - currentTime.value) ? cur : prev,
    )
    try {
      await projectStore.removeMarker(nearest.id)
      ElMessage.success('已删除最近标记')
    } catch (e: any) {
      ElMessage.error(e?.message || '删除标记失败')
    }
  }

  /** 跳到上一标记（[） */
  function jumpToPrevMarker() {
    const prevs = markers.value.filter(m => m.time < currentTime.value - 0.01)
    if (!prevs.length) {
      ElMessage.warning('已是第一个标记')
      return
    }
    const prev = prevs[prevs.length - 1]  // 已按 time 升序
    seekTo(prev.time)
  }

  /** 跳到下一标记（]） */
  function jumpToNextMarker() {
    const nexts = markers.value.filter(m => m.time > currentTime.value + 0.01)
    if (!nexts.length) {
      ElMessage.warning('已是最后一个标记')
      return
    }
    const next = nexts[0]
    seekTo(next.time)
  }

  return {
    markers,
    addMarker,
    addMarkerAtPlayhead,
    deleteNearestMarker,
    jumpToPrevMarker,
    jumpToNextMarker,
  }
}

/* =====================================================
 * 轨道状态管理 — Mute / Lock
 * 职责：
 *   - 通过 projectStore.trackStates 读写轨道状态
 *   - 提供 isMuted / isLocked / toggleMuted / toggleLocked 便捷方法
 *   - localforage 持久化（按 project_id 分键）
 * ===================================================== */

import localforage from 'localforage'
import { type Ref } from 'vue'
import { useProjectStore } from '@/stores/project'
import type { TrackState } from '@/types/project'

const trackStateStore = localforage.createInstance({
  name: 'agnes-platform',
  storeName: 'timeline-track-states',
})

function storageKey(projectId: number) {
  return `track_states_${projectId}`
}

export function useTrackStates(projectId: Ref<number | null>) {
  const projectStore = useProjectStore()

  function trackKey(trackType: string, trackIndex: number) {
    return `${trackType}:${trackIndex}`
  }

  function isMuted(trackType: string, trackIndex: number): boolean {
    return projectStore.isTrackMuted(trackType, trackIndex)
  }

  function isLocked(trackType: string, trackIndex: number): boolean {
    return projectStore.isTrackLocked(trackType, trackIndex)
  }

  function toggleMuted(trackType: string, trackIndex: number) {
    const cur = isMuted(trackType, trackIndex)
    projectStore.setTrackMuted(trackType, trackIndex, !cur)
    persist()
  }

  function toggleLocked(trackType: string, trackIndex: number) {
    const cur = isLocked(trackType, trackIndex)
    projectStore.setTrackLocked(trackType, trackIndex, !cur)
    persist()
  }

  async function persist() {
    if (!projectId.value) return
    try {
      await trackStateStore.setItem(storageKey(projectId.value), projectStore.trackStates)
    } catch (e) {
      console.warn('[useTrackStates] persist failed', e)
    }
  }

  async function loadTrackStates() {
    if (!projectId.value) return
    try {
      const saved = await trackStateStore.getItem<Record<string, TrackState>>(storageKey(projectId.value))
      if (saved) {
        projectStore.trackStates = saved
      }
    } catch (e) {
      console.warn('[useTrackStates] load failed', e)
    }
  }

  return {
    isMuted,
    isLocked,
    toggleMuted,
    toggleLocked,
    loadTrackStates,
    persist,
  }
}

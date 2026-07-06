/* =====================================================
 * 片段剪贴板 — 复制/剪切/粘贴
 * 职责：
 *   - 内存剪贴板（不跨页面，不持久化）
 *   - copy：仅存入剪贴板，不删除原片段
 *   - cut：复制到剪贴板并立即删除原片段（调用方负责 pushHistory）
 *   - paste：在目标时间创建新片段，cut 模式 paste 后转为 copy
 * ===================================================== */

import { ref, computed } from 'vue'
import type { TimelineClip, TimelineClipCreateRequest } from '@/types/project'
import { useProjectStore } from '@/stores/project'

interface ClipClipboardEntry {
  clip: TimelineClip
  operation: 'copy' | 'cut'
}

function deepClone(clip: TimelineClip): TimelineClip {
  return JSON.parse(JSON.stringify(clip))
}

/** 从 TimelineClip 构造 CreateRequest（剥离 id/project_id/created_at 等服务端字段） */
function toCreatePayload(clip: TimelineClip, startTime: number): TimelineClipCreateRequest {
  return {
    track_type: clip.track_type,
    track_index: clip.track_index,
    source_type: clip.source_type ?? undefined,
    source_id: clip.source_id ?? undefined,
    shot_id: clip.shot_id ?? undefined,
    start_time: startTime,
    duration: clip.duration,
    trim_start: clip.trim_start,
    trim_end: clip.trim_end ?? undefined,
    transition_type: clip.transition_type,
    transition_duration: clip.transition_duration,
    subtitle_text: clip.subtitle_text ?? undefined,
    sort_order: clip.sort_order,
    source_ref: clip.source_ref ?? undefined,
  }
}

export function useClipClipboard() {
  const projectStore = useProjectStore()
  const clipboard = ref<ClipClipboardEntry | null>(null)
  const hasContent = computed(() => clipboard.value !== null)

  function copy(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'copy' }
  }

  async function cut(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'cut' }
    // 立即删除原片段（pushHistory 由调用方在调用 cut 前完成）
    await projectStore.deleteTimelineClip(clip.id)
  }

  async function paste(targetStartTime: number): Promise<void> {
    if (!clipboard.value) return
    const { clip, operation } = clipboard.value
    // 创建新片段（id 由后端生成）
    await projectStore.createTimelineClip(toCreatePayload(clip, targetStartTime))
    // paste 成功后，cut 模式转为 copy 模式，允许重复粘贴
    if (operation === 'cut') {
      clipboard.value.operation = 'copy'
    }
  }

  function clear() {
    clipboard.value = null
  }

  return { clipboard, hasContent, copy, cut, paste, clear }
}

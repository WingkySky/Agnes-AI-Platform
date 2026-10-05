/* =====================================================
 * 剪辑器 store（Pinia）
 *
 * - document 是唯一事实源：所有编辑经 applyCommand（纯函数命令表）进入
 * - 撤销栈：200 层结构共享快照（lib/editor-history），仅内存
 * - 自动保存：约 2s 节流 PUT 带 base_revision；409 → 本地内容建「冲突副本」工程保底，
 *   当前编辑器转拉远端版本（数据零丢弃，流程仿画布冲突副本）
 * - 视频片段 duration=0 是「送进剪辑器」草稿的显式契约：load 后 healDurations
 *   用媒体元数据补正（直改文档不入撤销栈，随后随保存落库）
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'

import { t } from '@/i18n'
import { applyCanvasOps } from '@/api/canvasWorkspace'
import {
  type EditingProjectBrief,
  createEditorProject,
  getEditorProject,
  previewSubtitleSegments,
  saveEditorDocument,
  submitEditorRender,
  getEditorRenderStatus,
  updateEditorProject,
} from '@/api/editor'
import type { UnifiedAsset } from '@/api/assets'
import { getAsset } from '@/api/assets'
import {
  EditorCommandError,
  applyCommand,
  cmd,
  type EditorCommand,
} from '@/lib/editor-commands'
import { EditorHistory } from '@/lib/editor-history'
import type { EditorDocument } from '@/lib/editor-types'

const AUTOSAVE_INTERVAL_MS = 2000
const RENDER_POLL_MS = 2000

function newId(prefix: string): string {
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10)
  return `${prefix}_${rand}`
}

export const useEditorStore = defineStore('editor', () => {
  // ---------- 工程元信息 ----------
  const uid = ref('')
  const title = ref('')
  const workId = ref<number | null>(null)
  const sourceWorkspaceId = ref<string | null>(null)
  const revision = ref(1)
  const loaded = ref(false)

  // ---------- 文档与编辑态 ----------
  const doc = shallowRef<EditorDocument | null>(null)
  const selectedClipId = ref<string | null>(null)
  const playhead = ref(0)
  const isPlaying = ref(false)
  const history = new EditorHistory()

  // ---------- 保存态 ----------
  const dirty = ref(false)
  const saving = ref(false)
  const lastSavedAt = ref<string | null>(null)

  // ---------- 渲染态 ----------
  const renderStatus = ref<EditingProjectBrief['render_status']>('idle')
  const renderProgress = ref<string | null>(null)
  const renderError = ref<string | null>(null)
  const finalUrl = ref<string | null>(null)

  // ---------- 素材缓存（预览/时间线取 url） ----------
  const assetCache = shallowRef<Map<number, UnifiedAsset>>(new Map())

  async function fetchAsset(assetId: number): Promise<UnifiedAsset | null> {
    const cached = assetCache.value.get(assetId)
    if (cached) return cached
    try {
      const asset = await getAsset(assetId)
      const next = new Map(assetCache.value)
      next.set(assetId, asset)
      assetCache.value = next
      return asset
    } catch {
      return null
    }
  }

  // ---------- 加载 ----------

  async function load(projectUid: string): Promise<void> {
    const detail = await getEditorProject(projectUid)
    uid.value = detail.uid
    title.value = detail.title
    workId.value = detail.work_id
    sourceWorkspaceId.value = detail.source_workspace_id
    revision.value = detail.revision
    doc.value = detail.document
    renderStatus.value = detail.render_status
    renderProgress.value = detail.render_progress
    renderError.value = detail.render_error
    finalUrl.value = detail.final_url
    history.clear()
    dirty.value = false
    loaded.value = true
    void healDurations()
  }

  /** 草稿契约补正：duration<=0 的视频片段用媒体元数据时长回填（不入撤销栈） */
  async function healDurations(): Promise<void> {
    const current = doc.value
    if (!current) return
    const pending = current.clips.filter((c) => c.duration <= 0 && c.assetId != null)
    if (!pending.length) return
    let changed = false
    await Promise.all(pending.map(async (clip) => {
      const asset = await fetchAsset(clip.assetId!)
      if (!asset?.asset_url) return
      const duration = await probeMediaDuration(asset.asset_url)
      if (duration > 0) {
        clip.duration = Math.round(duration * 1000) / 1000
        changed = true
      }
    }))
    if (changed) {
      // 同轨视频片段按时间线顺序重排 start（草稿占位 start 全为累进占位）
      const videos = doc.value!.clips
        .filter((c) => c.trackId.startsWith('v') && doc.value!.tracks.find((t) => t.id === c.trackId)?.kind === 'video')
        .sort((a, b) => a.start - b.start)
      let cursor = 0
      for (const clip of videos) {
        clip.start = cursor
        cursor += clip.duration
      }
      doc.value = { ...doc.value!, clips: [...doc.value!.clips] }
      dirty.value = true
      scheduleSave()
    }
  }

  function probeMediaDuration(url: string): Promise<number> {
    return new Promise((resolve) => {
      const el = document.createElement(url.match(/\.(mp3|wav|m4a|aac)(\?|$)/i) ? 'audio' : 'video')
      el.preload = 'metadata'
      el.onloadedmetadata = () => resolve(el.duration || 0)
      el.onerror = () => resolve(0)
      el.src = url
    })
  }

  // ---------- 命令进入 ----------

  function apply(command: EditorCommand, label: string): void {
    if (!doc.value) return
    const next = applyCommand(doc.value, command)
    history.push({ undoDoc: doc.value, redoDoc: next, label })
    doc.value = next
    dirty.value = true
    scheduleSave()
  }

  function applyOrToast(command: EditorCommand, label: string): boolean {
    try {
      apply(command, label)
      return true
    } catch (err) {
      if (err instanceof EditorCommandError) {
        ElMessage.warning(t(`editor.errors.${err.code}`))
      } else {
        ElMessage.error(t('editor.errors.unknown'))
      }
      return false
    }
  }

  function undo(): void {
    if (!doc.value) return
    const entry = history.undo()
    if (entry) {
      doc.value = entry.undoDoc
      dirty.value = true
      scheduleSave()
    }
  }

  function redo(): void {
    if (!doc.value) return
    const entry = history.redo()
    if (entry) {
      doc.value = entry.redoDoc
      dirty.value = true
      scheduleSave()
    }
  }

  // ---------- 自动保存（节流 + 409 冲突副本） ----------

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) return
    saveTimer = setTimeout(() => {
      saveTimer = null
      void saveNow()
    }, AUTOSAVE_INTERVAL_MS)
  }

  async function saveNow(): Promise<void> {
    if (!doc.value || !uid.value || saving.value || !dirty.value) return
    saving.value = true
    try {
      const result = await saveEditorDocument(uid.value, doc.value, revision.value)
      revision.value = result.revision
      dirty.value = false
      lastSavedAt.value = result.saved_at
    } catch (err) {
      const status = (err as Error & { status?: number }).status
      if (status === 409) await handleConflict()
      else scheduleSave()
    } finally {
      saving.value = false
    }
  }

  /** 409：本地内容建冲突副本工程保底，当前编辑器转拉远端版本（数据零丢弃） */
  async function handleConflict(): Promise<void> {
    if (!doc.value) return
    try {
      await createEditorProject({
        title: `${title.value}（冲突副本）`,
        work_id: workId.value,
        document: doc.value,
      })
      ElMessage.warning(t('editor.conflictCopied'))
    } catch { /* 副本创建失败也继续拉远端，避免卡死 */ }
    const remote = await getEditorProject(uid.value)
    revision.value = remote.revision
    doc.value = remote.document
    dirty.value = false
    history.clear()
    ElMessage.info(t('editor.conflictReloaded'))
  }

  // ---------- 字幕 ----------

  async function transcribeTrack(trackId: string): Promise<void> {
    if (!uid.value) return
    try {
      const { segments } = await previewSubtitleSegments(uid.value, trackId)
      if (!segments.length) {
        ElMessage.info(t('editor.subtitleEmpty'))
        return
      }
      apply(cmd('rebuildSubtitleClips', {
        trackId,
        clips: segments.map((s) => ({ id: newId('sub'), start: s.start, duration: Math.max(s.end - s.start, 0.3), text: s.text })),
      }), t('editor.ops.rebuildSubtitleClips'))
    } catch (err) {
      const detail = (err as Error & { detail?: { message?: string } | string }).detail
      const msg = typeof detail === 'string' ? detail : detail?.message
      ElMessage.error(msg || t('editor.errors.transcribe'))
    }
  }

  // ---------- 渲染 ----------

  async function submitRender(): Promise<void> {
    if (!uid.value) return
    try {
      const status = await submitEditorRender(uid.value, newId('rop'))
      renderStatus.value = status.render_status
      void pollRender()
    } catch (err) {
      const detail = (err as Error & { detail?: { message?: string } | string }).detail
      const msg = typeof detail === 'string' ? detail : detail?.message
      ElMessage.error(msg || t('editor.errors.render'))
    }
  }

  async function pollRender(): Promise<void> {
    if (!uid.value) return
    try {
      const status = await getEditorRenderStatus(uid.value)
      renderStatus.value = status.render_status
      renderProgress.value = status.render_progress
      if (status.render_status === 'succeeded') {
        finalUrl.value = status.final_url
        ElMessage.success(t('editor.renderDone'))
        void writeBackToCanvas()
        return
      }
      if (status.render_status === 'failed') {
        renderError.value = status.render_error
        ElMessage.error(t('editor.renderFailed'))
        return
      }
    } catch { /* 单次轮询失败忽略，继续 */ }
    setTimeout(() => void pollRender(), RENDER_POLL_MS)
  }

  /** 成片回写：来自「送进剪辑器」的工程渲染成功后，成片节点落回来源画布（尽力而为） */
  async function writeBackToCanvas(): Promise<void> {
    if (!sourceWorkspaceId.value || !finalUrl.value) return
    try {
      await applyCanvasOps(sourceWorkspaceId.value, [{
        op: 'add_panel',
        type: 'video',
        name: `${title.value} ${t('editor.finalOutput')}`,
        content: { status: 'success', content: finalUrl.value },
      }])
    } catch {
      ElMessage.info(t('editor.writebackFailed'))
    }
  }

  /** 双击素材兜底：直接加到播放头处（视频/图片→首条视频轨，音频→首条音频轨） */
  async function addAssetAtPlayhead(asset: UnifiedAsset): Promise<void> {
    if (!doc.value) return
    const kind: 'video' | 'audio' = asset.media_type === 'audio' ? 'audio' : 'video'
    const track = doc.value.tracks.find((tr) => tr.kind === kind && tr.flag !== 'locked')
      ?? doc.value.tracks.find((tr) => tr.kind === kind)
    if (!track) {
      ElMessage.warning(t('editor.errors.noTrack'))
      return
    }
    const okAdded = applyOrToast({
      op: 'addClip',
      payload: {
        clip: {
          id: newId('clip'), trackId: track.id, assetId: asset.id,
          start: Math.round(playhead.value * 1000) / 1000,
          duration: asset.media_type === 'image' ? 3 : 0, trimStart: 0, props: {},
        },
      },
    }, t('editor.ops.addClip'))
    if (okAdded && asset.media_type !== 'image') void healDurations()
  }

  async function rename(newTitle: string): Promise<void> {
    if (!uid.value || !newTitle.trim()) return
    const detail = await updateEditorProject(uid.value, { title: newTitle.trim() })
    title.value = detail.title
  }

  function select(clipId: string | null): void {
    selectedClipId.value = clipId
  }

  function reset(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = null
    uid.value = ''
    doc.value = null
    loaded.value = false
    dirty.value = false
    history.clear()
    selectedClipId.value = null
    playhead.value = 0
    renderStatus.value = 'idle'
    finalUrl.value = null
  }

  return {
    uid, title, workId, sourceWorkspaceId, revision, loaded,
    doc, selectedClipId, playhead, isPlaying, history,
    dirty, saving, lastSavedAt,
    renderStatus, renderProgress, renderError, finalUrl,
    assetCache,
    load, fetchAsset, apply, applyOrToast, undo, redo, healDurations, addAssetAtPlayhead,
    saveNow, scheduleSave, transcribeTrack, submitRender, rename,
    select, reset, newId,
  }
})

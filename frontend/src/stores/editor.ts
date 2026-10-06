/* =====================================================
 * 剪辑器 store（Pinia）
 *
 * - document 是唯一事实源：所有编辑经 applyCommand（纯函数命令表）进入
 * - 撤销栈：200 层结构共享快照（lib/editor-history），仅内存
 * - 自动保存：约 2s 节流 PUT 带 base_revision；409 → 本地内容建「冲突副本」工程保底，
 *   当前编辑器转拉远端版本（数据零丢弃，流程仿画布冲突副本）
 * - 视频片段 duration=0 是「送进剪辑器」草稿的显式契约：load 后 healDurations
 *   用媒体元数据补正（纯函数 editor-derive 回填铺开，不入撤销栈，随后随保存落库）
 * - 吸附开关是本地偏好（localStorage 极小配置），不随文档落库
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, shallowRef, watch } from 'vue'
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
import { reflowPlaceholders } from '@/lib/editor-derive'
import { canPlaceOnTrack, findFreeTrack } from '@/lib/editor-placement'
import { probeMediaDuration as probeMediaDurationWithFallback } from '@/lib/editor-media'
import type { EditorDocument, EditorTrack } from '@/lib/editor-types'

const AUTOSAVE_INTERVAL_MS = 2000
const RENDER_POLL_MS = 2000
const SNAP_PREF_KEY = 'agnes_editor_snap'

function newId(prefix: string): string {
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10)
  return `${prefix}_${rand}`
}

function readSnapPref(): boolean {
  try {
    return localStorage.getItem(SNAP_PREF_KEY) !== '0'
  } catch {
    return true
  }
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

  // ---------- 素材临时预览（会话内 UI 态，不入文档/撤销栈/保存） ----------
  // 预览窗画面是 doc+playhead 的派生态：临时预览只盖浮层、不碰这两个值，退出即自动精确恢复
  const previewingAsset = shallowRef<UnifiedAsset | null>(null)

  function startAssetPreview(asset: UnifiedAsset): void {
    previewingAsset.value = asset
    isPlaying.value = false // 防止时间线声音与预览叠音
  }

  function endAssetPreview(): void {
    previewingAsset.value = null
  }

  // 开始播放时间线（空格/播放键）= 回到时间线视图
  watch(isPlaying, (playing) => { if (playing) previewingAsset.value = null })

  // ---------- 本地偏好 ----------
  const snappingEnabled = ref(readSnapPref())

  function setSnapping(enabled: boolean): void {
    snappingEnabled.value = enabled
    try {
      localStorage.setItem(SNAP_PREF_KEY, enabled ? '1' : '0')
    } catch { /* 存储不可用时仅会话内生效 */ }
  }

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

  /** 草稿占位补正：duration<=0 的片段用媒体元数据时长回填（不入撤销栈）。
   * 铺开规则在 lib/editor-derive 纯函数：视频轨占位按原 start 序从最早处顺序铺开，
   * 音频占位按 start 直接定位；不碰用户已摆放的其他片段。 */
  async function healDurations(): Promise<void> {
    const current = doc.value
    if (!current) return
    const pending = current.clips.filter((c) => c.duration <= 0 && c.assetId != null)
    if (!pending.length) return
    const healed = new Map<string, number>()
    await Promise.all(pending.map(async (clip) => {
      const asset = await fetchAsset(clip.assetId!)
      if (!asset?.asset_url) return
      const duration = await probeMediaDuration(asset.asset_url)
      if (duration > 0) healed.set(clip.id, duration)
    }))
    if (!healed.size) return
    doc.value = { ...current, clips: reflowPlaceholders(current, healed) }
    dirty.value = true
    scheduleSave()
  }

  function probeMediaElementDuration(url: string): Promise<number> {
    return new Promise((resolve) => {
      const el = document.createElement(url.match(/\.(mp3|wav|m4a|aac)(\?|$)/i) ? 'audio' : 'video')
      el.preload = 'metadata'
      el.onloadedmetadata = () => resolve(el.duration || 0)
      el.onerror = () => resolve(0)
      el.src = url
    })
  }

  /** 三级探测：mediabunny 容器元数据（WebCodecs 可用时）→ 元素 loadedmetadata 回退 */
  async function probeMediaDuration(url: string): Promise<number> {
    return probeMediaDurationWithFallback(url, probeMediaElementDuration)
  }

  /** 去重防线：同轨同素材落点过近（<80ms）视为重复放置 */
  function hasClipAt(trackId: string, assetId: number, start: number): boolean {
    return !!doc.value?.clips.some(
      (c) => c.trackId === trackId && c.assetId === assetId && Math.abs(c.start - start) < 0.08,
    )
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

  /** 素材落时间线（拖入指定轨 / 双击到播放头共用）：
   * 请求轨放不下（类型不符/锁定/重叠）时回退同类型第一个空闲轨，全满则自动开新轨；
   * 重复落点防线（<80ms）保留 */
  async function placeAsset(asset: UnifiedAsset, at: { trackId: string; start: number }): Promise<void> {
    if (!doc.value) return
    const kind: 'video' | 'audio' = asset.media_type === 'audio' ? 'audio' : 'video'
    const start = Math.round(Math.max(0, at.start) * 1000) / 1000
    let duration = 3
    if (asset.media_type !== 'image') {
      await fetchAsset(asset.id)
      const probed = await probeMediaDuration(asset.asset_url)
      duration = probed > 0 ? probed : 5  // 探测失败兜底，可后续 trim
    }
    const span = { start, duration: Math.round(duration * 1000) / 1000 }
    const requested = doc.value.tracks.find((tr) => tr.id === at.trackId)
    let track: EditorTrack | null =
      requested && requested.kind === kind && requested.flag !== 'locked'
        && canPlaceOnTrack(doc.value.clips.filter((c) => c.trackId === requested.id), span)
        ? requested
        : null
    if (!track) track = findFreeTrack(doc.value, kind, span)
    if (!track) track = await createTrackOfKind(kind)
    if (!track) {
      ElMessage.warning(t('editor.errors.noTrack'))
      return
    }
    if (hasClipAt(track.id, asset.id, start)) return
    const ok = applyOrToast({
      op: 'addClip',
      payload: { clip: { id: newId('clip'), trackId: track.id, assetId: asset.id, start, duration: span.duration, trimStart: 0, props: {} } },
    }, t('editor.ops.addClip'))
    if (ok) endAssetPreview() // 已落时间线，自动回到时间线视图
  }

  /** 自动开一条同类型新轨（放置回退的最后一档） */
  async function createTrackOfKind(kind: 'video' | 'audio'): Promise<EditorTrack | null> {
    if (!doc.value) return null
    const track: EditorTrack = {
      id: newId('track'),
      kind,
      order: doc.value.tracks.filter((tr) => tr.kind === kind).length,
      flag: null,
    }
    if (!applyOrToast({ op: 'addTrack', payload: { track } }, t('editor.ops.addTrack'))) return null
    return doc.value.tracks.find((tr) => tr.id === track.id) ?? null
  }

  /** 双击素材兜底：加到播放头处（放不下自动回退，见 placeAsset） */
  async function addAssetAtPlayhead(asset: UnifiedAsset): Promise<void> {
    if (!doc.value) return
    const kind: 'video' | 'audio' = asset.media_type === 'audio' ? 'audio' : 'video'
    const track = doc.value.tracks.find((tr) => tr.kind === kind && tr.flag !== 'locked')
      ?? doc.value.tracks.find((tr) => tr.kind === kind)
    if (!track) {
      ElMessage.warning(t('editor.errors.noTrack'))
      return
    }
    await placeAsset(asset, { trackId: track.id, start: playhead.value })
  }

  /** 音画分离：视频片段静音，自带音频转投音频轨（放不下自动回退/新建轨） */
  async function detachAudio(clipId: string): Promise<void> {
    if (!doc.value) return
    const clip = doc.value.clips.find((c) => c.id === clipId)
    if (!clip || clip.assetId == null) return
    const asset = await fetchAsset(clip.assetId)
    if (!asset || asset.media_type === 'image') {
      ElMessage.warning(t('editor.detachNoAudio'))
      return
    }
    const track = findFreeTrack(doc.value, 'audio', { start: clip.start, duration: clip.duration })
      ?? await createTrackOfKind('audio')
    if (!track) {
      ElMessage.warning(t('editor.errors.noTrack'))
      return
    }
    applyOrToast({ op: 'detachAudio', payload: { clipId, newId: newId('clip'), trackId: track.id } }, t('editor.ops.detachAudio'))
  }

  /** 播放头处分割选中片段（时间线按钮 / S 键共用） */
  function splitSelectedAtPlayhead(): void {
    const clipId = selectedClipId.value
    if (!clipId || !doc.value) return
    const clip = doc.value.clips.find((c) => c.id === clipId)
    if (!clip) return
    if (playhead.value <= clip.start || playhead.value >= clip.start + clip.duration) {
      ElMessage.warning(t('editor.splitOutsideClip'))
      return
    }
    applyOrToast({ op: 'splitClip', payload: { clipId, at: Math.round(playhead.value * 1000) / 1000, newId: newId('clip') } }, t('editor.ops.splitClip'))
  }

  /** 复制片段到原片段尾部（原轨放不下回退同类型空闲轨/新建轨） */
  async function duplicateClip(clipId: string): Promise<void> {
    const d = doc.value
    if (!d) return
    const clip = d.clips.find((c) => c.id === clipId)
    if (!clip) return
    const track = d.tracks.find((tr) => tr.id === clip.trackId)
    if (!track) return
    const start = Math.round((clip.start + clip.duration) * 1000) / 1000
    let trackId = track.id
    if (track.kind === 'video' || track.kind === 'audio') {
      const span = { start, duration: clip.duration }
      if (!canPlaceOnTrack(d.clips.filter((c) => c.trackId === track.id), span)) {
        const fallback = findFreeTrack(d, track.kind, span) ?? await createTrackOfKind(track.kind)
        if (!fallback) return
        trackId = fallback.id
      }
    }
    applyOrToast({
      op: 'addClip',
      payload: {
        clip: {
          id: newId('clip'), trackId, assetId: clip.assetId, start,
          duration: clip.duration, trimStart: clip.trimStart, props: { ...clip.props },
          ...(clip.text ? { text: clip.text } : {}),
        },
      },
    }, t('editor.ops.addClip'))
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
    previewingAsset.value = null
    renderStatus.value = 'idle'
    finalUrl.value = null
  }

  return {
    uid, title, workId, sourceWorkspaceId, revision, loaded,
    doc, selectedClipId, playhead, isPlaying, history,
    previewingAsset, startAssetPreview, endAssetPreview,
    snappingEnabled, setSnapping,
    dirty, saving, lastSavedAt,
    renderStatus, renderProgress, renderError, finalUrl,
    assetCache,
    load, fetchAsset, apply, applyOrToast, undo, redo, healDurations,
    placeAsset, addAssetAtPlayhead, detachAudio, splitSelectedAtPlayhead, duplicateClip,
    probeMediaDuration,
    saveNow, scheduleSave, transcribeTrack, submitRender, rename,
    select, reset, newId,
  }
})

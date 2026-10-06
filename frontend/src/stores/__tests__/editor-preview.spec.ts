/* 素材临时预览态单测：
 * - 进入预览暂停时间线播放（防叠音），退出清空
 * - 切换素材直接替换预览对象
 * - 时间线开始播放（空格/播放键）自动退出预览
 * - reset 清空预览态 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/canvasWorkspace', () => ({
  applyCanvasOps: vi.fn(async () => ({})),
  uploadCanvasAsset: vi.fn(),
}))
vi.mock('@/api/editor', () => ({
  createEditorProject: vi.fn(),
  getEditorProject: vi.fn(),
  previewSubtitleSegments: vi.fn(),
  saveEditorDocument: vi.fn(),
  submitEditorRender: vi.fn(),
  getEditorRenderStatus: vi.fn(),
  updateEditorProject: vi.fn(),
}))
vi.mock('@/api/assets', () => ({
  getAsset: vi.fn(async () => null),
}))

import { useEditorStore } from '../editor'
import type { UnifiedAsset } from '@/api/assets'

function makeAsset(id: number, mediaType: string): UnifiedAsset {
  return {
    id,
    type: 'video',
    name: `素材${id}`,
    description: null,
    visual_description: null,
    reference_images: [],
    media_type: mediaType,
    asset_url: `/api/files/${id}.mp4`,
    thumb_url: null,
    source: null,
    work_id: null,
    is_public: false,
    moderation_status: 'approved',
    use_count: 0,
    container_type: null,
    container_id: null,
    container_name: null,
    created_at: null,
    updated_at: null,
  }
}

describe('素材临时预览态', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('进入预览暂停播放；退出恢复 null', () => {
    const store = useEditorStore()
    store.isPlaying = true
    store.startAssetPreview(makeAsset(1, 'video'))
    expect(store.previewingAsset?.id).toBe(1)
    expect(store.isPlaying).toBe(false)
    store.endAssetPreview()
    expect(store.previewingAsset).toBeNull()
  })

  it('切换素材直接替换预览对象', () => {
    const store = useEditorStore()
    store.startAssetPreview(makeAsset(1, 'video'))
    store.startAssetPreview(makeAsset(2, 'image'))
    expect(store.previewingAsset?.id).toBe(2)
  })

  it('时间线开始播放自动退出预览', async () => {
    const store = useEditorStore()
    store.startAssetPreview(makeAsset(1, 'video'))
    store.isPlaying = true
    await nextTick() // watch 默认 flush=pre，下一拍才清
    expect(store.previewingAsset).toBeNull()
  })

  it('reset 清空预览态', () => {
    const store = useEditorStore()
    store.startAssetPreview(makeAsset(1, 'audio'))
    store.reset()
    expect(store.previewingAsset).toBeNull()
  })
})

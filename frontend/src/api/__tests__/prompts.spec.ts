/* api/prompts 单测：拦截器已解包 ok() 信封，api 层必须原样透传载荷
 * （回归锁定：曾因多剥一层 r.data.data 抛 "reading 'data'"） */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/api/client', () => ({
  default: { post: mocks.post },
}))

import { optimizePrompt } from '@/api/prompts'

describe('optimizePrompt', () => {
  beforeEach(() => {
    mocks.post.mockReset()
  })

  it('post 到 /api/prompts/optimize 且携带 silent，返回拦截器解包后的载荷', async () => {
    const payload = { positive: 'p', negative: '', changes: [], assumptions: [], variants: [] }
    mocks.post.mockResolvedValue(payload)
    const result = await optimizePrompt({ prompt: '少女', mode: 'refine', target: 'image' })
    expect(mocks.post).toHaveBeenCalledWith(
      '/api/prompts/optimize',
      { prompt: '少女', mode: 'refine', target: 'image' },
      { silent: true },
    )
    expect(result).toEqual(payload)
  })
})

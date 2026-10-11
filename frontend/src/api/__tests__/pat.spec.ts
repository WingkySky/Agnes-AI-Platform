/* api/pat 单测：端点路径与载荷透传（拦截器已解包 ok() 信封，api 层不得再剥层） */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  default: { get: mocks.get, post: mocks.post, delete: mocks.delete },
}))

import { createPat, listPats, revokePat } from '@/api/pat'

describe('api/pat', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.delete.mockReset()
  })

  it('listPats GET /api/auth/pat 原样返回清单', async () => {
    const rows = [{ id: 1, name: 'cli', permission: 'full' }]
    mocks.get.mockResolvedValue(rows)
    expect(await listPats()).toBe(rows)
    expect(mocks.get).toHaveBeenCalledWith('/api/auth/pat')
  })

  it('createPat POST 名称+档位，返回带一次性明文的载荷', async () => {
    const created = { id: 2, name: 'cli', permission: 'readonly', token: 'agn_pat_x' }
    mocks.post.mockResolvedValue(created)
    expect(await createPat('cli', 'readonly')).toEqual(created)
    expect(mocks.post).toHaveBeenCalledWith('/api/auth/pat', { name: 'cli', permission: 'readonly' })
  })

  it('revokePat DELETE /api/auth/pat/{id}', async () => {
    mocks.delete.mockResolvedValue({ revoked: true })
    expect(await revokePat(7)).toEqual({ revoked: true })
    expect(mocks.delete).toHaveBeenCalledWith('/api/auth/pat/7')
  })
})

/* AgentHostPanel 几何纯函数：形态推导/钳位/预设/位置记忆/三态模式 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  HOST_GEOM_KEY, HOST_MODE_KEY, HOST_DOCK_MIN_W, HOST_DOCK_MAX_W,
  clampGeom, clampDockWidth, isExpandedGeom, presetGeom, readGeom, saveGeom,
  readHostModeState, saveHostModeState,
} from '../agent-host-geom'

const store = new Map<string, string>()

beforeEach(() => {
  store.clear()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
    removeItem: (k: string) => { store.delete(k) },
  })
})

afterEach(() => vi.unstubAllGlobals())

describe('isExpandedGeom：形态由宽度推导', () => {
  it('无几何/窄宽=小面板态，≥560=展开态', () => {
    expect(isExpandedGeom(null)).toBe(false)
    expect(isExpandedGeom({ left: 0, top: 0, width: 559, height: 400 })).toBe(false)
    expect(isExpandedGeom({ left: 0, top: 0, width: 560, height: 400 })).toBe(true)
  })
})

describe('clampGeom：视口钳位', () => {
  it('宽高下限 320、左缘触底收回、顶部不为负', () => {
    const g = clampGeom({ left: -500, top: -50, width: 100, height: 100 }, 1280, 720)
    expect(g.width).toBe(320)
    expect(g.height).toBe(320)
    expect(g.top).toBe(0)
    // left 钳到 -width + 80（保留 80px 可见）
    expect(g.left).toBe(-320 + 80)
  })

  it('右/下越界收回视口内', () => {
    const g = clampGeom({ left: 2000, top: 2000, width: 400, height: 400 }, 1280, 720)
    expect(g.left).toBe(1280 - 80)
    expect(g.top).toBe(720 - 48)
  })
})

describe('presetGeom：两档预设', () => {
  it('小面板=右停靠 360×(高-112)', () => {
    const g = presetGeom('small', 1280, 720)
    expect(g.width).toBe(360)
    expect(g.left).toBe(1280 - 360 - 16)
    expect(g.top).toBe(16)
    expect(g.height).toBe(720 - 112)
  })

  it('展开态=居中 86%', () => {
    const g = presetGeom('expanded', 1280, 720)
    expect(g.width).toBe(Math.round(1280 * 0.86))
    expect(g.height).toBe(Math.round(720 * 0.86))
    expect(g.left).toBe(Math.round((1280 - Math.round(1280 * 0.86)) / 2))
  })

  it('展开态在极小视口下收敛（下限被视口上限截断）', () => {
    const g = presetGeom('expanded', 340, 300)
    expect(g.width).toBe(320)
    // 视口仅 300 高：钳位下限 320 被 maxH 截住，不超出视口
    expect(g.height).toBe(300)
  })
})

describe('位置记忆', () => {
  it('saveGeom → readGeom 往返一致；坏 JSON/缺字段回落 null', () => {
    const g = { left: 10, top: 20, width: 360, height: 608 }
    saveGeom(HOST_GEOM_KEY, g)
    expect(readGeom(HOST_GEOM_KEY)).toEqual(g)
    localStorage.setItem(HOST_GEOM_KEY, '{oops')
    expect(readGeom(HOST_GEOM_KEY)).toBeNull()
    localStorage.setItem(HOST_GEOM_KEY, JSON.stringify({ left: 1 }))
    expect(readGeom(HOST_GEOM_KEY)).toBeNull()
  })
})

describe('三态模式记忆', () => {
  it('缺省回 small+未钉+420', () => {
    expect(readHostModeState()).toEqual({ mode: 'small', pinned: false, dockWidth: 420 })
  })

  it('保存回读三态', () => {
    saveHostModeState({ mode: 'dock', pinned: false, dockWidth: 480 })
    expect(readHostModeState()).toEqual({ mode: 'dock', pinned: false, dockWidth: 480 })
    saveHostModeState({ mode: 'small', pinned: true, dockWidth: 420 })
    const s = readHostModeState()
    expect(s.mode).toBe('small')
    expect(s.pinned).toBe(true)
  })

  it('损坏数据与非法 mode 回退缺省', () => {
    localStorage.setItem(HOST_MODE_KEY, '{broken')
    expect(readHostModeState().mode).toBe('small')
    localStorage.setItem(HOST_MODE_KEY, JSON.stringify({ mode: 'weird', dockWidth: 'x' }))
    const s = readHostModeState()
    expect(s.mode).toBe('small')
    expect(s.dockWidth).toBe(420)
  })
})

describe('clampDockWidth', () => {
  it('钳到 240~560 区间', () => {
    expect(clampDockWidth(100, 1920)).toBe(HOST_DOCK_MIN_W)
    expect(clampDockWidth(999, 1920)).toBe(HOST_DOCK_MAX_W)
    expect(clampDockWidth(420, 1920)).toBe(420)
  })

  it('窄屏钳到视口（至少留 56px 页面），但不低于下限', () => {
    expect(clampDockWidth(560, 500)).toBe(444)
    expect(clampDockWidth(420, 800)).toBe(420)  // 放得下不放大
    expect(clampDockWidth(420, 260)).toBe(HOST_DOCK_MIN_W)
  })
})

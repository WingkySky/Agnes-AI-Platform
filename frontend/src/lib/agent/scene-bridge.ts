/* =====================================================
 * 导演台 ↔ Agent 工具层数据桥（b4）
 * 视口页面挂载时注册（提供场景数据读写），卸载时注销；
 * 工具层只面向本接口，不接触 Vue 组件。
 * ===================================================== */

import type { SceneData } from '@/types/scene'

export interface SceneBridgeApi {
  getScene(): SceneData
  /** 应用工具层产出的新场景（整树替换，视口/面板响应式跟随） */
  applyScene(next: SceneData): void
  getSelection(): { type: string; index: number } | null
  getSceneId(): number | null
  getSceneName(): string
}

let bridge: SceneBridgeApi | null = null

export function registerSceneBridge(api: SceneBridgeApi): void {
  bridge = api
}

export function unregisterSceneBridge(): void {
  bridge = null
}

export function getSceneBridge(): SceneBridgeApi | null {
  return bridge
}

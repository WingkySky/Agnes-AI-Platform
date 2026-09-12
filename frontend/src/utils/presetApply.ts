/* =====================================================
 * 预设应用工具 — 把广场预设转换为页面可用的应用载荷
 * 纯函数，无副作用；使用记录由 store 负责上报
 * ===================================================== */

import type { PromptPreset } from '@/types/preset'

/** 预设应用载荷：按预设类型产生不同动作 */
export interface PresetApplyResult {
  /** 追加到提示词输入框的文本（style/effect/prompt 类型） */
  appendText?: string
  /** 负面提示词（仅生视频页填写，生图 API 不支持负面词） */
  negativePrompt?: string
  /** 运镜参数（camera 类型，随生成请求提交） */
  cameraParams?: Record<string, unknown>
  /** 脚本文本（script 类型，复制到剪贴板） */
  scriptText?: string
}

/**
 * 把预设转换为应用载荷（仅 prompt / script 类型）。
 * - prompt：prompt_text 追加
 * - script：script_text 复制
 * style / effect / camera 类型不走此函数，用 composeMounted 挂载式拼接。
 */
export function buildApplyPayload(preset: PromptPreset): PresetApplyResult {
  if (preset.type === 'script') {
    return { scriptText: preset.script_text || '' }
  }
  return { appendText: preset.prompt_text || '' }
}

/** 挂载预设的提交时拼接结果 */
export interface MountedComposition {
  /** 拼接到用户提示词后的文本（'' 表示无） */
  promptSuffix: string
  /** 合并的负面提示词（仅视频侧使用） */
  negativePrompt: string
  /** 运镜参数（随请求提交，后端拼接运镜后缀） */
  cameraParams: Record<string, unknown> | null
}

/**
 * 把已挂载预设（style/effect/camera）合成为提交时拼接内容：
 * - style/effect：prompt_config.suffix 依次拼接（负面词合并）
 * - camera：取运镜参数（单选，挂载时已互斥）
 */
export function composeMounted(mounted: PromptPreset[]): MountedComposition {
  const suffixes: string[] = []
  const negatives: string[] = []
  let cameraParams: Record<string, unknown> | null = null
  for (const p of mounted) {
    if (p.type === 'style' || p.type === 'effect') {
      const cfg = p.prompt_config || {}
      const fragment = cfg.suffix || p.prompt_text || ''
      if (fragment) suffixes.push(fragment)
      if (cfg.negative_prompt) negatives.push(cfg.negative_prompt)
    } else if (p.type === 'camera') {
      cameraParams = (p.camera_params as Record<string, unknown>) || null
    }
  }
  return {
    promptSuffix: suffixes.join('，'),
    negativePrompt: negatives.join('，'),
    cameraParams,
  }
}

/**
 * 把文本追加到当前提示词输入框：
 * 输入框为空直接填入，非空用中文逗号衔接，不做去重（避免误删用户内容）
 */
export function appendPromptText(current: string, addition?: string): string {
  if (!addition) return current
  const trimmed = current.trim()
  if (!trimmed) return addition
  return `${trimmed}，${addition}`
}

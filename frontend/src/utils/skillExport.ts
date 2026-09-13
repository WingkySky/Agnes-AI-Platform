/* =====================================================
 * 技能卡导出（prompt_presets 技能卡 → 主流 Agent 技能格式 SKILL.md）
 * frontmatter 用 yaml 库序列化（name/description/tag），与 skillImport 解析规则互逆
 * ===================================================== */

import { stringify as stringifyYaml } from 'yaml'
import type { PromptPreset } from '@/types/preset'

/** 技能卡 → SKILL.md 文本：frontmatter（name/description/tag）+ 正文 */
export function skillToSkillMd(preset: Pick<PromptPreset, 'name' | 'description' | 'prompt_text' | 'prompt_config'>): string {
  const tag = preset.prompt_config?.tag ?? ''
  const fm: Record<string, string> = { name: preset.name }
  if (preset.description) fm.description = preset.description
  if (tag) fm.tag = tag
  return `---\n${stringifyYaml(fm)}---\n\n${preset.prompt_text.trim()}\n`
}

/* =====================================================
 * SKILL.md 导入解析（传统 Agent 技能格式 → prompt_presets 技能卡）
 *
 * - 主文件 = 以 `---` frontmatter 开头的 .md（对齐主流 Agent 技能格式）
 * - frontmatter 用 yaml 库解析（标准格式用成熟库）；未知键原样存 import_meta
 * - 其余 .md/.txt 按「## 附件：文件名」并入正文；脚本/二进制跳过并报告
 * ===================================================== */

import { parse as parseYaml } from 'yaml'

export interface SkillImportInput {
  name: string
  text: string
}

export interface SkillImportResult {
  name: string
  /** 短标识（/ 快速对齐；frontmatter tag/alias，可空） */
  tag: string
  description: string
  content: string
  /** 非阻断提示（附件并入、兜底命名等） */
  warnings: string[]
  /** 被跳过的文件（脚本/二进制等） */
  skipped: string[]
  /** 记入 prompt_config.import_meta */
  importMeta: { frontmatter: Record<string, unknown>; skipped_files: string[] }
}

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/

function isTextAttachment(name: string): boolean {
  return /\.(md|markdown|txt)$/i.test(name)
}

/** 解析 SKILL.md 导入；致命问题抛中文 Error，调用方直接展示 */
export function parseSkillImport(files: SkillImportInput[]): SkillImportResult {
  if (files.length === 0) throw new Error('未提供任何文件')

  const mainIdx = files.findIndex((f) => FRONTMATTER_RE.test(f.text))
  if (mainIdx === -1) {
    throw new Error('未找到技能主文件：需要一个以 --- frontmatter 开头的 SKILL.md（name/description）')
  }
  const main = files[mainIdx]
  const match = FRONTMATTER_RE.exec(main.text)!
  let fm: Record<string, unknown> = {}
  try {
    const parsed: unknown = parseYaml(match[1])
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      fm = parsed as Record<string, unknown>
    }
  } catch {
    throw new Error('frontmatter 不是合法 YAML，请检查格式')
  }

  const warnings: string[] = []
  const skipped: string[] = []
  const fallbackName = main.name.replace(/\.(md|markdown|txt)$/i, '').trim()

  const name = typeof fm.name === 'string' && fm.name.trim() ? fm.name.trim() : fallbackName
  if (!fm.name) warnings.push(`frontmatter 缺少 name，已用文件名兜底：「${name}」`)
  if (!name) throw new Error('技能名为空：frontmatter 与文件名都未提供有效名称')
  const description = typeof fm.description === 'string' ? fm.description.trim() : ''
  if (!description) warnings.push('frontmatter 缺少 description：技能清单里将没有"何时使用"说明，建议补写')
  const rawTag = typeof fm.tag === 'string' ? fm.tag.trim() : typeof fm.alias === 'string' ? fm.alias.trim() : ''

  let content = main.text.slice(match[0].length).trim()
  if (!content) throw new Error('技能正文为空')

  for (const f of files) {
    if (f === main) continue
    if (isTextAttachment(f.name)) {
      content += `\n\n## 附件：${f.name}\n\n${f.text.trim()}`
      warnings.push(`附件已并入正文：${f.name}`)
    } else {
      skipped.push(f.name)
    }
  }
  if (skipped.length > 0) {
    warnings.push(`已跳过 ${skipped.length} 个脚本/二进制文件（画布 Agent 无代码执行能力）：${skipped.join('、')}`)
  }

  return {
    name,
    tag: rawTag,
    description,
    content,
    warnings,
    skipped,
    importMeta: { frontmatter: fm, skipped_files: skipped },
  }
}

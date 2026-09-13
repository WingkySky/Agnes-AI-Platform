/* =====================================================
 * 技能整包导入解析（zip/文件夹 → 技能卡 + 资源）
 *
 * - 主文件必须名为 SKILL.md（对齐主流 Agent 技能整包格式），frontmatter 用 yaml 库解析
 * - 其余文本文件 → resources（references/脚本一视同仁存档；脚本本期不执行）
 * - 二进制/超限文件跳过并记入 import_meta.skipped_files
 * - frontmatter allowed-tools 解析为产品工具名白名单（映射后为空 = 不限制）
 * ===================================================== */

import { parse as parseYaml } from 'yaml'
import type { SkillResource } from '@/types/preset'
import { AGENT_TOOL_NAMES } from '@/lib/agent/tools'
import { CHAT_TOOL_NAMES } from '@/lib/agent/chat-tools'

export interface SkillImportInput {
  /** 相对路径（zip 内路径或 webkitRelativePath 去公共根，'/' 分隔） */
  path: string
  text: string
}

export interface SkillImportResult {
  name: string
  /** 短标识（/ 快速对齐；frontmatter tag/alias，可空） */
  tag: string
  description: string
  /** SKILL.md 正文（frontmatter 之后） */
  content: string
  /** 其余文本文件（按 SKILL.md 所在目录取相对路径） */
  resources: SkillResource[]
  /** 被跳过的文件（二进制/超限） */
  skipped: string[]
  /** 非阻断提示 */
  warnings: string[]
  /** 映射到产品工具名后的白名单（空 = 不限制） */
  allowedTools: string[]
  /** 记入 prompt_config.import_meta */
  importMeta: {
    frontmatter: Record<string, unknown>
    skipped_files: string[]
    allowed_tools_raw?: string[]
  }
}

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/

/** 资源文本扩展名白名单（其余按二进制跳过） */
const TEXT_RESOURCE_EXTS = /\.(md|markdown|txt|json|yaml|yml|csv|tsv|py|js|mjs|cjs|ts|jsx|tsx|sh|bash|zsh|html?|css|xml|svg|ini|toml|rst|sql)$/i

/** 资源上限：单文件 10 万字符、总量 30 万字符、最多 50 个（防上下文与库表膨胀） */
export const SKILL_RESOURCE_FILE_MAX_CHARS = 100_000
export const SKILL_RESOURCES_MAX_TOTAL_CHARS = 300_000
export const SKILL_RESOURCES_MAX_FILES = 50

/** 产品工具名全集（allowed-tools 映射目标；chat 工具含生成类） */
const PRODUCT_TOOL_NAMES = new Set([...AGENT_TOOL_NAMES, ...CHAT_TOOL_NAMES])

function baseName(path: string): string {
  return path.split('/').pop() || path
}

/** 主文件 = 名为 SKILL.md 的最浅层文件（兼容包外裹一层目录） */
function findMainFile(files: SkillImportInput[]): SkillImportInput {
  const candidates = files.filter((f) => baseName(f.path).toLowerCase() === 'skill.md')
  if (candidates.length === 0) {
    throw new Error('压缩包或文件夹中未找到 SKILL.md（须含 YAML frontmatter：name/description）')
  }
  return candidates.sort((a, b) => a.path.split('/').length - b.path.split('/').length)[0]
}

/** allowed-tools：字符串（逗号分隔，条目可含空格）或数组 → 原始清单；条目支持 "Name(pattern)" 取 Name 部分 */
function parseAllowedToolsRaw(fm: Record<string, unknown>): string[] {
  const v = fm['allowed-tools'] ?? fm.allowed_tools
  const parts = Array.isArray(v) ? v.map(String) : typeof v === 'string' ? v.split(',') : []
  return parts
    .map((s) => (s.includes('(') ? s.slice(0, s.indexOf('(')) : s).trim())
    .flatMap((s) => s.split(/\s+/))
    .filter(Boolean)
}

/** 原始条目 → 产品工具名（大小写不敏感的精确匹配，映射不上即丢弃） */
export function mapAllowedTools(raw: string[]): string[] {
  const lower = new Map([...PRODUCT_TOOL_NAMES].map((n) => [n.toLowerCase(), n]))
  const mapped = new Set<string>()
  for (const item of raw) {
    const hit = lower.get(item.toLowerCase())
    if (hit) mapped.add(hit)
  }
  return [...mapped]
}

/** 解析技能整包；致命问题抛中文 Error，调用方直接展示 */
export function parseSkillPackage(files: SkillImportInput[]): SkillImportResult {
  const cleaned = files
    .map((f) => ({ ...f, path: f.path.replace(/\\/g, '/').replace(/^\.?\//, '') }))
    .filter((f) => f.path && !f.path.endsWith('/'))
  if (cleaned.length === 0) throw new Error('未提供任何文件')

  const main = findMainFile(cleaned)
  const match = FRONTMATTER_RE.exec(main.text)
  if (!match) {
    throw new Error(`SKILL.md（${main.path}）缺少 frontmatter：文件须以 --- 开头的 YAML 头（name/description）`)
  }
  let fm: Record<string, unknown> = {}
  try {
    const parsed: unknown = parseYaml(match[1])
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      fm = parsed as Record<string, unknown>
    }
  } catch {
    throw new Error('SKILL.md frontmatter 不是合法 YAML，请检查格式')
  }

  const warnings: string[] = []
  const skipped: string[] = []
  const fallbackName = baseName(main.path).replace(/\.md$/i, '').trim()

  const name = typeof fm.name === 'string' && fm.name.trim() ? fm.name.trim() : fallbackName
  if (!fm.name) warnings.push(`frontmatter 缺少 name，已用文件名兜底：「${name}」`)
  if (!name) throw new Error('技能名为空：frontmatter 与文件名都未提供有效名称')
  const description = typeof fm.description === 'string' ? fm.description.trim() : ''
  if (!description) warnings.push('frontmatter 缺少 description：技能清单里将没有"何时使用"说明，建议补写')
  const rawTag = typeof fm.tag === 'string' ? fm.tag.trim() : typeof fm.alias === 'string' ? fm.alias.trim() : ''

  const content = main.text.slice(match[0].length).trim()
  if (!content) throw new Error('SKILL.md 正文为空')

  // 资源收集：SKILL.md 所在目录作为技能根，其余文本文件存档；二进制/超限跳过
  const mainDir = main.path.includes('/') ? main.path.slice(0, main.path.lastIndexOf('/') + 1) : ''
  const resources: SkillResource[] = []
  let totalChars = 0
  for (const f of cleaned) {
    if (f === main) continue
    const rel = f.path.startsWith(mainDir) ? f.path.slice(mainDir.length) : f.path
    // zip 内二进制按 utf-8 解码会出现替换符，与 \u0000 一起作为二进制判定
    if (!TEXT_RESOURCE_EXTS.test(rel) || f.text.includes('\u0000') || f.text.includes('\uFFFD')) {
      skipped.push(f.path)
      continue
    }
    const trimmed = f.text.trim()
    if (resources.length >= SKILL_RESOURCES_MAX_FILES || totalChars + trimmed.length > SKILL_RESOURCES_MAX_TOTAL_CHARS) {
      skipped.push(f.path)
      warnings.push(`资源超出上限（最多 ${SKILL_RESOURCES_MAX_FILES} 个 / 总量 ${SKILL_RESOURCES_MAX_TOTAL_CHARS} 字符），已跳过：${f.path}`)
      continue
    }
    if (trimmed.length > SKILL_RESOURCE_FILE_MAX_CHARS) {
      skipped.push(f.path)
      warnings.push(`资源单文件超限（>${SKILL_RESOURCE_FILE_MAX_CHARS} 字符），已跳过：${f.path}`)
      continue
    }
    resources.push({ path: rel, content: trimmed })
    totalChars += trimmed.length
  }
  if (skipped.length > 0) {
    warnings.push(`已跳过 ${skipped.length} 个二进制或超限文件：${skipped.join('、')}`)
  }

  const allowedToolsRaw = parseAllowedToolsRaw(fm)
  const allowedTools = mapAllowedTools(allowedToolsRaw)
  if (allowedToolsRaw.length > 0 && allowedTools.length === 0) {
    warnings.push('allowed-tools 未映射到本产品工具，技能将不限制工具使用（建议经「技能转译」映射）')
  }

  return {
    name,
    tag: rawTag,
    description,
    content,
    resources,
    skipped,
    warnings,
    allowedTools,
    importMeta: {
      frontmatter: fm,
      skipped_files: skipped,
      ...(allowedToolsRaw.length > 0 ? { allowed_tools_raw: allowedToolsRaw } : {}),
    },
  }
}

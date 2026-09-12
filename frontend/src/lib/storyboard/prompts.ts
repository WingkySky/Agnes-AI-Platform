/* =====================================================
 * 分镜提示词模板（lib/storyboard，全项目唯一源）
 *
 * - 实体提取 / 分镜拆分 / 一枪出（plan）三套 LLM 模板
 * - buildFramePrompt：分镜图成品提示词（单帧约束唯一源，收编原三处重复）
 * - buildAssetPrompt：实体卡设定图提示词（角色三视图/空场景/物品图）
 * - 风格段统一由 StyleConfig 渲染（prefix/suffix/negativePrompt）
 * ===================================================== */

import type { EntityKind, StoryboardEntity, StoryboardShot, StyleConfig } from './schemas'
import { EMPTY_STYLE } from './schemas'

/** 分镜图单帧约束：一个镜头只画一个瞬间，防模型把连续动作铺成多格分屏；并禁止画面内出现任何文字 */
export const SINGLE_FRAME_PROMPT_LINE =
  '单帧画面：只表现该镜头的一个瞬间，电影剧照式单画面构图；不出现多格、分屏、四宫格、连环画，不叙述动作先后；画面中不出现任何文字、字幕、台词、标语、标志或水印'

/** 资产卡 -> 设定文本（"名称：描述"） */
export function entityText(e: StoryboardEntity): string {
  return e.name ? `${e.name}：${e.description}` : e.description
}

/** 实体清单 -> 模板注入文本（"名称：描述"逐行；给定实体标注"不得改写"） */
function entityLines(entities: StoryboardEntity[], mustKeep: boolean): string {
  if (entities.length === 0) return '无'
  const keep = mustKeep ? '（必须沿用以下给定设定，不得改写其名称与描述）' : ''
  return entities.map((e) => `- ${entityText(e)}${e.refImageUrl ? `（参考图：${e.refImageUrl}）` : ''}`).join('\n') + keep
}

/** 风格段渲染：prefix/suffix 合成为"画面风格"，negativePrompt 单独成行 */
export function styleSection(style: StyleConfig): string {
  const parts = [style.prefix, style.suffix].map((s) => s.trim()).filter(Boolean)
  if (parts.length === 0 && !style.negativePrompt) return ''
  const lines: string[] = []
  if (parts.length > 0) lines.push(`画面风格：${parts.join('，')}`)
  if (style.negativePrompt) lines.push(`画面避免：${style.negativePrompt}`)
  return lines.join('\n')
}

/** 实体提取模板：从剧本提取角色/场景/物品清单（Agent 实体设定阶段） */
export function extractEntitiesPrompt(scriptText: string): string {
  return `你是专业短剧美术指导。请从剧情中提取实体清单，供后续生成设定图与分镜使用。

## 要求
- 角色 description 写外貌/服饰/气质等可直接用于生成角色三视图设定图的内容
- 场景 description 写环境/时间/氛围，可直接用于生成空场景全景图
- 物品 description 写外观/材质/状态等可视特征，可直接用于生成物品设定图
- 只提取剧情中出现或明确需要的实体，不虚构
- 严格输出 JSON 对象，不要输出任何其他内容

## 剧情
${scriptText}

## 输出格式
{"characters": [{"name": "...", "description": "..."}], "scenes": [{"name": "...", "description": "..."}], "props": [{"name": "...", "description": "..."}]}`
}

/** 分镜拆分模板：给定实体清单，拆分镜并产出画面描述（Agent 分镜提示词阶段） */
export function splitStoryboardPrompt(input: {
  scriptText: string
  characters: StoryboardEntity[]
  scenes: StoryboardEntity[]
  props: StoryboardEntity[]
  cameraVocabulary: string[]
  shotCountMin: number
  shotCountMax: number
}): string {
  const cameraLine = input.cameraVocabulary.length > 0
    ? `运镜从以下词表中选取：${input.cameraVocabulary.join('、')}`
    : '运镜用简短中文描述（如"缓推""手持跟随"）'
  return `你是专业短剧分镜师。请根据剧情概述和给定实体设定，生成结构化分镜脚本。

## 要求
- 镜头数量：${input.shotCountMin} 到 ${input.shotCountMax} 个
- 每个镜头包含：no（序号，从1开始）、shot_size（景别：远景/全景/中景/近景/特写）、camera（机位/运镜）、location（场景名，必须取自场景清单）、characters（出场角色名数组，必须取自角色清单）、props（出场物品名数组，取自物品清单，可为空数组）、description（画面描述）、dialogue（台词，没有则为空字符串）
- ${cameraLine}
- description 必须是单帧画面描述：只表现该镜头的一个瞬间（主体+动作瞬间+场景+光线），镜头内连续动作拆成多个分镜，不叙述先后；包含场景、人物动作、表情、光线；人物以角色名指代，与 characters 字段一致；60~120 字，信息密度优先；台词不写入 description
- 严格输出 JSON 对象，不要输出任何其他内容

## 剧情概述
${input.scriptText}

## 角色设定
${entityLines(input.characters, true)}

## 场景设定
${entityLines(input.scenes, true)}

## 物品设定
${entityLines(input.props, true)}

## 输出格式
{"shots": [{"no": 1, "shot_size": "中景", "camera": "缓推", "location": "...", "characters": ["..."], "props": [], "description": "...", "dialogue": "..."}]}`
}

/** 一枪出模板（剧情 → 实体清单 + 分镜，向导/Composer 快速路径；实体与分镜同次产出） */
export function planStoryboardPrompt(input: {
  scriptText: string
  characters: StoryboardEntity[]
  scenes: StoryboardEntity[]
  style: string
  cameraVocabulary: string[]
  shotCountMin: number
  shotCountMax: number
}): string {
  const cameraLine = input.cameraVocabulary.length > 0
    ? `运镜从以下词表中选取：${input.cameraVocabulary.join('、')}`
    : '运镜用简短中文描述（如"缓推""手持跟随"）'
  const styleLine = input.style ? `## 画面风格\n${input.style}\n` : ''
  return `你是专业短剧分镜师。请根据剧情概述和角色/场景设定，完成两件事：
1. 提取全剧实体清单（角色/场景/物品）；2. 生成结构化分镜脚本。

## 要求
- 镜头数量：${input.shotCountMin} 到 ${input.shotCountMax} 个
- 实体清单：从剧情中提取。角色 description 写外貌/服饰/气质等可直接用于生成角色设定图的内容；场景 description 写环境/时间/氛围；物品 description 写外观/材质/状态等可视特征。若下方已给定角色/场景设定，必须沿用其 name 与描述，不得改写
- 每个镜头包含：no（序号，从1开始）、shot_size（景别：远景/全景/中景/近景/特写）、camera（机位/运镜）、location（场景名，必须取自场景清单）、characters（出场角色名数组，必须取自角色清单）、props（出场物品名数组，取自物品清单，可为空数组）、description（画面描述）、dialogue（台词，没有则为空字符串）
- ${cameraLine}
- description 必须是单帧画面描述：只表现该镜头的一个瞬间（主体+动作瞬间+场景+光线），镜头内连续动作拆成多个分镜，不叙述先后；包含场景、人物动作、表情、光线；人物以角色名指代，与 characters 字段一致；60~120 字，信息密度优先；台词不写入 description
- 台词短句化，符合短剧节奏
- 严格输出 JSON 对象，不要输出任何其他内容
${styleLine}
## 剧情概述
${input.scriptText}

## 已有角色设定
${entityLines(input.characters, true)}

## 已有场景设定
${entityLines(input.scenes, true)}

## 输出格式
{"assets": {"characters": [{"name": "...", "description": "..."}], "scenes": [{"name": "...", "description": "..."}], "props": [{"name": "...", "description": "..."}]}, "shots": [{"no": 1, "shot_size": "中景", "camera": "缓推", "location": "...", "characters": ["..."], "props": [], "description": "...", "dialogue": "..."}]}`
}

/** 分镜图成品提示词：画面描述 + 单帧约束 + 景别/运镜 + 风格 + 实体设定上下文 */
export function buildFramePrompt(
  shot: Pick<StoryboardShot, 'description' | 'shotSize' | 'camera'>,
  contexts: { characters: string[]; scenes: string[]; props?: string[] },
  style: StyleConfig = EMPTY_STYLE,
): string {
  const lines = [shot.description, SINGLE_FRAME_PROMPT_LINE]
  if (shot.shotSize) lines.push(`景别：${shot.shotSize}`)
  if (shot.camera) lines.push(`运镜：${shot.camera}`)
  const styleText = styleSection(style)
  if (styleText) lines.push(styleText)
  if (contexts.characters.length > 0) lines.push(`角色设定：${contexts.characters.join('；')}`)
  if (contexts.scenes.length > 0) lines.push(`场景设定：${contexts.scenes.join('；')}`)
  if (contexts.props && contexts.props.length > 0) lines.push(`物品设定：${contexts.props.join('；')}`)
  return lines.filter(Boolean).join('\n')
}

/** 设定图纯净度约束（不注入剧情，避免把其他角色/动作污染进参考图） */
const ASSET_PURITY: Record<EntityKind, string> = {
  character: '同一角色三视图设定图：正面、侧面、背面全身立绘并排排列，三个视角为同一人物，发型服装完全一致，纯色简洁背景，画面中只有这一个角色，无其他人物，无文字',
  scene: '空场景环境全景，画面中无人物出现，无文字',
  prop: '物品单体设定图：该物品的清晰特写，纯色简洁背景，画面中只有这一个物品，无人物，无文字',
}

const ASSET_LABEL: Record<EntityKind, string> = {
  character: '角色设定图',
  scene: '场景设定图',
  prop: '物品设定图',
}

/** 实体卡设定图提示词：名称 + 描述 + 纯净度约束 + 风格 */
export function buildAssetPrompt(entity: StoryboardEntity, style: StyleConfig = EMPTY_STYLE): string {
  const lines = [
    `${ASSET_LABEL[entity.kind]}：${entity.name || ''}`.trim(),
    entity.description.trim(),
    ASSET_PURITY[entity.kind],
  ]
  const styleText = styleSection(style)
  if (styleText) lines.push(styleText)
  return lines.filter(Boolean).join('\n')
}

/* =====================================================
 * 项目制模板（收编原后端 wizard_chains / extract_entities 的 LLM 模板）
 * ===================================================== */

/** 项目制模板类别（原 wizard_chains.WIZARD_CHAINS 四类） */
export type WizardCategory = 'drama' | 'ad' | 'education' | 'anime'

/** 模板占位符填充：{key} 按 inputs 填充，未知 key 原样保留 */
export function fillTemplate(template: string, inputs: Record<string, unknown>): string {
  return template.replace(/\{(\w+)\}/g, (raw, key: string) =>
    key in inputs && inputs[key] !== undefined && inputs[key] !== null ? String(inputs[key]) : raw,
  )
}

/** 剧本生成模板（收编 wizard_chains 四类 script_prompt，逐字对齐） */
const SCRIPT_PROMPTS: Record<WizardCategory, string> = {
  drama: `请根据以下主题生成一部短剧剧本：
主题：{topic}
风格：{style}
集数：{episodes} 集
单集时长：约 {duration_per_episode} 秒

要求：
1. 包含完整的故事弧线（起因/发展/高潮/结局）
2. 每个场景有明确的地点、时间、人物、动作描述
3. 包含主要角色的对话和旁白
4. 输出纯文本剧本，不要附加说明`,
  ad: `请根据以下信息生成一份广告剧本：
产品：{product}
卖点：{selling_points}
风格：{style}
视频时长：约 {duration} 秒

要求：
1. 包含吸引眼球的开场（前 3 秒）
2. 突出产品卖点和使用场景
3. 包含明确的行动号召（CTA）
4. 输出纯文本剧本`,
  education: `请根据以下信息生成一份教学课件剧本：
教学主题：{topic}
目标年级：{grade}
课件风格：{style}
视频时长：约 {duration} 分钟

要求：
1. 包含知识点拆解和例题讲解
2. 语言通俗易懂，适合目标年级
3. 包含互动提问环节
4. 输出纯文本剧本`,
  anime: `请根据以下信息生成一份动漫剧本：
主角设定：{character}
画风：{style}
故事背景：{story}
图片数量：{num_images} 张

要求：
1. 围绕主角展开故事
2. 每个场景有丰富的视觉描述
3. 包含角色的情感和动作描写
4. 输出纯文本剧本`,
}

export function scriptPrompt(category: WizardCategory, inputs: Record<string, unknown>): string {
  return fillTemplate(SCRIPT_PROMPTS[category], inputs)
}

/** 项目制实体提取模板（字段对齐 ProjectCharacter/Scene/Prop 列） */
export function projectEntitiesPrompt(scriptText: string): string {
  return `请从以下剧本中提取所有角色、场景、道具清单，返回 JSON 格式：
{
  "characters": [{"name": "角色名", "description": "简介", "appearance_desc": "外观描述（用于生图）", "role_type": "main|supporting|minor"}],
  "scenes": [{"name": "场景名", "description": "简介", "location": "地点", "time_of_day": "白天/夜晚/黄昏", "atmosphere": "氛围"}],
  "props": [{"name": "道具名", "description": "简介", "visual_desc": "视觉描述（用于生图）"}]
}
特别注意提取主要角色的详细外观描述（发色/瞳色/服装等）

剧本：
${scriptText}

请确保 JSON 格式正确，不要附加其他说明。`
}

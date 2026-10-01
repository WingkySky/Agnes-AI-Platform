/* =====================================================
 * canvas-emotion — 表情控制纯函数集
 * - 5×5 情绪象限预设（亲近↔疏离 × 激动↔平静），每格一个表情预设
 * - 人脸框 → 编辑区裁切 / 人物参考图 / 生成尺寸 / 只改表情提示词
 * - 生成结果以源图为底、仅在羽化人脸椭圆内混合生成像素（本地合成）
 * 供 CanvasEmotionDialog 与单测使用
 * ===================================================== */

import { t } from '@/i18n'

/** 人脸框（图像像素坐标）；keypoints 为检测关键点（前两位为双眼，用于合成对齐） */
export interface EmotionFaceBox {
  id: string
  x: number
  y: number
  width: number
  height: number
  confidence?: number
  source: 'detected' | 'manual'
  keypoints?: Array<{ x: number; y: number }>
}

/** 头部编辑区（图像像素坐标） */
export interface EmotionEditRegion {
  x: number
  y: number
  width: number
  height: number
}

/** 表情预设 */
export interface EmotionPreset {
  id: string
  labelKey: string
  /** 亲近度 -2(疏离)~2(亲近) */
  intimacy: -2 | -1 | 0 | 1 | 2
  /** 唤醒度 -2(平静)~2(激动) */
  arousal: -2 | -1 | 0 | 1 | 2
  /** 英文表情提示词（生图模型对英文表情词更稳） */
  prompt: string
}

export interface EmotionPromptCharacter {
  name: string
  preset: EmotionPreset
  faceBox: EmotionFaceBox
}

/** 生成前处理产物：编辑区裁切图 + 各角色脸部参考图 + 人脸白椭圆蒙版（上游局部编辑用） */
export interface EmotionArtifacts {
  sourceDataUrl: string
  characterDataUrls: string[]
  /** 黑底白椭圆蒙版（白色=可编辑），与 sourceDataUrl 同尺寸 */
  maskDataUrl: string
  editRegion: EmotionEditRegion
  imageWidth: number
  imageHeight: number
}

/** 确认生成时单个角色的载荷（裁切/提示词由画布按脸逐个构建） */
export interface EmotionCharacterPayload {
  name: string
  presetId: string
  label: string
  intimacy: number
  arousal: number
  faceBox: EmotionFaceBox
}

/** 确认生成时传给画布的完整载荷（逐脸紧裁切生成+合成，宫格等背景像素零改动） */
export interface EmotionGeneratePayload {
  characters: EmotionCharacterPayload[]
  imageWidth: number
  imageHeight: number
  /** 微调模式：对上一轮表情结果单独重抽部分脸（基准回原始图重建，旧伪影不带入） */
  fixContext?: EmotionJobRecord
}

/** 结果节点上持久化的逐脸生成信息（sourcePanelId 恒指向原始源图节点） */
export interface EmotionJobRecord {
  sourcePanelId: string
  allFaces: EmotionCharacterPayload[]
}

/* ---------- 5×5 情绪预设 ---------- */

const MOOD_LABEL_KEYS = [
  ['moodEcstatic', 'moodElated', 'moodSurprised', 'moodShocked', 'moodTerrified'],
  ['moodBeaming', 'moodExpectant', 'moodFocused', 'moodAlert', 'moodTense'],
  ['moodTender', 'moodSoftSmile', 'moodNeutral', 'moodRestrained', 'moodAloof'],
  ['moodReassured', 'moodRelieved', 'moodWeary', 'moodDowncast', 'moodSad'],
  ['moodContent', 'moodSerene', 'moodCold', 'moodHeartbroken', 'moodDespairing'],
] as const

const MOOD_PROMPTS = [
  ['joyful open laughter, bright symmetric grin, lifted cheeks, natural smile lines around the eyes', 'clearly delighted, full warm smile', 'pleasantly surprised, eyes widened, mouth naturally open', 'visibly shocked, eyebrows raised, mouth slightly open', 'intense terror, eyes wide open, face tense'],
  ['natural hearty laughter with smiling eyes', 'expectant and excited, bright expression', 'deeply focused, firm steady gaze', 'vigilant and watchful, brows and eyes slightly tightened', 'nervous and uneasy, lips gently pressed'],
  ['gentle and warm, faint soft smile', 'restrained natural slight smile', 'fully neutral, composed and relaxed', 'suppressing emotion, slightly stiff expression', 'distant and cold, minimal facial emotion'],
  ['at ease and relaxed, soft closed mouth', 'relieved, brows and eyes relaxing', 'visibly tired, drooping eyelids', 'low-spirited, mouth corners slightly dropped', 'sad, inner brows raised, mouth corners down'],
  ['quiet contentment, slight closed-mouth smile', 'calm and serene, relaxed expression', 'cold and reserved, level steady gaze', 'holding back heartache, lips pressed tight, eyes dimmed', 'deep despair, sunken brows and eyes, face losing tension'],
] as const

/** 25 格预设：行=唤醒度（上激动下平静），列=亲近度（左亲近右疏离） */
export const EMOTION_PRESETS: EmotionPreset[] = MOOD_LABEL_KEYS.flatMap((row, rowIndex) =>
  row.map((mood, columnIndex) => {
    const intimacy = (2 - columnIndex) as EmotionPreset['intimacy']
    const arousal = (2 - rowIndex) as EmotionPreset['arousal']
    return {
      id: `emotion-${intimacy}-${arousal}`,
      labelKey: `canvas.imageOps.${mood}`,
      intimacy,
      arousal,
      prompt: MOOD_PROMPTS[rowIndex][columnIndex],
    }
  }),
)

export const NEUTRAL_EMOTION_PRESET = EMOTION_PRESETS.find(p => p.intimacy === 0 && p.arousal === 0)!

export function clampAxis(value: number): EmotionPreset['intimacy'] {
  return Math.max(-2, Math.min(2, Math.round(value))) as EmotionPreset['intimacy']
}

export function findEmotionPreset(intimacy: number, arousal: number): EmotionPreset {
  const x = clampAxis(intimacy)
  const y = clampAxis(arousal)
  return EMOTION_PRESETS.find(p => p.intimacy === x && p.arousal === y) || NEUTRAL_EMOTION_PRESET
}

/** 预设中文名（子节点命名用） */
export function emotionPresetLabel(preset: EmotionPreset): string {
  return t(preset.labelKey)
}

/* ---------- blendshapes（实时预览用，ARKIT 命名，与 facecap.glb morph 字典对齐） ---------- */

export type EmotionBlendshapes = Partial<Record<string, number>>

/** 情绪预设 → 面部混合形状权重（中性返回空对象），L/R 成对输出同一权重 */
export function emotionBlendshapes(preset: EmotionPreset): EmotionBlendshapes {
  if (preset.intimacy === 0 && preset.arousal === 0) return {}
  const warmth = Math.max(0, preset.intimacy / 2)
  const distance = Math.max(0, -preset.intimacy / 2)
  const activation = Math.max(0, preset.arousal / 2)
  const calm = Math.max(0, -preset.arousal / 2)
  const surprise = Math.max(0, activation * (1 - Math.abs(preset.intimacy) / 3))
  const sadness = Math.max(0, calm * (0.35 + distance * 0.65))
  const smile = warmth * (0.24 + activation * 0.48 + calm * 0.12)
  const tension = distance * (0.16 + activation * 0.46 + calm * 0.22)
  const shapes: Record<string, number> = {
    browInnerUp: clamp01(surprise * 0.58 + sadness * 0.42),
    browDown_L: clamp01(tension * 0.7),
    browDown_R: clamp01(tension * 0.7),
    browOuterUp_L: clamp01(activation * 0.22 + surprise * 0.32),
    browOuterUp_R: clamp01(activation * 0.22 + surprise * 0.32),
    eyeBlink_L: clamp01(calm * 0.28),
    eyeBlink_R: clamp01(calm * 0.28),
    eyeSquint_L: clamp01(smile * 0.34 + tension * 0.28),
    eyeSquint_R: clamp01(smile * 0.34 + tension * 0.28),
    eyeWide_L: clamp01(activation * (0.16 + surprise * 0.48 + distance * 0.18)),
    eyeWide_R: clamp01(activation * (0.16 + surprise * 0.48 + distance * 0.18)),
    cheekSquint_L: clamp01(smile * 0.42),
    cheekSquint_R: clamp01(smile * 0.42),
    noseSneer_L: clamp01(tension * activation * 0.35),
    noseSneer_R: clamp01(tension * activation * 0.35),
    jawOpen: clamp01(activation * (0.06 + surprise * 0.34)),
    mouthPucker: clamp01(distance * calm * 0.12),
    mouthClose: clamp01(calm * 0.18 + tension * 0.2),
    mouthSmile_L: clamp01(smile),
    mouthSmile_R: clamp01(smile),
    mouthFrown_L: clamp01(sadness * 0.54 + distance * calm * 0.14),
    mouthFrown_R: clamp01(sadness * 0.54 + distance * calm * 0.14),
    mouthDimple_L: clamp01(warmth * 0.22),
    mouthDimple_R: clamp01(warmth * 0.22),
    mouthShrugUpper: clamp01(sadness * 0.18),
    mouthPress_L: clamp01(tension * 0.48 + calm * distance * 0.18),
    mouthPress_R: clamp01(tension * 0.48 + calm * distance * 0.18),
    mouthStretch_L: clamp01(activation * distance * 0.24),
    mouthStretch_R: clamp01(activation * distance * 0.24),
  }
  return Object.fromEntries(Object.entries(shapes).filter(([, v]) => v > 0.01))
}

/* ---------- 提示词 ---------- */

/** 目标人脸框相对裁切图的像素/中心位置描述 */
function describeEmotionTarget(box: EmotionFaceBox, region: EmotionEditRegion): string {
  const x = clamp(Math.round(box.x - region.x), 0, Math.max(0, region.width - 1))
  const y = clamp(Math.round(box.y - region.y), 0, Math.max(0, region.height - 1))
  const width = Math.max(1, Math.min(region.width - x, Math.round(box.width)))
  const height = Math.max(1, Math.min(region.height - y, Math.round(box.height)))
  const centerX = Math.round(((x + width / 2) / Math.max(1, region.width)) * 100)
  const centerY = Math.round(((y + height / 2) / Math.max(1, region.height)) * 100)
  return `目标人脸框（相对于第一张裁切输入图）：x=${x}px，y=${y}px，width=${width}px，height=${height}px；人脸中心约位于裁切图的 ${centerX}% 横向、${centerY}% 纵向。最终仅将该人脸周围的椭圆区域融合回原图。`
}

/** 组装"只改表情、锁身份"提示词（第一张输入图为编辑区裁切图，其后各张为对应角色的脸部参考图；单角色走久经验证的措辞） */
export function buildEmotionPrompt(characters: EmotionPromptCharacter[], editRegion: EmotionEditRegion): string {
  if (characters.length === 1) {
    const { name, preset, faceBox } = characters[0]
    return [
      `仅修改第一张输入图中“${name}”脸部的表情，其他像素保持源图一致。`,
      `目标情绪：${t(preset.labelKey)}；表情要求：${preset.prompt}。情绪强度通过眉眼、嘴角和脸颊的肌肉张力表达，不要通过夸大嘴巴或重绘整张脸表达。`,
      '第一张输入图是唯一编辑目标，第二张输入图仅用于核对同一人物身份，不得复制第二张图的构图、背景或光线。',
      describeEmotionTarget(faceBox, editRegion),
      '如果第一张输入图中出现其他人脸，其他人脸全部视为不可编辑背景；只允许修改目标人脸框及其邻近表情区域。',
      '只改变眉眼开合、眼角、嘴角、脸颊和口腔内部的表情细节；保持眼睛大小与方向、嘴裂宽度、牙齿数量大小排列、嘴唇厚度、下巴轮廓和脸型自然且与原图一致。',
      '第一张输入图附带编辑范围蒙版：仅椭圆标记的区域（目标人脸及其邻近表情区）允许重绘表情，蒙版外所有像素必须与输入图逐像素一致，绝对不要生成或修改。',
      '保持蒙版区域内外的曝光、色温、对比度和肤色完全一致，不要添加白色雾感、光晕、描边、边框或任何可见覆盖层。',
      '输出图像必须与输入裁切图构图完全对齐：人物头部在画面中的位置、大小和裁切范围保持一致，不得放大、缩小、平移或改变取景。',
      '严格保持人物身份、五官比例、肤色、发型、发丝、耳朵、配饰、服装、姿势、头部朝向、镜头、景深、光线、背景及画面其他人物不变；不要重绘眼镜、帽子或遮挡物。',
      '禁止夸张卡通笑、嘴巴过大或拉宽、牙齿像整齐白墙、露出不自然牙龈、眼睛变形或眯成线、脸颊鼓包、塑料磨皮、重复五官，以及任何身份漂移。',
    ].join('\n')
  }
  const characterLines = characters.map((character, index) =>
    `角色${index + 1}「${character.name}」：${describeEmotionTarget(character.faceBox, editRegion)}目标情绪：${t(character.preset.labelKey)}；表情要求：${character.preset.prompt}。情绪强度通过眉眼、嘴角和脸颊的肌肉张力表达，不要通过夸大嘴巴或重绘整张脸表达。`)
  return [
    `仅修改第一张输入图中以下 ${characters.length} 个角色脸部的表情，其他像素保持源图一致。`,
    ...characterLines,
    `第2张至第${characters.length + 1}张输入图分别对应上述角色1至角色${characters.length}（顺序一一对应），仅用于核对各人物身份，不得复制这些图的构图、背景或光线。`,
    '如果第一张输入图中出现未列为角色的其他人脸，全部视为不可编辑背景；只允许修改上述角色人脸框及其邻近表情区域。',
    '只改变每个角色眉眼开合、眼角、嘴角、脸颊和口腔内部的表情细节；保持每个角色眼睛大小与方向、嘴裂宽度、牙齿数量大小排列、嘴唇厚度、下巴轮廓和脸型自然且与原图一致。',
    '第一张输入图附带编辑范围蒙版：仅椭圆标记的区域（各角色人脸及其邻近表情区）允许重绘表情，蒙版外所有像素必须与输入图逐像素一致，绝对不要生成或修改。',
    '保持蒙版区域内外的曝光、色温、对比度和肤色完全一致，不要添加白色雾感、光晕、描边、边框或任何可见覆盖层。',
    '输出图像必须与输入裁切图构图完全对齐：各角色头部在画面中的位置、大小和裁切范围保持一致，不得放大、缩小、平移或改变取景。',
    '严格保持每个人物身份、五官比例、肤色、发型、发丝、耳朵、配饰、服装、姿势、头部朝向、镜头、景深、光线、背景及画面其他人物不变；不要重绘眼镜、帽子或遮挡物。',
    '禁止夸张卡通笑、嘴巴过大或拉宽、牙齿像整齐白墙、露出不自然牙龈、眼睛变形或眯成线、脸颊鼓包、塑料磨皮、重复五官，以及任何身份漂移。',
  ].join('\n')
}

/* ---------- 几何：人脸框 → 编辑区 ---------- */

export function clampFaceBox(box: EmotionFaceBox, imageWidth: number, imageHeight: number): EmotionFaceBox {
  const x = Math.max(0, Math.min(imageWidth - 1, box.x))
  const y = Math.max(0, Math.min(imageHeight - 1, box.y))
  return {
    ...box,
    x,
    y,
    width: Math.max(1, Math.min(imageWidth - x, box.width)),
    height: Math.max(1, Math.min(imageHeight - y, box.height)),
  }
}

/** 编辑区 = 人脸框四周留出头发/下巴/表情过渡余量，并裁回图像范围 */
export function resolveEmotionEditRegion(box: EmotionFaceBox, imageWidth: number, imageHeight: number): EmotionEditRegion {
  const left = Math.floor(Math.max(0, box.x - box.width * 0.85))
  const top = Math.floor(Math.max(0, box.y - box.height * 0.75))
  const right = Math.ceil(Math.min(imageWidth, box.x + box.width * 1.85))
  const bottom = Math.ceil(Math.min(imageHeight, box.y + box.height * 2))
  return { x: left, y: top, width: Math.max(1, right - left), height: Math.max(1, bottom - top) }
}

/** 编辑区宽高比 → 生成尺寸（接近方图用 1:1，宽图/高图用 3:2） */
export function emotionGenerationSize(region: EmotionEditRegion): string {
  const ratio = region.width / Math.max(1, region.height)
  if (ratio >= 1.2) return '1536x1024'
  if (ratio <= 0.83) return '1024x1536'
  return '1024x1024'
}

/* ---------- 画布操作：裁切 / 合成 ---------- */

async function loadImageBitmap(dataUrl: string): Promise<ImageBitmap> {
  const response = await fetch(dataUrl)
  if (!response.ok) throw new Error(t('canvas.imageOps.emotionImageReadFailed'))
  return createImageBitmap(await response.blob())
}

/** 裁出联合编辑区底图（模型编辑目标）与各角色脸部参考图（身份核对），不再生成蒙版（结果本地合成） */
export async function buildEmotionArtifacts(dataUrl: string, faceBoxes: EmotionFaceBox[], imageWidth: number, imageHeight: number): Promise<EmotionArtifacts> {
  const image = await loadImageBitmap(dataUrl)
  try {
    const width = image.width || imageWidth
    const height = image.height || imageHeight
    const normalized = faceBoxes.map(box => clampFaceBox(box, width, height))
    // 联合编辑区 = 各角色编辑区的并集（单角色时即其自身编辑区）
    const regions = normalized.map(box => resolveEmotionEditRegion(box, width, height))
    const left = Math.min(...regions.map(r => r.x))
    const top = Math.min(...regions.map(r => r.y))
    const right = Math.max(...regions.map(r => r.x + r.width))
    const bottom = Math.max(...regions.map(r => r.y + r.height))
    const editRegion = clampEditRegion({ x: left, y: top, width: right - left, height: bottom - top }, width, height)
    return {
      sourceDataUrl: drawSourceCrop(image, editRegion),
      characterDataUrls: normalized.map(box => drawFaceCrop(image, box, width, height)),
      maskDataUrl: drawFaceMask(editRegion, normalized),
      editRegion,
      imageWidth: width,
      imageHeight: height,
    }
  } finally {
    image.close()
  }
}

/** 人脸椭圆（对齐/混合/蒙版共用）：收紧到表情核心区，边界落在皮肤低频区——
 *  余量过大会让边界穿过头发，模型重绘的发丝与原图错位会显出细弧线接缝 */
export function emotionEditEllipse(box: EmotionFaceBox, region: EmotionEditRegion): { centerX: number; centerY: number; radiusX: number; radiusY: number } {
  const localX = box.x - region.x
  const localY = box.y - region.y
  const expandX = box.width * 0.1
  const expandTop = box.height * 0.1
  const expandBottom = box.height * 0.12
  const width = box.width + expandX * 2
  const height = box.height + expandTop + expandBottom
  return {
    centerX: localX + box.width / 2,
    centerY: localY - expandTop + height / 2,
    radiusX: Math.max(1, width / 2),
    radiusY: Math.max(1, height / 2),
  }
}

/** 逐脸合成入参：源图人脸框 + 生成图中检测到的人脸框（用于取景对齐） */
export interface EmotionBlendFace {
  faceBox: EmotionFaceBox
  /** 生成图中检测到的人脸框；缺省退化为居中覆盖 */
  generatedFaceBox?: EmotionFaceBox
  /** 生成图与源图同坐标系（微调重建：从上一轮结果按椭圆取回已生成的表情），1:1 平移贴回不做任何校正 */
  sameCoords?: boolean
}

// 模型只负责局部重绘；最终结果始终以源图为底，仅在羽化人脸椭圆内混合生成像素。
// 模型重合成时可能平移/缩放取景，有 generatedFaceBox 时按"生成图人脸 → 源图人脸"等比对齐后再混合。
export async function compositeEmotionFaces(sourceDataUrl: string, generatedDataUrl: string, region: EmotionEditRegion, faces: EmotionBlendFace[]): Promise<string> {
  const [source, generated] = await Promise.all([loadImageBitmap(sourceDataUrl), loadImageBitmap(generatedDataUrl)])
  try {
    const normalizedRegion = clampEditRegion(region, source.width, source.height)
    const canvas = document.createElement('canvas')
    canvas.width = source.width
    canvas.height = source.height
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) throw new Error(t('canvas.imageOps.emotionCompositeFailed'))
    context.drawImage(source, 0, 0)

    for (const face of faces) {
      const normalizedFace = clampFaceBox(face.faceBox, source.width, source.height)
      const generatedCanvas = document.createElement('canvas')
      generatedCanvas.width = normalizedRegion.width
      generatedCanvas.height = normalizedRegion.height
      const generatedContext = generatedCanvas.getContext('2d', { willReadFrequently: true })
      if (!generatedContext) throw new Error(t('canvas.imageOps.emotionCompositeFailed'))
      generatedContext.imageSmoothingEnabled = true
      generatedContext.imageSmoothingQuality = 'high'
      // 先垫源图区域像素：对齐变换覆盖不到的地方合成结果等于源图，混合后无缝
      generatedContext.drawImage(source, normalizedRegion.x, normalizedRegion.y, normalizedRegion.width, normalizedRegion.height, 0, 0, normalizedRegion.width, normalizedRegion.height)
      if (face.sameCoords) {
        // 同坐标系整图 1:1 贴回（微调重建：从上一轮结果按椭圆取回已生成的表情），几何零偏移不做校正
        generatedContext.setTransform(1, 0, 0, 1, -normalizedRegion.x, -normalizedRegion.y)
        generatedContext.drawImage(generated, 0, 0)
        generatedContext.setTransform(1, 0, 0, 1, 0, 0)
        const sourcePixels = context.getImageData(normalizedRegion.x, normalizedRegion.y, normalizedRegion.width, normalizedRegion.height)
        const generatedPixels = generatedContext.getImageData(0, 0, normalizedRegion.width, normalizedRegion.height)
        const ellipse = emotionEditEllipse(normalizedFace, normalizedRegion)
        const gains = sampleEdgeColorGains(sourcePixels.data, generatedPixels.data, normalizedRegion.width, normalizedRegion.height, ellipse)
        blendEmotionPixels(sourcePixels.data, generatedPixels.data, normalizedRegion.width, normalizedRegion.height, ellipse, gains)
        context.putImageData(sourcePixels, normalizedRegion.x, normalizedRegion.y)
        continue
      }
      // 软校正：检测测量噪声（±3-5%）与模型真实漂移（0-20% 随机）同量级——
      // 偏差在噪声底内不修（噪声不再变成大小偏差），超过死区线性增强到全量（真实漂移修得掉）。
      // 缩放锚 = 覆盖缩放（区域/生成图尺寸，跨图量纲稳定），双眼关键点：中心=中点、缩放=眼距比、旋转=连线角差。
      const coverScale = Math.max(normalizedRegion.width / generated.width, normalizedRegion.height / generated.height)
      const noCorrGenAnchorX = generated.width / 2
      const noCorrGenAnchorY = generated.height / 2
      let scale = coverScale
      let rotation = 0
      let anchorX = normalizedFace.x + normalizedFace.width / 2 - normalizedRegion.x
      let anchorY = normalizedFace.y + normalizedFace.height / 2 - normalizedRegion.y
      let genAnchorX = noCorrGenAnchorX
      let genAnchorY = noCorrGenAnchorY
      const srcEyes = normalizedFace.keypoints && normalizedFace.keypoints.length >= 2 ? [normalizedFace.keypoints[0], normalizedFace.keypoints[1]] : null
      const genEyes = face.generatedFaceBox && face.generatedFaceBox.width >= 8 && face.generatedFaceBox.keypoints && face.generatedFaceBox.keypoints.length >= 2 ? [face.generatedFaceBox.keypoints[0], face.generatedFaceBox.keypoints[1]] : null
      let softGain = 0
      if (srcEyes && genEyes) {
        const srcDist = Math.hypot(srcEyes[1].x - srcEyes[0].x, srcEyes[1].y - srcEyes[0].y)
        const genDist = Math.hypot(genEyes[1].x - genEyes[0].x, genEyes[1].y - genEyes[0].y)
        if (srcDist >= 1 && genDist >= 1) {
          softGain = correctionGain((srcDist / genDist) / coverScale)
          scale = coverScale * (1 + (clamp((srcDist / genDist) / coverScale, 0.75, 1.35) - 1) * softGain)
          rotation = clamp(normalizeLineAngle(Math.atan2(srcEyes[1].y - srcEyes[0].y, srcEyes[1].x - srcEyes[0].x)) - normalizeLineAngle(Math.atan2(genEyes[1].y - genEyes[0].y, genEyes[1].x - genEyes[0].x)), -0.35, 0.35) * softGain
          anchorX = (srcEyes[0].x + srcEyes[1].x) / 2 - normalizedRegion.x
          anchorY = (srcEyes[0].y + srcEyes[1].y) / 2 - normalizedRegion.y
          genAnchorX = (genEyes[0].x + genEyes[1].x) / 2
          genAnchorY = (genEyes[0].y + genEyes[1].y) / 2
        }
      } else if (face.generatedFaceBox && face.generatedFaceBox.width >= 8 && face.generatedFaceBox.height >= 8) {
        const faceScale = ((normalizedFace.width / face.generatedFaceBox.width) + (normalizedFace.height / face.generatedFaceBox.height)) / 2
        softGain = correctionGain(faceScale / coverScale)
        scale = coverScale * (1 + (clamp(faceScale / coverScale, 0.75, 1.35) - 1) * softGain)
        anchorX = normalizedFace.x + normalizedFace.width / 2 - normalizedRegion.x
        anchorY = normalizedFace.y + normalizedFace.height / 2 - normalizedRegion.y
        genAnchorX = face.generatedFaceBox.x + face.generatedFaceBox.width / 2
        genAnchorY = face.generatedFaceBox.y + face.generatedFaceBox.height / 2
      }
      // 平移/缩放/旋转按同一软增益插值：无校正位=居中覆盖
      const noCorrAnchorX = normalizedRegion.width / 2
      const noCorrAnchorY = normalizedRegion.height / 2
      const cos = Math.cos(rotation)
      const sin = Math.sin(rotation)
      const targetE = anchorX - (cos * scale * genAnchorX - sin * scale * genAnchorY)
      const targetF = anchorY - (sin * scale * genAnchorX + cos * scale * genAnchorY)
      const baseE = noCorrAnchorX - coverScale * noCorrGenAnchorX
      const baseF = noCorrAnchorY - coverScale * noCorrGenAnchorY
      generatedContext.setTransform(
        coverScale + (cos * scale - coverScale) * softGain,
        (sin * scale) * softGain,
        (-sin * scale) * softGain,
        coverScale + (cos * scale - coverScale) * softGain,
        baseE + (targetE - baseE) * softGain,
        baseF + (targetF - baseF) * softGain,
      )
      generatedContext.drawImage(generated, 0, 0)
      generatedContext.setTransform(1, 0, 0, 1, 0, 0)

      const sourcePixels = context.getImageData(normalizedRegion.x, normalizedRegion.y, normalizedRegion.width, normalizedRegion.height)
      const generatedPixels = generatedContext.getImageData(0, 0, normalizedRegion.width, normalizedRegion.height)
      const ellipse = emotionEditEllipse(normalizedFace, normalizedRegion)
      const gains = sampleEdgeColorGains(sourcePixels.data, generatedPixels.data, normalizedRegion.width, normalizedRegion.height, ellipse)
      blendEmotionPixels(sourcePixels.data, generatedPixels.data, normalizedRegion.width, normalizedRegion.height, ellipse, gains)
      context.putImageData(sourcePixels, normalizedRegion.x, normalizedRegion.y)
    }
    return canvas.toDataURL('image/png')
  } finally {
    source.close()
    generated.close()
  }
}

/** 合成结果转上传文件（PNG 超 4.5MB 时回退 JPEG，接口上限 5MB） */
export async function emotionResultToFile(dataUrl: string, name: string): Promise<File> {
  let finalUrl = dataUrl
  if (dataUrl.length > 4_500_000) {
    const image = await loadImageBitmap(dataUrl)
    try {
      const canvas = document.createElement('canvas')
      canvas.width = image.width
      canvas.height = image.height
      canvas.getContext('2d')!.drawImage(image, 0, 0)
      finalUrl = canvas.toDataURL('image/jpeg', 0.92)
    } finally {
      image.close()
    }
  }
  const blob = await (await fetch(finalUrl)).blob()
  return new File([blob], name, { type: blob.type || 'image/png' })
}

function drawSourceCrop(image: ImageBitmap, region: EmotionEditRegion): string {
  const canvas = document.createElement('canvas')
  canvas.width = region.width
  canvas.height = region.height
  const context = canvas.getContext('2d')
  if (!context) throw new Error(t('canvas.imageOps.emotionCropFailed'))
  context.drawImage(image, region.x, region.y, region.width, region.height, 0, 0, region.width, region.height)
  return canvas.toDataURL('image/png')
}

/** 黑底白椭圆蒙版（Agnes 局部编辑语义：白色=可编辑区域），限定上游只许重绘人脸椭圆；
 *  椭圆边缘用径向渐变羽化，硬边蒙版容易让模型画出可见的边界感 */
function drawFaceMask(region: EmotionEditRegion, boxes: EmotionFaceBox[]): string {
  const canvas = document.createElement('canvas')
  canvas.width = region.width
  canvas.height = region.height
  const context = canvas.getContext('2d')
  if (!context) throw new Error(t('canvas.imageOps.emotionCropFailed'))
  context.fillStyle = '#000'
  context.fillRect(0, 0, region.width, region.height)
  for (const box of boxes) {
    const ellipse = emotionEditEllipse(box, region)
    context.save()
    context.translate(ellipse.centerX, ellipse.centerY)
    context.scale(ellipse.radiusX, ellipse.radiusY)
    const gradient = context.createRadialGradient(0, 0, 0, 0, 0, 1)
    gradient.addColorStop(0, '#fff')
    gradient.addColorStop(0.7, '#fff')
    gradient.addColorStop(1, '#000')
    context.fillStyle = gradient
    context.beginPath()
    context.arc(0, 0, 1, 0, Math.PI * 2)
    context.fill()
    context.restore()
  }
  return canvas.toDataURL('image/png')
}

/** 人物参考图：脸部裁切居中到 384×384 深色底（供模型核对身份） */
function drawFaceCrop(image: ImageBitmap, box: EmotionFaceBox, imageWidth: number, imageHeight: number): string {
  const paddingX = box.width * 0.45
  const paddingTop = box.height * 0.35
  const paddingBottom = box.height * 0.65
  const sx = Math.max(0, Math.floor(box.x - paddingX))
  const sy = Math.max(0, Math.floor(box.y - paddingTop))
  const sw = Math.max(1, Math.min(imageWidth - sx, Math.ceil(box.width + paddingX * 2)))
  const sh = Math.max(1, Math.min(imageHeight - sy, Math.ceil(box.height + paddingTop + paddingBottom)))
  const canvas = document.createElement('canvas')
  canvas.width = 384
  canvas.height = 384
  const context = canvas.getContext('2d')
  if (!context) throw new Error(t('canvas.imageOps.emotionCropFailed'))
  context.fillStyle = '#111'
  context.fillRect(0, 0, canvas.width, canvas.height)
  const scale = Math.min(canvas.width / sw, canvas.height / sh)
  const dw = sw * scale
  const dh = sh * scale
  context.drawImage(image, sx, sy, sw, sh, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh)
  return canvas.toDataURL('image/jpeg', 0.9)
}

function clampEditRegion(region: EmotionEditRegion, imageWidth: number, imageHeight: number): EmotionEditRegion {
  const x = Math.max(0, Math.min(imageWidth - 1, Math.round(region.x)))
  const y = Math.max(0, Math.min(imageHeight - 1, Math.round(region.y)))
  return {
    x,
    y,
    width: Math.max(1, Math.min(imageWidth - x, Math.round(region.width))),
    height: Math.max(1, Math.min(imageHeight - y, Math.round(region.height))),
  }
}

/* ---------- 羽化混合 ---------- */

type EmotionEllipse = { centerX: number; centerY: number; radiusX: number; radiusY: number }

/** 羽化透明度：椭圆内 0.65 全透明度 1，0.65~1 宽过渡带平滑衰减（窄带会在色调差下显出可见圆环） */
export function emotionFeatherAlpha(distance: number): number {
  if (distance <= 0.65) return 1
  if (distance >= 1) return 0
  const t = (distance - 0.65) / 0.35
  return 1 - t * t * (3 - 2 * t)
}

function ellipseDistance(x: number, y: number, ellipse: EmotionEllipse): number {
  const dx = (x + 0.5 - ellipse.centerX) / ellipse.radiusX
  const dy = (y + 0.5 - ellipse.centerY) / ellipse.radiusY
  return Math.sqrt(dx * dx + dy * dy)
}

/** 仅采样羽化边缘，按 RGB 分通道校正亮度/冷暖色偏，中心表情仍以模型结果为主 */
function sampleEdgeColorGains(source: Uint8ClampedArray, generated: Uint8ClampedArray, width: number, height: number, ellipse: EmotionEllipse): [number, number, number] {
  const sourceSum = [0, 0, 0]
  const generatedSum = [0, 0, 0]
  let count = 0
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const distance = ellipseDistance(x, y, ellipse)
      if (distance < 0.72 || distance > 0.96) continue
      const index = (y * width + x) * 4
      for (let channel = 0; channel < 3; channel += 1) {
        sourceSum[channel] += source[index + channel]
        generatedSum[channel] += generated[index + channel]
      }
      count += 1
    }
  }
  if (count < 32) return [1, 1, 1]
  return sourceSum.map((sum, channel) => clamp(sum / Math.max(1, generatedSum[channel]), 0.65, 1.45)) as [number, number, number]
}

function blendEmotionPixels(source: Uint8ClampedArray, generated: Uint8ClampedArray, width: number, height: number, ellipse: EmotionEllipse, gains: [number, number, number]) {
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = emotionFeatherAlpha(ellipseDistance(x, y, ellipse))
      if (alpha <= 0) continue
      const index = (y * width + x) * 4
      // 色彩增益近乎全量施加（含中心）：模型重绘区常带轻微曝光/色温偏移，正是椭圆边缘白圈感的来源
      const correctionStrength = 0.92 + (1 - alpha) * 0.08
      for (let channel = 0; channel < 3; channel += 1) {
        const gain = 1 + (gains[channel] - 1) * correctionStrength
        const corrected = clamp(generated[index + channel] * gain, 0, 255)
        source[index + channel] = Math.round(source[index + channel] * (1 - alpha) + corrected * alpha)
      }
      source[index + 3] = Math.round(source[index + 3] * (1 - alpha) + generated[index + 3] * alpha)
    }
  }
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

/** 线段角度归一到 (-π/2, π/2]：双眼连线无方向，避免关键点顺序差异导致旋转反向 */
function normalizeLineAngle(angle: number): number {
  if (angle > Math.PI / 2) return angle - Math.PI
  if (angle <= -Math.PI / 2) return angle + Math.PI
  return angle
}

/** 软校正增益：|偏差|≤6%（检测噪声底）不修，6%~18% 线性增强，≥18% 全量修正 */
function correctionGain(ratio: number): number {
  const magnitude = Math.abs(ratio - 1)
  if (magnitude <= 0.06) return 0
  if (magnitude >= 0.18) return 1
  return (magnitude - 0.06) / 0.12
}

/** 几何漂移评分（0=完全对齐）：缩放偏差与中心平移偏差取大者，供坏结果自动重roll判定 */
export function emotionDriftScore(face: { faceBox: EmotionFaceBox; generatedFaceBox?: EmotionFaceBox }, region: EmotionEditRegion, generatedWidth: number, generatedHeight: number): number {
  const gen = face.generatedFaceBox
  if (!gen || gen.width < 8 || gen.height < 8) return 0
  const coverScale = Math.max(region.width / Math.max(1, generatedWidth), region.height / Math.max(1, generatedHeight))
  const faceWidth = Math.max(1, face.faceBox.width)
  const srcEyes = face.faceBox.keypoints && face.faceBox.keypoints.length >= 2 ? [face.faceBox.keypoints[0], face.faceBox.keypoints[1]] : null
  const genEyes = gen.keypoints && gen.keypoints.length >= 2 ? [gen.keypoints[0], gen.keypoints[1]] : null
  let scaleDev = 0
  let transDev = 0
  if (srcEyes && genEyes) {
    const srcDist = Math.hypot(srcEyes[1].x - srcEyes[0].x, srcEyes[1].y - srcEyes[0].y)
    const genDist = Math.hypot(genEyes[1].x - genEyes[0].x, genEyes[1].y - genEyes[0].y)
    if (srcDist < 1 || genDist < 1) return 0
    scaleDev = Math.abs((srcDist / genDist) / coverScale - 1)
  } else {
    scaleDev = Math.abs(((face.faceBox.width / gen.width + face.faceBox.height / gen.height) / 2) / coverScale - 1)
  }
  // 中心平移：生成图按居中覆盖摆放后，脸部锚点与源图锚点的偏差（相对脸宽）
  const srcAnchorX = (srcEyes ? (srcEyes[0].x + srcEyes[1].x) / 2 : face.faceBox.x + face.faceBox.width / 2) - region.x
  const srcAnchorY = (srcEyes ? (srcEyes[0].y + srcEyes[1].y) / 2 : face.faceBox.y + face.faceBox.height / 2) - region.y
  const genAnchorX = (genEyes ? (genEyes[0].x + genEyes[1].x) / 2 : gen.x + gen.width / 2) - generatedWidth / 2
  const genAnchorY = (genEyes ? (genEyes[0].y + genEyes[1].y) / 2 : gen.y + gen.height / 2) - generatedHeight / 2
  const placedX = region.width / 2 + genAnchorX * coverScale
  const placedY = region.height / 2 + genAnchorY * coverScale
  transDev = Math.hypot(srcAnchorX - placedX, srcAnchorY - placedY) / faceWidth
  return Math.max(scaleDev, transDev)
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

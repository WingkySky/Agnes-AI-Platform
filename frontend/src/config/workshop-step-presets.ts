/* =====================================================
 * 创意工坊预设步骤库
 *
 * 模板编辑器左栏列出这些预设，用户点击 + 即可加到流程。
 * 每个预设自带合理默认 config 和默认提示词模板，
 * 高级参数折叠在"展开高级"区里。
 *
 * 9 个预设的 type 必须命中后端权威 step_type 清单
 * (llm_generate / image_batch / video_batch / tts_generate /
 *  ffmpeg_composite / color_grade / video_edit)
 * 后端注册表见 backend/app/services/pipeline/steps/__init__.py
 * ===================================================== */

/** 后端权威 step_type（与后端注册表对齐，编译期保证拼写正确） */
export type WorkshopStepType =
  | 'llm_generate'
  | 'image_batch'
  | 'video_batch'
  | 'tts_generate'
  | 'ffmpeg_composite'
  | 'color_grade'
  | 'video_edit'

/** 高级折叠区字段规格（驱动 StepCard 动态渲染表单） */
export interface AdvancedFieldSpec {
  /** config 字段名，如 'model' / 'temperature' */
  key: string
  /** 显示名 */
  label: string
  /** 控件类型 */
  type: 'text' | 'number' | 'select' | 'boolean'
  /** select 控件的可选项 */
  options?: { label: string; value: string | number | boolean }[]
  /** 默认值 */
  default: string | number | boolean
  /** number 控件的最小值 */
  min?: number
  /** number 控件的最大值 */
  max?: number
  /** number 控件的步长 */
  step?: number
}

/** 预设步骤定义 */
export interface WorkshopStepPreset {
  /** 预设唯一标识 */
  presetKey: string
  /** 显示名（i18n 覆盖，此处为中文兜底） */
  name: string
  /** 后端 step_type，必须命中 WorkshopStepType */
  type: WorkshopStepType
  /** Element Plus Icon 组件名 */
  icon: string
  /** 主题色 hex（节点头/标签颜色） */
  color: string
  /** 步骤默认名（追加到流程时填入 step.name） */
  defaultName: string
  /** 该步骤类型的合理默认 config（用户可改） */
  defaultConfig: Record<string, any>
  /** 默认提示词模板（含 {{}} 占位符；非 llm_generate 类型可为空） */
  defaultPromptTemplate: string
  /** 高级折叠区字段规格 */
  advancedFields: AdvancedFieldSpec[]
}

/**
 * 7 个预设步骤定义
 *
 * 设计原则：
 * - 每个 type 至少有一个预设；常用的 type（llm_generate）有多个预设
 * - defaultConfig 必须包含执行器真实读取的字段，避免保存后运行报错
 * - from_step / audio_from_step / subtitle_from_step 默认 null，
 *   由前端按流程顺序自动填充（见 SaveAsWorkshopTemplateDialog / TemplateWizardView）
 */
export const WORKSHOP_STEP_PRESETS: WorkshopStepPreset[] = [
  {
    presetKey: 'script_generate',
    name: '剧本生成',
    type: 'llm_generate',
    icon: 'Document',
    color: '#378ADD',
    defaultName: '剧本生成',
    defaultConfig: {
      model: 'agnes-2.0-flash',
      temperature: 0.8,
      max_tokens: 2048,
      output_format: 'json',
    },
    defaultPromptTemplate:
      '根据主题 {{theme}} 生成 8 个分镜剧本，输出 JSON 数组，每个元素含 prompt 字段',
    advancedFields: [
      {
        key: 'model',
        label: '模型',
        type: 'text',
        default: 'agnes-2.0-flash',
      },
      {
        key: 'temperature',
        label: '温度',
        type: 'number',
        default: 0.8,
        min: 0,
        max: 2,
        step: 0.1,
      },
      {
        key: 'max_tokens',
        label: '最大 token',
        type: 'number',
        default: 2048,
        min: 256,
        max: 8192,
        step: 256,
      },
      {
        key: 'output_format',
        label: '输出格式',
        type: 'select',
        default: 'json',
        options: [
          { label: 'JSON', value: 'json' },
          { label: '文本', value: 'text' },
          { label: 'Markdown', value: 'markdown' },
        ],
      },
    ],
  },
  {
    presetKey: 'character_design',
    name: '角色设计',
    type: 'llm_generate',
    icon: 'UserFilled',
    color: '#7F77DD',
    defaultName: '角色设计',
    defaultConfig: {
      model: 'agnes-2.0-flash',
      temperature: 0.7,
      max_tokens: 2048,
      output_format: 'json',
    },
    defaultPromptTemplate:
      '根据主题 {{theme}} 设计主要角色的外貌、性格、服装，输出 JSON 数组',
    advancedFields: [
      { key: 'model', label: '模型', type: 'text', default: 'agnes-2.0-flash' },
      {
        key: 'temperature',
        label: '温度',
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
      },
      {
        key: 'output_format',
        label: '输出格式',
        type: 'select',
        default: 'json',
        options: [
          { label: 'JSON', value: 'json' },
          { label: '文本', value: 'text' },
        ],
      },
    ],
  },
  {
    presetKey: 'storyboard_draw',
    name: '分镜绘制',
    type: 'image_batch',
    icon: 'Picture',
    color: '#1D9E75',
    defaultName: '分镜绘制',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 llm_generate step.key
      prompt_field: 'prompt',
      model: 'agnes-image-1.0',
      size: '1024x1024',
      batch_size: 8,
    },
    defaultPromptTemplate: '',
    advancedFields: [
      { key: 'model', label: '模型', type: 'text', default: 'agnes-image-1.0' },
      {
        key: 'size',
        label: '图片尺寸',
        type: 'select',
        default: '1024x1024',
        options: [
          { label: '1024×1024', value: '1024x1024' },
          { label: '768×768', value: '768x768' },
          { label: '512×512', value: '512x512' },
        ],
      },
      {
        key: 'batch_size',
        label: '批量数',
        type: 'number',
        default: 8,
        min: 1,
        max: 32,
        step: 1,
      },
    ],
  },
  {
    presetKey: 'video_generate',
    name: '视频生成',
    type: 'video_batch',
    icon: 'VideoPlay',
    color: '#D85A30',
    defaultName: '视频生成',
    defaultConfig: {
      from_step: null,
      model: 'agnes-video-1.0',
      seconds: 5,
      aspect_ratio: '16:9',
    },
    defaultPromptTemplate: '',
    advancedFields: [
      { key: 'model', label: '模型', type: 'text', default: 'agnes-video-1.0' },
      {
        key: 'seconds',
        label: '时长(秒)',
        type: 'number',
        default: 5,
        min: 1,
        max: 30,
        step: 1,
      },
      {
        key: 'aspect_ratio',
        label: '宽高比',
        type: 'select',
        default: '16:9',
        options: [
          { label: '16:9', value: '16:9' },
          { label: '9:16', value: '9:16' },
          { label: '1:1', value: '1:1' },
        ],
      },
    ],
  },
  {
    presetKey: 'voiceover',
    name: '配音',
    type: 'tts_generate',
    icon: 'Microphone',
    color: '#EF9F27',
    defaultName: '配音',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 llm_generate step.key
      voice: 'default',
      speed: 1.0,
      provider: 'agnes-tts',
    },
    defaultPromptTemplate: '',
    advancedFields: [
      {
        key: 'voice',
        label: '音色',
        type: 'select',
        default: 'default',
        options: [
          { label: '默认', value: 'default' },
          { label: '女声', value: 'female' },
          { label: '男声', value: 'male' },
        ],
      },
      {
        key: 'speed',
        label: '语速',
        type: 'number',
        default: 1.0,
        min: 0.5,
        max: 2.0,
        step: 0.1,
      },
      { key: 'provider', label: 'TTS 服务', type: 'text', default: 'agnes-tts' },
    ],
  },
  {
    presetKey: 'subtitle',
    name: '字幕',
    type: 'llm_generate',
    icon: 'ChatLineSquare',
    color: '#D4537E',
    defaultName: '字幕',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 llm_generate step.key
      model: 'agnes-2.0-flash',
      temperature: 0.5,
      max_tokens: 2048,
      output_format: 'text',
    },
    defaultPromptTemplate:
      '根据上游剧本内容生成 SRT 格式字幕，每条字幕不超过 20 字',
    advancedFields: [
      { key: 'model', label: '模型', type: 'text', default: 'agnes-2.0-flash' },
      {
        key: 'temperature',
        label: '温度',
        type: 'number',
        default: 0.5,
        min: 0,
        max: 2,
        step: 0.1,
      },
    ],
  },
  {
    presetKey: 'compose',
    name: '成片合成',
    type: 'ffmpeg_composite',
    icon: 'Connection',
    color: '#5F5E5A',
    defaultName: '成片合成',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 video_batch step.key
      with_subtitle: true,
      audio_from_step: null, // 可选：最近的 tts_generate step.key
      subtitle_from_step: null, // 可选：最近的 subtitle(llm_generate) step.key
    },
    defaultPromptTemplate: '',
    advancedFields: [
      {
        key: 'with_subtitle',
        label: '烧录字幕',
        type: 'boolean',
        default: true,
      },
    ],
  },
  {
    presetKey: 'color_grade',
    name: '调色',
    type: 'color_grade',
    icon: 'MagicStick',
    color: '#A855F7',
    defaultName: '调色',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 video_batch / ffmpeg_composite step.key
      preset: 'neutral_punch',
      with_audio_fade: true,
    },
    defaultPromptTemplate: '',
    advancedFields: [
      {
        key: 'preset',
        label: '调色预设',
        type: 'select',
        default: 'neutral_punch',
        options: [
          { label: '不调色', value: 'none' },
          { label: '轻微清理', value: 'subtle' },
          { label: '中性增艳（推荐）', value: 'neutral_punch' },
          { label: '暖色电影感', value: 'warm_cinematic' },
          { label: '自动', value: 'auto' },
        ],
      },
      {
        key: 'with_audio_fade',
        label: '音频淡入淡出',
        type: 'boolean',
        default: true,
      },
    ],
  },
  {
    presetKey: 'video_edit',
    name: '视频剪辑',
    type: 'video_edit',
    icon: 'Scissor',
    color: '#EC4899',
    defaultName: '视频剪辑',
    defaultConfig: {
      from_step: null, // 前端按流程顺序自动填充为最近的 video_batch / ffmpeg_composite / color_grade step.key
      operations: [], // 剪辑操作列表，由专门编辑器填写：[{type: 'trim'|'cut', start, end}, ...]
    },
    defaultPromptTemplate: '',
    advancedFields: [], // operations 由专门的剪辑操作编辑器渲染，不走通用 advancedFields 表单
  },
]

/**
 * 按 presetKey 查找预设
 */
export function getStepPreset(presetKey: string): WorkshopStepPreset | undefined {
  return WORKSHOP_STEP_PRESETS.find((p) => p.presetKey === presetKey)
}

/**
 * 按 type 查找该类型的第一个预设（用于画布新节点默认配置）
 */
export function getPresetByType(
  type: WorkshopStepType,
): WorkshopStepPreset | undefined {
  return WORKSHOP_STEP_PRESETS.find((p) => p.type === type)
}

/**
 * 创建一个新步骤（基于预设，含默认 config 和默认 prompt）
 *
 * @param presetKey 预设 key
 * @param index 当前流程中已有步骤数（用于生成 step.key）
 */
export function createStepFromPreset(
  presetKey: string,
  index: number,
): {
  key: string
  name: string
  type: WorkshopStepType
  depends_on: string[]
  config: Record<string, any>
} {
  const preset = getStepPreset(presetKey)
  if (!preset) {
    throw new Error(`未找到预设: ${presetKey}`)
  }
  return {
    key: `step_${index}`,
    name: preset.defaultName,
    type: preset.type,
    depends_on: index > 0 ? [`step_${index - 1}`] : [],
    config: {
      ...preset.defaultConfig,
      // llm_generate 类型带 prompt 字段
      ...(preset.type === 'llm_generate' && preset.defaultPromptTemplate
        ? { prompt: preset.defaultPromptTemplate }
        : {}),
    },
  }
}

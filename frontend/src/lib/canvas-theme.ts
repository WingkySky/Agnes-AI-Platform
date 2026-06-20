/* 画布主题 token 表：背景、节点、连线、锚点、选择框 */
/* 包含 dark / light 两套，供 store 透出 canvasTheme getter，
   同时供 CanvasView 内的 CSS 变量做具体值映射 */
/* 融合项目深蓝紫主题：对齐 Agnes AI Platform 全局配色，
   canvas/node/toolbar 三组 token 与 App.vue 的 --agnes-* 变量协调 */

/** 画布区域主题 token */
interface CanvasThemeTokens {
  background: string
  dot: string
  line: string
  selectionStroke: string
  selectionFill: string
}

/** 节点主题 token */
interface NodeThemeTokens {
  label: string
  fill: string
  panel: string
  stroke: string
  activeStroke: string
  placeholder: string
  text: string
  muted: string
  faint: string
}

/** 工具栏主题 token */
interface ToolbarThemeTokens {
  panel: string
  border: string
  item: string
  itemHover: string
  activeBg: string
  activeText: string
}

/** 单套主题 */
interface CanvasTheme {
  canvas: CanvasThemeTokens
  node: NodeThemeTokens
  toolbar: ToolbarThemeTokens
}

/** 全部主题集合 */
interface CanvasThemes {
  light: CanvasTheme
  dark: CanvasTheme
}

export const canvasThemes: CanvasThemes = {
  // 浅色主题：与项目浅色风格协调
  light: {
    canvas: {
      background: '#f0f2f8',
      dot: 'rgba(60,80,120,.22)',
      line: 'rgba(60,80,120,.10)',
      selectionStroke: '#6b9cff',
      selectionFill: 'rgba(107,156,255,.08)',
    },
    node: {
      label: '#5a6a8a',
      fill: '#ffffff',
      panel: '#f7f9fc',
      stroke: '#d0d8e8',
      activeStroke: '#6b9cff',
      placeholder: '#9aa8c0',
      text: '#1a2333',
      muted: '#6a7a96',
      faint: '#a0b0c8',
    },
    toolbar: {
      panel: 'rgba(255,255,255,.92)',
      border: '#d0d8e8',
      item: '#5a6a8a',
      itemHover: '#e8edf5',
      activeBg: '#e8edf5',
      activeText: '#1a2333',
    },
  },

  // 深色主题：与项目深蓝紫渐变背景协调
  dark: {
    canvas: {
      background: '#0b0f1a',
      dot: 'rgba(160,180,220,.18)',
      line: 'rgba(160,180,220,.08)',
      selectionStroke: '#6b9cff',
      selectionFill: 'rgba(107,156,255,.10)',
    },
    node: {
      label: '#a0b4d6',
      fill: 'rgba(22,32,54,.85)',
      panel: 'rgba(15,22,38,.95)',
      stroke: 'rgba(120,170,230,.20)',
      activeStroke: '#6b9cff',
      placeholder: '#6b84aa',
      text: '#e8eef7',
      muted: '#8ba3c9',
      faint: '#5a6a8a',
    },
    toolbar: {
      panel: 'rgba(15,22,38,.80)',
      border: 'rgba(120,170,230,.18)',
      item: '#a0b4d6',
      itemHover: 'rgba(120,170,255,.10)',
      activeBg: 'rgba(107,156,255,.15)',
      activeText: '#ffffff',
    },
  },
}

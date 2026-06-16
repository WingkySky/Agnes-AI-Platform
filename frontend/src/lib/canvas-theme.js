/* 画布主题 token 表：背景、节点、连线、锚点、选择框 */
/* 包含 dark / light 两套，供 store 透出 canvasTheme getter，
   同时供 CanvasView 内的 CSS 变量做具体值映射 */

export const canvasThemes = {
  // 深色主题：沿用项目原有的蓝紫渐变
  dark: {
    bg: {
      canvas: 'linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%)',
      panel: 'rgba(22, 32, 54, 0.7)',
      gridDot: 'rgba(245, 245, 244, 0.24)',
      gridLine: 'rgba(245, 245, 244, 0.10)',
    },
    node: {
      border: 'rgba(120, 170, 230, 0.2)',
      activeBorder: '#85b2ff',
      glow: 'rgba(100, 150, 255, 0.35)',
      titleText: '#ffffff',
      mutedText: '#8ba3c9',
    },
    connection: {
      active: 'rgba(80, 140, 255, 0.6)',
      muted: 'rgba(150, 150, 180, 0.3)',
      hit: 'transparent',
    },
    anchor: {
      fill: '#6b9cff',
      input: '#6b9cff',
      output: '#a78bff',
    },
    selectionBox: {
      fill: 'rgba(100, 150, 255, 0.15)',
      stroke: '#6b9cff',
    },
    // Minimap 上面板色块：按面板类型区分的视觉标识，半透明叠加
    minimap: {
      panelColors: {
        image: 'rgba(80, 140, 255, 0.5)',
        video: 'rgba(160, 120, 255, 0.5)',
        text: 'rgba(80, 200, 160, 0.5)',
        url: 'rgba(255, 180, 80, 0.5)',
        'quick-generate': 'rgba(255, 120, 120, 0.5)',
        'file-upload': 'rgba(120, 200, 255, 0.5)',
        placeholder: 'rgba(150, 150, 180, 0.3)',
        default: 'rgba(150, 150, 180, 0.4)',
      },
    },
  },

  // 浅色主题：白底深蓝对比
  light: {
    bg: {
      canvas: '#f5f7fa',
      panel: 'rgba(255, 255, 255, 0.95)',
      gridDot: 'rgba(68, 64, 60, 0.28)',
      gridLine: 'rgba(68, 64, 60, 0.12)',
    },
    node: {
      border: 'rgba(0, 0, 0, 0.1)',
      activeBorder: '#1d4ed8',
      glow: 'rgba(37, 99, 235, 0.25)',
      titleText: '#1f2937',
      mutedText: '#6b7280',
    },
    connection: {
      active: '#2563eb',
      muted: 'rgba(120, 113, 108, 0.5)',
      hit: 'transparent',
    },
    anchor: {
      fill: '#1d4ed8',
      input: '#1d4ed8',
      output: '#7c3aed',
    },
    selectionBox: {
      fill: 'rgba(37, 99, 235, 0.1)',
      stroke: '#2563eb',
    },
    // Minimap 上面板色块：浅色主题下用更深的颜色，确保在白底上仍然可见
    minimap: {
      panelColors: {
        image: 'rgba(37, 99, 235, 0.55)',
        video: 'rgba(124, 58, 237, 0.55)',
        text: 'rgba(22, 163, 74, 0.55)',
        url: 'rgba(217, 119, 6, 0.6)',
        'quick-generate': 'rgba(220, 38, 38, 0.55)',
        'file-upload': 'rgba(14, 116, 144, 0.55)',
        placeholder: 'rgba(120, 113, 108, 0.4)',
        default: 'rgba(120, 113, 108, 0.45)',
      },
    },
  },
}

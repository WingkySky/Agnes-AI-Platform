/* 画布主题 token 表：背景、节点、连线、锚点、选择框 */
/* 包含 dark / light 两套，供 store 透出 canvasTheme getter，
   同时供 CanvasView 内的 CSS 变量做具体值映射 */
/* stone 暖灰色系主题：1:1 对齐参考项目 infinite-canvas 的 token 设计，
   包含 canvas（画布背景/网格点线/选择框）、node（节点）、toolbar（工具栏）三组 token */

export const canvasThemes = {
  // 浅色主题：stone 暖灰浅底
  light: {
    canvas: {
      background: '#f4f2ed',
      dot: 'rgba(68,64,60,.28)',
      line: 'rgba(68,64,60,.12)',
      selectionStroke: '#1c1917',
      selectionFill: 'rgba(28,25,23,.06)',
    },
    node: {
      label: '#57534e',
      fill: '#e7e5df',
      panel: '#fbfaf7',
      stroke: '#d6d3ca',
      activeStroke: '#1c1917',
      placeholder: '#8a8479',
      text: '#292524',
      muted: '#78716c',
      faint: '#a8a29e',
    },
    toolbar: {
      panel: 'rgba(251,250,247,.96)',
      border: '#d6d3ca',
      item: '#57534e',
      itemHover: '#e7e5df',
      activeBg: '#e7e5df',
      activeText: '#292524',
    },
  },

  // 深色主题：stone 暖灰深底
  dark: {
    canvas: {
      background: '#181715',
      dot: 'rgba(245,245,244,.24)',
      line: 'rgba(245,245,244,.10)',
      selectionStroke: '#fafaf9',
      selectionFill: 'rgba(250,250,249,.10)',
    },
    node: {
      label: '#d6d3d1',
      fill: '#292524',
      panel: '#1f1d1a',
      stroke: '#44403c',
      activeStroke: '#fafaf9',
      placeholder: '#a8a29e',
      text: '#f5f5f4',
      muted: '#d6d3d1',
      faint: '#78716c',
    },
    toolbar: {
      panel: 'rgba(31,29,26,.96)',
      border: '#44403c',
      item: '#d6d3d1',
      itemHover: '#292524',
      activeBg: '#3a3631',
      activeText: '#f5f5f4',
    },
  },
}

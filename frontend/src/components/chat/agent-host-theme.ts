/* =====================================================
 * AgentHostPanel 默认主题 token（defineProps 默认值须模块级）
 * 与画布面板 HostTheme 同形；缺省映射 agnes 全局变量，自动跟随深浅色。
 * ===================================================== */

export interface HostTheme {
  node: { text: string; muted: string; panel: string }
  toolbar: { panel: string; border: string; item: string; itemHover: string; activeBg: string; activeText: string }
}

export const DEFAULT_HOST_THEME: HostTheme = {
  node: {
    text: 'var(--agnes-text-primary)',
    muted: 'var(--agnes-text-muted)',
    panel: 'var(--agnes-bg-card)',
  },
  toolbar: {
    panel: 'var(--agnes-bg-elevated)',
    border: 'var(--agnes-border)',
    item: 'var(--agnes-text-secondary)',
    itemHover: 'var(--agnes-bg-hover)',
    activeBg: 'var(--agnes-primary)',
    activeText: '#ffffff',
  },
}

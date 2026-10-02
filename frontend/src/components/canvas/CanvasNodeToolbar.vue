<!-- =====================================================
     CanvasNodeToolbar 节点工具栏（选中节点后常驻显示于节点上方）
     - 内容由 lib/canvas-node-tools 注册表驱动：一级平铺 + 分类下拉
     - 一级钮=图标+文字；分类钮（生成/编辑/管理）点开 el-dropdown 条目列表
     - 点击任意工具统一 emit('action', toolId, payload)，由 CanvasView 分发
     - 下拉 popper teleported=false：留在工具栏子树内继承主题 CSS 变量，
       且点击事件被容器 pointerdown.stop 覆盖，不会清掉节点选中
     ===================================================== -->

<template>
  <div
    class="canvas-node-toolbar"
    :style="toolbarStyle"
    @mousedown.stop
    @pointerdown.stop
  >
    <button
      v-for="tool in model.primary"
      :key="tool.id"
      type="button"
      class="tool-btn"
      :class="{ 'is-danger': tool.danger }"
      :style="btnStyle(tool)"
      @click="run(tool)"
    >
      <component :is="toolIcon(tool, ctx)" :size="15" />
      <span>{{ label(tool) }}</span>
    </button>

    <template v-for="g in model.groups" :key="g.key">
      <div class="tool-divider" :style="{ background: props.theme.toolbar.border }" />
      <el-dropdown
        trigger="click"
        placement="bottom-end"
        :teleported="false"
        popper-class="canvas-node-tool-popper"
        @visible-change="(v: boolean) => (openGroup = v ? g.key : null)"
      >
        <button type="button" class="tool-btn" :class="{ 'is-open': openGroup === g.key }" :style="btnStyle()">
          <span>{{ t(`canvas.hoverToolbar.${g.labelKey}`) }}</span>
          <ChevronDown :size="13" class="chev" />
        </button>
        <template #dropdown>
          <el-dropdown-menu class="tool-menu">
            <el-dropdown-item
              v-for="tool in g.tools"
              :key="tool.id"
              :class="['menu-item', { 'is-danger': tool.danger }]"
              @click="run(tool)"
            >
              <component :is="toolIcon(tool, ctx)" :size="15" />
              <span>{{ label(tool) }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>
  </div>
</template>

<script setup lang="ts">
/* =====================================================
 * CanvasNodeToolbar 节点工具栏
 *
 * 数据约定：panel.content 作为节点元数据（content/status/prompt/freeResize），
 * 工具集合与分组归属全部来自 lib/canvas-node-tools 注册表。
 * ===================================================== */

import { computed, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import {
  getShotLineageInfo, findTailFramePanel, findPrevFramePanel, readChainSegments,
} from '@/lib/canvas-storyboard'
import {
  resolveToolbarTools, toolIcon, toolLabelKey,
  type ToolContext, type ToolDef,
} from '@/lib/canvas-node-tools'

const { t } = useI18n()

/* ---------- Props / Emits ---------- */
const props = defineProps({
  panel: { type: Object, required: true },
  theme: { type: Object, required: true },
})

const emit = defineEmits(['action'])

/* ---------- 工具上下文（按 panel 现状组装，供注册表条件判断） ---------- */
const ctx = computed<ToolContext>(() => {
  const panel = props.panel
  const c = (panel.content || {}) as Record<string, unknown>
  const lineageInfo = getShotLineageInfo(panel)
  const lineage = lineageInfo?.lineage
  let hasTailFrame = false
  let hasPrevFrame = false
  let chainSegments = 0
  if (lineage) {
    const scriptPanel = useCanvasStore().panels.find((p) => p.id === lineage.scriptPanelId)
    if (scriptPanel) {
      chainSegments = readChainSegments(scriptPanel)
      hasTailFrame = Boolean(findTailFramePanel(lineage.scriptPanelId, lineage.shotId))
      hasPrevFrame = Boolean(findPrevFramePanel(lineage.scriptPanelId, lineage.shotId))
    }
  }
  return {
    type: panel.type || '',
    hasContent: Boolean(c.content),
    isError: c.status === 'error',
    isLoading: c.status === 'loading',
    hasPrompt: typeof c.prompt === 'string' && c.prompt.trim().length > 0,
    freeResize: Boolean(c.freeResize),
    isLineage: Boolean(lineage),
    lineageIsImage: lineage?.kind === 'image',
    lineageIsFirst: lineage ? lineage.role === undefined || lineage.role === 'first' : false,
    hasTailFrame,
    hasPrevFrame,
    chainSegments,
  }
})

/** 工具栏模型：一级平铺 + 分类分组（注册表解析结果） */
const model = computed(() => resolveToolbarTools(ctx.value))

/* ---------- 交互 ---------- */
const openGroup = ref<string | null>(null)

/** 点击工具：统一上报 action，payload 由注册表条目自带 */
function run(tool: ToolDef) {
  openGroup.value = null
  emit('action', tool.id, tool.payload?.(ctx.value))
}

/* ---------- 样式 ---------- */
const toolbarStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  border: `1px solid ${props.theme.toolbar.border}`,
  '--hover-bg': props.theme.toolbar.itemHover,
  '--tool-popper-bg': props.theme.toolbar.panel,
  '--tool-popper-border': props.theme.toolbar.border,
  '--tool-hover': props.theme.toolbar.itemHover,
  '--tool-item': props.theme.toolbar.item,
}))

function btnStyle(tool?: ToolDef) {
  return { color: tool?.danger ? 'var(--agnes-error)' : props.theme.toolbar.item }
}

function label(tool: ToolDef) {
  return t(`canvas.hoverToolbar.${toolLabelKey(tool, ctx.value)}`)
}
</script>

<style scoped>
/* ===== 工具栏容器：h-12（48px）+ rounded-[18px] + 边框 + 阴影 ===== */
.canvas-node-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 48px;
  padding: 0 8px;
  border-radius: 18px;
  border: 1px solid;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  overflow: visible;
}

/* ===== 一级按钮：图标 + 文字 ===== */
.tool-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 150ms ease;
  flex-shrink: 0;
}

.tool-btn:hover,
.tool-btn.is-open {
  background-color: var(--hover-bg, var(--agnes-bg-hover));
}

.tool-btn .chev {
  transition: transform 150ms ease;
  opacity: 0.7;
}

.tool-btn.is-open .chev {
  transform: rotate(180deg);
}

/* ===== 一级与分类钮之间的分隔线 ===== */
.tool-divider {
  width: 1px;
  height: 18px;
  margin: 0 4px;
  opacity: 0.5;
  flex-shrink: 0;
}

/* ===== 下拉条目 ===== */
.tool-menu {
  background: transparent;
  padding: 4px;
  min-width: 136px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
  border-radius: 8px;
  list-style: none;
  color: var(--tool-item, inherit);
  transition: background-color 150ms ease;
}

.menu-item:hover {
  background-color: var(--tool-hover, var(--agnes-bg-hover));
  color: var(--tool-item, inherit);
}

.menu-item.is-danger {
  color: var(--agnes-error);
}
</style>

<style>
/* 非 scoped：下拉 popper 根节点不带本组件 scope id（teleported=false 挂在工具栏子树内，CSS 变量可继承） */
.canvas-node-tool-popper.el-popper {
  background: var(--tool-popper-bg, #1f1f23);
  border: 1px solid var(--tool-popper-border, rgba(255, 255, 255, 0.12));
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  padding: 0;
}

.canvas-node-tool-popper .el-popper__arrow {
  display: none;
}
</style>

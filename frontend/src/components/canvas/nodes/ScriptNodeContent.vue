<!-- =====================================================
  ScriptNodeContent 脚本节点内容（无限画布，LibTV 复刻）
  - 紧凑卡片：三步进度概览（确认镜头/准备资产/批量生成）+ 向导入口
  - 所有文字内容（剧情/镜头/资产）均在全屏分镜向导内编辑，不在节点内挤小空间
  - 数据全部存画布节点 content（localforage），后端无状态
  - 样式沿用 config 节点约定：原生控件 + @mousedown.stop + 主题 token
===================================================== -->

<template>
  <div v-if="panel" class="script-node">
    <!-- 三步进度概览（对应向导后三步） -->
    <div class="script-steps">
      <template v-for="(s, i) in stepDots" :key="s.no">
        <div class="script-step" @click="wizardVisible = true">
          <span class="dot" :class="{ done: s.done, active: !s.done && i === 0 }" :style="dotStyle(s, i)">
            {{ s.done ? '✓' : s.no }}
          </span>
          <span class="step-title" :style="titleStyle(s, i)">{{ s.title }}</span>
          <span class="step-hint" :style="mutedStyle">{{ s.hint }}</span>
        </div>
        <div v-if="i < stepDots.length - 1" class="step-line" :style="lineStyle"></div>
      </template>
    </div>

    <!-- 向导入口 -->
    <button
      type="button"
      class="script-btn primary" :style="primaryBtnStyle"
      @mousedown.stop @click="wizardVisible = true"
    >
      {{ t('canvas.script.wizard.openNode') }} →
    </button>

    <!-- 全屏分镜向导：剧情 -> 确认镜头 -> 准备资产 -> 批量生成 -->
    <ScriptWizardDialog
      :panel-id="panel.id"
      :visible="wizardVisible"
      @close="wizardVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { getDerivedShotIds, readAssets, readShots } from '@/lib/canvas-storyboard'
import ScriptWizardDialog from '@/components/canvas/nodes/ScriptWizardDialog.vue'

// 通过 panelId 从 store 取节点（CanvasNode 的 panel prop 是松类型，不直接透传）
const props = defineProps<{ panelId: string }>()

const { t } = useI18n()
const store = useCanvasStore()

/** 当前脚本节点（节点被删除时为 null，模板 v-if 兜底） */
const panel = computed(() => store.panels.find((p) => p.id === props.panelId) || null)

const wizardVisible = ref(false)

// 外部唤起（对话框生成完分镜后）：openScriptWizardId 等于本节点时自动打开向导并消费
watch(() => store.openScriptWizardId, (id) => {
  if (id && id === props.panelId) {
    wizardVisible.value = true
    store.openScriptWizardId = null
  }
})

/* ---------- 进度数据（直接读 content，向导编辑后自动同步） ---------- */
const shotsCount = computed(() => (panel.value ? readShots(panel.value).length : 0))
const assetsCount = computed(() => {
  if (!panel.value) return 0
  const a = readAssets(panel.value)
  return a.characters.length + a.scenes.length
})
const genStatus = computed(() =>
  panel.value
    ? getDerivedShotIds(panel.value.id)
    : { image: new Set<string>(), video: new Set<string>() },
)

/* ---------- 三步指示（标题/提示随数据动态） ---------- */
const stepDots = computed(() => [
  {
    no: 1,
    title: t('canvas.script.wizard.stepShot'),
    hint: t('canvas.script.wizard.hintShots', { n: shotsCount.value }),
    done: shotsCount.value > 0,
  },
  {
    no: 2,
    title: t('canvas.script.wizard.stepAsset'),
    hint: t('canvas.script.wizard.hintAssets', { n: assetsCount.value }),
    done: assetsCount.value > 0,
  },
  {
    no: 3,
    title: t('canvas.script.wizard.stepGen'),
    hint: t('canvas.script.wizard.hintGen', { done: genStatus.value.image.size, total: shotsCount.value }),
    done: shotsCount.value > 0 && genStatus.value.image.size >= shotsCount.value,
  },
])

/* ---------- 主题样式 ---------- */
const theme = computed(() => store.canvasTheme)
const mutedStyle = computed(() => ({ color: theme.value.node.muted }))
const lineStyle = computed(() => ({ background: theme.value.node.faint }))
const primaryBtnStyle = computed(() => ({
  background: theme.value.node.activeStroke,
  borderColor: theme.value.node.activeStroke,
  color: '#fff',
}))

function dotStyle(s: { done: boolean }, idx: number) {
  if (s.done) {
    return { background: theme.value.node.activeStroke, color: '#fff', borderColor: theme.value.node.activeStroke }
  }
  if (idx === 0) {
    return { background: theme.value.node.activeStroke, color: '#fff', borderColor: theme.value.node.activeStroke }
  }
  return { background: 'transparent', color: theme.value.node.muted, borderColor: theme.value.node.faint }
}

function titleStyle(s: { done: boolean }, idx: number) {
  const highlight = s.done || idx === 0
  return { color: highlight ? theme.value.node.text : theme.value.node.muted }
}
</script>

<style scoped>
/* 紧凑卡片：上进度概览 + 下入口按钮 */
.script-node {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 20px;
  padding: 16px;
  box-sizing: border-box;
  overflow: hidden;
}
.script-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.script-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
  min-width: 52px;
}
.dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: none;
}
.step-title {
  font-size: 11px;
  white-space: nowrap;
}
.step-hint {
  font-size: 10px;
  white-space: nowrap;
}
.step-line {
  width: 28px;
  height: 1px;
  margin-bottom: 26px;
  opacity: 0.6;
  flex: none;
}

/* 入口按钮 */
.script-btn {
  border: 1px solid;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  width: 100%;
}
.script-btn.primary {
  font-weight: 600;
}
</style>

<!--
  CanvasAgentPanel.vue
  画布 Agent 面板（小面板 ⇄ 展开态双形态）
  - 小面板：360px 右侧浮层；展开态：居中大界面 + 会话列表侧栏（画布不被遮罩仍可点选）
  - 消息渲染/输入框/会话侧栏由 components/chat 共享组件承担（dense 形态 + --cb-* 主题注入）
  - Agent 特有 UI 留在面板：三档权限切换、阶段确认卡片、"/" 技能清单、风格卡片
  对话状态全部来自 agent store，主题 token 由 CanvasView 传入（与本目录其他面板一致）
-->
<template>
  <div ref="rootRef" class="canvas-agent-panel" :class="{ 'is-expanded': isExpanded }" :style="[rootVars, panelPosStyle]">
    <!-- 头部：标题 + 展开/清空/关闭（标题区可拖动；双击在大小两档预设间切换） -->
    <div
      class="panel-header"
      :style="{ borderColor: theme.toolbar.border }"
      @pointerdown="onHeaderPointerDown"
      @dblclick="onHeaderDblClick"
    >
      <div class="panel-title" :style="{ color: theme.node.text }">
        <Bot :size="16" />
        <span>{{ t('agent.title') }}</span>
      </div>
      <div class="header-btns">
        <button
          type="button"
          class="icon-btn"
          :aria-label="expandLabel"
          :title="expandLabel"
          @click="togglePreset()"
        >
          <Minimize2 v-if="isExpanded" :size="14" />
          <Maximize2 v-else :size="14" />
        </button>
        <button type="button" class="icon-btn" :aria-label="t('agent.clear')" :title="t('agent.clear')" @click="agent.clearSession()">
          <Trash2 :size="14" />
        </button>
        <button type="button" class="icon-btn" :aria-label="t('common.close')" :title="t('common.close')" @click="agent.open = false">
          <X :size="14" />
        </button>
      </div>
    </div>

    <!-- 主体：展开态加会话侧栏 -->
    <div class="panel-body">
      <ChatSessionSidebar
        v-if="isExpanded"
        :title="t('chat.title')"
        :sessions="sessionViews"
        :active-id="agent.activeSessionId"
        :extra-commands="sessionExtraCommands"
        @select="onSelectSession"
        @create="agent.createSession()"
        @rename="onRenameSession"
        @delete="onDeleteSession"
        @extra="onSessionExtra"
      />

      <div class="panel-chat">
        <!-- 消息流（共享列表，dense 形态；领域渲染经插槽注入） -->
        <ChatMessageList ref="listRef" :items="items" dense>
          <template #empty>
            <div class="empty" :style="{ color: theme.node.muted }">{{ t('agent.empty') }}</div>
          </template>
          <template #step-extra="{ step }">
            <!-- 风格库卡片：list_styles 完成后渲染可点选卡片（可视化选风格） -->
            <div v-if="styleEntriesOf(step).length" class="style-cards">
              <button
                v-for="s in styleEntriesOf(step)"
                :key="s.id"
                type="button"
                class="style-card"
                :style="{ borderColor: theme.toolbar.border }"
                :disabled="agent.busy"
                :title="s.description"
                @click="pickStyle(s)"
              >
                <img v-if="s.cover" :src="s.cover" alt="">
                <span v-else class="style-card-fallback" :style="{ background: theme.toolbar.activeBg, color: '#fff' }">{{ s.name.slice(0, 1) }}</span>
                <span class="style-card-name" :style="{ color: theme.node.text }">{{ s.name }}</span>
              </button>
              <button
                type="button"
                class="style-card style-card-custom"
                :style="{ borderColor: theme.toolbar.border, color: theme.node.muted }"
                :disabled="agent.busy"
                @click="customStyle()"
              >+ {{ t('agent.styleCustom') }}</button>
            </div>
          </template>
          <template #footer>
            <!-- 工作指示：模型思考/调用期 -->
            <div v-if="agent.busy && agent.thinking" class="thinking-row" :style="{ color: theme.node.muted }">
              <Loader2 :size="12" class="spin" />
              <span>{{ t('agent.thinking') }}</span>
            </div>

            <!-- 阶段门确认卡片：阶段成果审阅 -->
            <div v-if="agent.pendingConfirm?.kind === 'stage'" class="confirm-card" :style="confirmCardStyle">
              <div class="confirm-title" :style="{ color: theme.node.text }">{{ t('agent.stageTitle') }}：{{ agent.pendingConfirm.stage }}</div>
              <div v-if="agent.pendingConfirm.source" class="confirm-source" :style="{ color: theme.node.muted }">{{ t('agent.confirmSource') }}：{{ agent.pendingConfirm.source }}</div>
              <div class="confirm-summary" :style="{ color: theme.node.text }">{{ agent.pendingConfirm.summary }}</div>
              <div class="confirm-btns">
                <button
                  type="button"
                  class="confirm-btn"
                  :style="{ color: theme.toolbar.item, borderColor: theme.toolbar.border }"
                  @click="agent.confirmPending(false)"
                >{{ t('agent.stagePause') }}</button>
                <button
                  type="button"
                  class="confirm-btn primary"
                  :style="confirmPrimaryStyle"
                  @click="agent.confirmPending(true)"
                >{{ t('agent.stageContinue') }}</button>
              </div>
            </div>

            <!-- 写操作确认卡片 -->
            <div v-else-if="agent.pendingConfirm" class="confirm-card" :style="confirmCardStyle">
              <div class="confirm-title" :style="{ color: theme.node.text }">{{ t('agent.confirmTitle') }}</div>
              <div class="confirm-tool" :style="{ color: theme.toolbar.activeText }">{{ agent.pendingConfirm.tool }}</div>
              <pre class="confirm-args" :style="{ background: theme.toolbar.itemHover, color: theme.node.muted }">{{ prettyArgs }}</pre>
              <div class="confirm-btns">
                <button
                  type="button"
                  class="confirm-btn"
                  :style="{ color: theme.toolbar.item, borderColor: theme.toolbar.border }"
                  @click="agent.confirmPending(false)"
                >{{ t('common.cancel') }}</button>
                <button
                  type="button"
                  class="confirm-btn primary"
                  :style="confirmPrimaryStyle"
                  @click="agent.confirmPending(true)"
                >{{ t('common.confirm') }}</button>
              </div>
            </div>

            <div v-if="agent.error" class="error-line">{{ agent.error }}</div>
          </template>
        </ChatMessageList>

        <!-- 输入区（共享输入条；"/" 技能清单与附件预览经插槽注入） -->
        <ChatInputBar
          v-model="draft"
          :sending="agent.busy"
          stoppable
          :placeholder="t('agent.inputPlaceholder')"
          :has-attachments="pendingAttaches.length > 0"
          :accept="ATTACH_ACCEPT"
          @keydown="onDraftKeydown"
          @send="handleSend"
          @stop="agent.requestStop()"
          @pick-files="addFiles"
          @paste-image="onPasteImage"
          @drop-files="addFiles"
        >
          <!-- 权限模式胶囊（输入行内下拉，图标+名称+描述+对勾） -->
          <template #leading>
            <div class="agent-menu-anchor">
              <button
                type="button"
                class="pill-btn mode-pill"
                :title="currentMode?.hint"
                @click.stop="toggleMenu('mode')"
              >
                <component :is="currentMode?.icon" :size="13" />
                <span class="pill-text">{{ currentMode?.label }}</span>
                <ChevronDown :size="12" class="pill-chevron" :class="{ open: openMenu === 'mode' }" />
              </button>
              <div v-if="openMenu === 'mode'" class="pill-menu" :style="{ background: theme.toolbar.panel, borderColor: theme.toolbar.border }">
                <button
                  v-for="m in modeOptions"
                  :key="m.value"
                  type="button"
                  class="pill-menu-item"
                  :class="{ active: agent.mode === m.value }"
                  @click="pickMode(m.value)"
                >
                  <component :is="m.icon" :size="14" class="pill-menu-icon" />
                  <span class="pill-menu-body">
                    <span class="pill-menu-name" :style="{ color: theme.node.text }">{{ m.label }}</span>
                    <span class="pill-menu-desc" :style="{ color: theme.node.muted }">{{ m.hint }}</span>
                  </span>
                  <Check v-if="agent.mode === m.value" :size="14" class="pill-menu-check" :style="{ color: theme.node.text }" />
                </button>
              </div>
            </div>
          </template>

          <!-- 对话模型胶囊（共享组件；选择真实生效：内核 model id → BFF 命中 chat 注册表） -->
          <template #trail>
            <ChatModelPill
              :model-id="currentChatModelId"
              :models="chatModelChoices"
              @select="pickChatModel"
            />
          </template>

          <template #attachments>
            <div v-if="pendingAttaches.length" class="attach-strip">
              <div v-for="(a, i) in pendingAttaches" :key="a.id" class="attach-item" :style="{ borderColor: theme.toolbar.border }">
                <img v-if="a.kind === 'image'" class="attach-thumb" :src="a.dataUrl" alt="">
                <span v-else class="attach-file" :style="{ background: theme.toolbar.itemHover, color: theme.node.muted }">{{ a.name }}</span>
                <button type="button" class="attach-remove" :aria-label="t('common.cancel')" @click="removeAttach(i)">
                  <X :size="10" />
                </button>
              </div>
            </div>
            <ChatSkillMenu
              v-if="skillMenuVisible"
              :items="filteredSkills"
              :highlight="skillHighlight"
              @pick="pickSkill"
              @hover="(i: number) => (skillHighlight = i)"
            />
          </template>
        </ChatInputBar>
      </div>
    </div>

    <!-- 拉伸把手：四边+四角恒备（小面板此前缺右缘，现已补全）。贴内侧放置（overflow:hidden 会裁掉负偏移） -->
    <div class="edge-handle edge-n" @pointerdown.stop="onResizePointerDown($event, 'n')" />
    <div class="edge-handle edge-s" @pointerdown.stop="onResizePointerDown($event, 's')" />
    <div class="edge-handle edge-e" @pointerdown.stop="onResizePointerDown($event, 'e')" />
    <div class="edge-handle edge-w" @pointerdown.stop="onResizePointerDown($event, 'w')" />
    <div class="edge-handle corner-nw" @pointerdown.stop="onResizePointerDown($event, 'nw')" />
    <div class="edge-handle corner-ne" @pointerdown.stop="onResizePointerDown($event, 'ne')" />
    <div class="edge-handle corner-sw" @pointerdown.stop="onResizePointerDown($event, 'sw')" />
    <div class="edge-handle corner-se" @pointerdown.stop="onResizePointerDown($event, 'se')" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Bot, Trash2, X, Loader2, Maximize2, Minimize2, ChevronDown, Check,
  Eye, Hand, Zap,
} from 'lucide-vue-next'
import type { CSSProperties } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAgentStore } from '@/stores/agent'
import type { AgentMessage, AgentToolStep, AgentMode } from '@/stores/agent'
import { useCanvasStore } from '@/stores/canvas'
import { useModelsStore } from '@/stores/models'
import { summarizeChatSession } from '@/api/chat'
import { useConfirm } from '@/composables/useConfirm'
import { useSlashSkills } from '@/composables/useSlashSkills'
import {
  prepareImageFile, extractFileText, isImageFile, isSupportedFile,
  attachmentErrorKey, MAX_IMAGES_PER_MESSAGE,
} from '@/lib/agent/attachments'
import type { AgentImageAttachment } from '@/lib/agent/kernel'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatSkillMenu from '@/components/chat/ChatSkillMenu.vue'
import ChatModelPill from '@/components/chat/ChatModelPill.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import ChatSessionSidebar from '@/components/chat/ChatSessionSidebar.vue'
import type { ChatBubbleItem, ChatSessionCommand, ChatSessionView, ChatStepView } from '@/components/chat/types'

const props = defineProps({
  theme: { type: Object, required: true },
})

const { t } = useI18n()
const { confirm } = useConfirm()
const agent = useAgentStore()
const canvasStore = useCanvasStore()

const draft = ref('')
const listRef = ref<InstanceType<typeof ChatMessageList> | null>(null)
const rootRef = ref<HTMLElement | null>(null)

// ---------- 面板几何：唯一几何，尺寸决定形态（宽度过阈值即大面板态），拖动/拉伸/双击共用 ----------
interface PanelGeom { left: number; top: number; width: number; height: number }

const GEOM_KEY = 'agnes_agent_panel_geom'
const MIN_W = 320
const MIN_H = 320
/** 大小面板态的宽度分界（≥ 为大面板态：带会话侧栏） */
const EXPAND_MIN_W = 560

function readGeom(key: string): PanelGeom | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const g = JSON.parse(raw) as Partial<PanelGeom>
    const { left, top, width, height } = g
    if (typeof left !== 'number' || typeof top !== 'number' || typeof width !== 'number' || typeof height !== 'number') return null
    return { left, top, width, height }
  } catch {
    return null
  }
}

const geom = ref<PanelGeom | null>(readGeom(GEOM_KEY))

/** 形态由尺寸推导：没有显式几何（从未拖动/切换过）时是小面板态 */
const isExpanded = computed(() => (geom.value?.width ?? 0) >= EXPAND_MIN_W)

function saveGeom(): void {
  if (!geom.value) return
  try {
    localStorage.setItem(GEOM_KEY, JSON.stringify(geom.value))
  } catch {
    // 记忆失败不影响拖动
  }
}

/** 钳位：至少留 80px 在画布内，宽高不小于下限且不超出容器 */
function clampGeom(g: PanelGeom): PanelGeom {
  const parent = rootRef.value?.parentElement
  const maxW = parent?.clientWidth ?? 2000
  const maxH = parent?.clientHeight ?? 2000
  const width = Math.min(Math.max(g.width, MIN_W), maxW)
  const height = Math.min(Math.max(g.height, MIN_H), maxH)
  return {
    width,
    height,
    left: Math.min(Math.max(g.left, -width + 80), maxW - 80),
    top: Math.min(Math.max(g.top, 0), maxH - 48),
  }
}

const panelPosStyle = computed<CSSProperties>(() => {
  const g = geom.value
  if (!g) return {}
  return {
    left: `${g.left}px`,
    top: `${g.top}px`,
    right: 'auto',
    bottom: 'auto',
    width: `${g.width}px`,
    height: `${g.height}px`,
  }
})

/** 尺寸预设：小面板（右停靠 360）⇄ 大面板（居中 86%×86%），双击头部/展开按钮共用 */
function applyPreset(kind: 'small' | 'expanded'): void {
  const parent = rootRef.value?.parentElement
  const maxW = parent?.clientWidth ?? window.innerWidth
  const maxH = parent?.clientHeight ?? window.innerHeight
  if (kind === 'expanded') {
    const width = Math.round(maxW * 0.86)
    const height = Math.round(maxH * 0.86)
    geom.value = clampGeom({
      left: Math.round((maxW - width) / 2),
      top: Math.round(maxH * 0.07),
      width,
      height,
    })
  } else {
    geom.value = clampGeom({
      left: maxW - 360 - 16,
      top: 16,
      width: 360,
      height: Math.max(MIN_H, maxH - 112),
    })
  }
  saveGeom()
}

function togglePreset(): void {
  applyPreset(isExpanded.value ? 'small' : 'expanded')
}

function onHeaderDblClick(): void {
  togglePreset()
}

function beginPointerTracking(
  e: PointerEvent,
  onMove: (ev: PointerEvent) => void,
): void {
  const up = (): void => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', up)
    saveGeom()
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', up)
  e.preventDefault()
}

/** 基准几何：已有记忆用之；否则把当前实际位置换算为显式几何（首次拖动/拉伸时定型） */
function baseGeom(): PanelGeom | null {
  const current = geom.value
  if (current) return current
  const panel = rootRef.value
  const parent = panel?.parentElement
  if (!panel || !parent) return null
  const parentRect = parent.getBoundingClientRect()
  const rect = panel.getBoundingClientRect()
  return {
    left: rect.left - parentRect.left,
    top: rect.top - parentRect.top,
    width: rect.width,
    height: rect.height,
  }
}

/** 头部拖动移位（按钮不触发） */
function onHeaderPointerDown(e: PointerEvent): void {
  if (e.target instanceof Element && e.target.closest('button')) return
  const base = baseGeom()
  if (!base) return
  const startX = e.clientX
  const startY = e.clientY
  beginPointerTracking(e, (ev) => {
    geom.value = clampGeom({
      ...base,
      left: base.left + (ev.clientX - startX),
      top: base.top + (ev.clientY - startY),
    })
  })
}

/** 拉伸：dir 含 n/s 调高、e/w 调宽（w/n 同时移位，触底下限后收敛位置） */
function onResizePointerDown(e: PointerEvent, dir: string): void {
  const base = baseGeom()
  if (!base) return
  const startX = e.clientX
  const startY = e.clientY
  beginPointerTracking(e, (ev) => {
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    const g: PanelGeom = { ...base }
    if (dir.includes('e')) g.width = base.width + dx
    if (dir.includes('s')) g.height = base.height + dy
    if (dir.includes('w')) {
      g.width = base.width - dx
      g.left = base.left + dx
      if (g.width < MIN_W) {
        g.width = MIN_W
        g.left = base.left + base.width - MIN_W
      }
    }
    if (dir.includes('n')) {
      g.height = base.height - dy
      g.top = base.top + dy
      if (g.height < MIN_H) {
        g.height = MIN_H
        g.top = base.top + base.height - MIN_H
      }
    }
    geom.value = clampGeom(g)
  })
}

// ---------- 主题 token → 共享组件 --cb-* 变量（组件默认值即对话页观感，画布侧全量覆盖） ----------
const rootVars = computed<CSSProperties>(() => ({
  borderColor: props.theme.toolbar.border,
  boxShadow: '0 18px 45px rgba(0,0,0,.32)',
  '--cb-panel': props.theme.toolbar.panel,
  '--cb-user-bg': props.theme.toolbar.activeBg,
  '--cb-user-text': props.theme.toolbar.activeText,
  '--cb-ai-bg': props.theme.toolbar.itemHover,
  '--cb-ai-text': props.theme.node.text,
  '--cb-text': props.theme.node.text,
  '--cb-text-secondary': props.theme.node.text,
  '--cb-muted': props.theme.node.muted,
  '--cb-placeholder': props.theme.node.muted,
  '--cb-sidebar-bg': props.theme.toolbar.panel,
  '--cb-sidebar-border': props.theme.toolbar.border,
  '--cb-item-hover': props.theme.toolbar.itemHover,
  '--cb-item-active': props.theme.toolbar.activeBg,
  '--cb-item-active-border': props.theme.toolbar.border,
  '--cb-input-bg': props.theme.toolbar.panel,
  '--cb-input-border': props.theme.toolbar.border,
  '--cb-input-field-bg': props.theme.toolbar.itemHover,
  '--cb-input-field-border': 'transparent',
  '--cb-send-bg': props.theme.toolbar.activeBg,
  '--cb-send-text': props.theme.toolbar.activeText,
  '--cb-stop-bg': '#ef4444',
  '--cb-pill-text': props.theme.toolbar.item,
}))

const expandLabel = computed(() => (isExpanded.value ? t('agent.collapse') : t('agent.expand')))

// ---------- 消息视图映射（AgentMessage → ChatBubbleItem；步骤文案经 stepAction 转译） ----------
function attachmentSrc(img: AgentImageAttachment): string {
  return `data:${img.mimeType};base64,${img.data}`
}

function stepToView(step: AgentToolStep): ChatStepView {
  return {
    callId: step.callId,
    label: stepAction(step),
    tooltip: step.tool,
    status: step.status,
    result: step.result,
    progress: delegateProgressText(step),
  }
}

/** agent_delegate 步骤的实时进度文本（running 态渲染） */
function delegateProgressText(step: AgentToolStep): string | undefined {
  if (step.status !== 'running' || !step.delegateProgress) return undefined
  const { round, tool } = step.delegateProgress
  return `${t('agent.delegateProgress', { n: round })}${tool ? ` · ${tool}` : ''}`
}

const items = computed<ChatBubbleItem[]>(() =>
  agent.messages.map((m: AgentMessage) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    images: m.images?.length ? m.images.map((img) => ({ src: attachmentSrc(img) })) : undefined,
    steps: m.steps.length ? m.steps.map(stepToView) : undefined,
    createdAt: m.createdAt,
  })),
)

// ---------- 会话侧栏（展开态） ----------
const sessionViews = computed<ChatSessionView[]>(() =>
  agent.sessions.map((s) => ({ id: s.id, title: s.title, updatedAt: s.updatedAt })),
)

const sessionExtraCommands = computed<ChatSessionCommand[]>(() => [
  { command: 'summarize', label: t('chat.autoSummarize') },
])

function onSelectSession(id: number | string): void {
  void agent.switchSession(String(id))
}

function onRenameSession(id: number | string, title: string): void {
  void agent.renameSession(String(id), title)
}

function onSessionExtra(id: number | string, command: string): void {
  if (command === 'summarize') void summarizeSessionTitle(String(id))
}

/** AI 总结会话标题：复用对话页 summarize 端点（读已落库的消息行生成） */
async function summarizeSessionTitle(sessionId: string): Promise<void> {
  const s = agent.sessions.find((x) => x.id === sessionId)
  if (!s) return
  if (s.backendId == null) {
    ElMessage.warning(t('agent.sessionNotSynced'))
    return
  }
  try {
    ElMessage.info(t('chat.summarizing'))
    const updated = await summarizeChatSession(s.backendId)
    agent.applyTitle(sessionId, updated.title)
    ElMessage.success(t('chat.summarizeSuccess') + ': ' + updated.title)
  } catch (e: unknown) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('chat.summarizeFailed'))
  }
}

async function onDeleteSession(id: number | string): Promise<void> {
  try {
    await confirm(t('chat.confirmDelete'), t('common.confirm'))
    await agent.deleteSession(String(id))
  } catch {
    // 取消删除
  }
}

// ---------- 附件（图片随消息发 base64；文件解析为文本拼进消息） ----------
const ATTACH_ACCEPT = 'image/*,.txt,.md,.markdown,.json,.csv,.log,.ts,.tsx,.js,.mjs,.py,.html,.css,.xml,.yml,.yaml,.pdf,.docx'

interface PendingImage { kind: 'image'; id: string; name: string; attachment: AgentImageAttachment; dataUrl: string }
interface PendingFile { kind: 'file'; id: string; name: string; text: string }
type PendingAttach = PendingImage | PendingFile

const pendingAttaches = ref<PendingAttach[]>([])
let attachSeq = 0

async function addFiles(files: File[]): Promise<void> {
  for (const f of files) {
    if (agent.busy) break
    try {
      if (isImageFile(f)) {
        const imageCount = pendingAttaches.value.filter((a) => a.kind === 'image').length
        if (imageCount >= MAX_IMAGES_PER_MESSAGE) {
          ElMessage.warning(t('agent.tooManyImages', { n: MAX_IMAGES_PER_MESSAGE }))
          break
        }
        const attachment = await prepareImageFile(f)
        pendingAttaches.value.push({ kind: 'image', id: `a${++attachSeq}`, name: f.name, attachment, dataUrl: attachmentSrc(attachment) })
      } else if (isSupportedFile(f)) {
        const { name, text } = await extractFileText(f)
        pendingAttaches.value.push({ kind: 'file', id: `a${++attachSeq}`, name, text })
      } else {
        ElMessage.warning(t('agent.unsupportedType'))
      }
    } catch (e) {
      ElMessage.warning(t(`agent.${attachmentErrorKey(e)}`))
    }
  }
}

function onPasteImage(file: File): void {
  void addFiles([file])
}

function removeAttach(idx: number): void {
  pendingAttaches.value.splice(idx, 1)
}

// ---------- "/" 技能快速清单（共享组合式；菜单渲染用共享 ChatSkillMenu） ----------
const { skillMenuVisible, filteredSkills, skillHighlight, pickSkill, handleMenuKeydown } = useSlashSkills(draft, () => !agent.busy)

function onDraftKeydown(e: KeyboardEvent): void {
  handleMenuKeydown(e)
}

// ---------- 三档权限（胶囊菜单） ----------
const modeOptions = computed(() => [
  { value: 'readonly' as AgentMode, icon: Eye, label: t('agent.modeReadonly'), hint: t('agent.modeReadonlyHint') },
  { value: 'confirm' as AgentMode, icon: Hand, label: t('agent.modeConfirm'), hint: t('agent.modeConfirmHint') },
  { value: 'auto' as AgentMode, icon: Zap, label: t('agent.modeAuto'), hint: t('agent.modeAutoHint') },
])

const currentMode = computed(() => modeOptions.value.find((m) => m.value === agent.mode))

// ---------- 输入行模式胶囊（模型胶囊为共享 ChatModelPill） ----------
const openMenu = ref<'mode' | null>(null)

function toggleMenu(m: 'mode'): void {
  openMenu.value = openMenu.value === m ? null : m
}

function closeMenu(): void {
  openMenu.value = null
}

function pickMode(value: AgentMode): void {
  agent.mode = value
  closeMenu()
}

const modelsStore = useModelsStore()

const chatModelChoices = computed(() => modelsStore.chatModels)
/** 当前生效模型：用户选择优先，否则跟随后端默认解析链（偏好 default_chat_model_id > 列表第一个） */
const currentChatModelId = computed(() => agent.chatModelId || modelsStore.getDefaultModel('chat'))

function pickChatModel(id: string): void {
  agent.setChatModel(id)
  closeMenu()
}

/** 点胶囊菜单外部关闭 */
function onPointerDown(e: PointerEvent): void {
  if (!openMenu.value) return
  if (e.target instanceof Element && e.target.closest('.agent-menu-anchor')) return
  closeMenu()
}

// ---------- 确认卡片 ----------
const confirmCardStyle = computed(() => ({
  background: props.theme.node.panel,
  borderColor: props.theme.toolbar.border,
}))

const confirmPrimaryStyle = computed(() => ({
  background: props.theme.toolbar.activeBg,
  color: props.theme.toolbar.activeText,
  borderColor: 'transparent',
}))

// 确认卡片参数预览（截断防超长）
const prettyArgs = computed(() => {
  if (!agent.pendingConfirm) return ''
  const text = JSON.stringify(agent.pendingConfirm.args, null, 2)
  return text.length > 600 ? `${text.slice(0, 600)}\n…` : text
})

// ---------- 工具步骤转译（中文动作为主行，英文工具名收进 tooltip） ----------
/** 风格卡片数据：list_styles 步骤结果可解析时返回条目（守卫式，不做类型断言） */
interface AgentStyleEntry { id: number; name: string; description: string; cover: string }
function styleEntriesOf(step: ChatStepView): AgentStyleEntry[] {
  if (step.tooltip !== 'storyboard_list_styles' || step.status !== 'done' || !step.result) return []
  try {
    const parsed: unknown = JSON.parse(step.result)
    if (typeof parsed !== 'object' || parsed === null) return []
    const styles = (parsed as Record<string, unknown>).styles
    if (!Array.isArray(styles)) return []
    const out: AgentStyleEntry[] = []
    for (const item of styles) {
      if (typeof item !== 'object' || item === null) continue
      const rec = item as Record<string, unknown>
      if (typeof rec.id !== 'number' || typeof rec.name !== 'string') continue
      out.push({
        id: rec.id,
        name: rec.name,
        description: typeof rec.description === 'string' ? rec.description : '',
        cover: typeof rec.cover_image === 'string' ? rec.cover_image : '',
      })
    }
    return out
  } catch {
    return []
  }
}

/** 点选风格卡片：以用户口吻发消息，Agent 走 storyboard_set_style 落库并继续管线 */
function pickStyle(entry: AgentStyleEntry) {
  void agent.send(t('agent.stylePickedMsg', { name: entry.name, id: entry.id }))
}

/** 自定义风格：弹窗输入描述，经 storyboard_set_style 走正路（所有提示词统一带此风格段） */
async function customStyle() {
  try {
    const { value } = await ElMessageBox.prompt(
      t('agent.stylePromptPlaceholder'),
      t('agent.stylePromptTitle'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), inputPattern: /\S/, inputErrorMessage: t('agent.stylePromptEmpty') },
    )
    if (value && value.trim()) void agent.send(t('agent.styleCustomMsg', { text: value.trim() }))
  } catch {
    // 用户取消
  }
}

function stepAction(step: AgentToolStep): string {
  const args = step.args
  const nodeName = (ref: unknown): string => {
    if (typeof ref !== 'string') return ''
    const panel = canvasStore.panels.find((p) => p.id === ref)
    return panel?.name || ref
  }
  switch (step.tool) {
    case 'agent_get_state':
      return t('agent.actGetState')
    case 'agent_get_selection':
      return t('agent.actGetSelection')
    case 'agent_get_models':
      return t('agent.actGetModels')
    case 'agent_stage_review':
      return typeof args.stage === 'string' && args.stage
        ? `${t('agent.actStageReview')}：${args.stage}`
        : t('agent.actStageReview')
    case 'agent_select':
      return `${t('agent.actSelect')}：${nodeName(args.panel_id)}`
    case 'agent_read_image':
      return `${t('agent.actReadImage')}：${nodeName(args.panel_id)}`
    case 'agent_load_skill':
      return `${t('agent.actLoadSkill')}：${typeof args.name === 'string' ? args.name : ''}`
    case 'agent_create_text_node':
      return `${t('agent.actCreateText')}${typeof args.name === 'string' && args.name ? `：${args.name}` : ''}`
    case 'agent_apply_ops': {
      const ops = Array.isArray(args.ops) ? args.ops : []
      const count = (kind: string) => ops.filter((o) => o && typeof o === 'object' && !Array.isArray(o) && (o as Record<string, unknown>).op === kind).length
      const parts: string[] = []
      if (count('add_panel')) parts.push(`${t('agent.opsAddPanel')} ×${count('add_panel')}`)
      if (count('add_connection')) parts.push(`${t('agent.opsConnect')} ×${count('add_connection')}`)
      if (count('update_panel')) parts.push(`${t('agent.opsUpdatePanel')} ×${count('update_panel')}`)
      if (count('delete_panel') || count('delete_connection')) parts.push(`${t('agent.opsDelete')} ×${count('delete_panel') + count('delete_connection')}`)
      return parts.length ? `${t('agent.actApplyOps')}：${parts.join(t('agent.opsJoiner'))}` : t('agent.actApplyOps')
    }
    case 'agent_run_generation': {
      const kind = typeof args.kind === 'string' ? args.kind : ''
      const label = kind === 'video' ? t('agent.actGenVideo') : kind === 'compose' ? t('agent.actCompose') : t('agent.actGenImage')
      const name = nodeName(args.panel_id)
      return name ? `${label}：${name}` : label
    }
    default:
      return step.tool
  }
}

// ---------- 发送 ----------
function handleSend() {
  if (agent.busy) return
  const text = draft.value.trim()
  const images: AgentImageAttachment[] = []
  const fileParts: string[] = []
  for (const a of pendingAttaches.value) {
    if (a.kind === 'image') images.push(a.attachment)
    else fileParts.push(`【文件：${a.name}】\n${a.text}`)
  }
  if (!text && images.length === 0) return
  const fullText = fileParts.length ? (text ? text + '\n\n' : '') + fileParts.join('\n\n') : text
  draft.value = ''
  pendingAttaches.value = []
  void agent.send(fullText, images)
}

// ---------- 生命周期 ----------
/** Esc 优先级：先关胶囊菜单，再收起展开态（输入条已消费的 Esc 不再重复处理） */
function onWindowKeydown(e: KeyboardEvent): void {
  if (e.defaultPrevented) return
  if (e.key === 'Escape' && openMenu.value) {
    e.preventDefault()
    closeMenu()
    return
  }
  if (e.key === 'Escape' && isExpanded.value) applyPreset('small')
}

// 面板打开/工作区切换时恢复会话
onMounted(() => {
  void modelsStore.fetchConfig()
  agent.ensureSession()
  window.addEventListener('keydown', onWindowKeydown)
  window.addEventListener('pointerdown', onPointerDown)
  // 记忆的几何按当前容器钳位一次（窗口可能变小过）
  if (geom.value) geom.value = clampGeom(geom.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onWindowKeydown)
  window.removeEventListener('pointerdown', onPointerDown)
})

watch(() => canvasStore.activeWorkspaceId, () => agent.ensureSession())

// 确认卡出现/思考指示/错误行：滚动到底部（消息增长由 ChatMessageList 自锚定）
watch(
  () => [agent.pendingConfirm, agent.thinking, agent.error],
  () => {
    void listRef.value?.scrollToBottom(true)
  },
)
</script>

<style scoped>
.canvas-agent-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  bottom: 96px;
  width: 360px;
  display: flex;
  flex-direction: column;
  border: 1px solid transparent;
  border-radius: 12px;
  z-index: 60;
  overflow: hidden;
  /* 小面板浮层：保持主题 token 的半透明（透过可见画布） */
  background: var(--cb-panel, var(--agnes-bg-elevated, #171a26));
}

/* 大面板态（宽度 ≥ 阈值推导，布局完全由几何驱动）：阅读面需不透明底 */
.canvas-agent-panel.is-expanded {
  /* 不透明垫层在下 + 主题面板色叠上（toolbar.panel 是 .80 半透明，直接用会透出画布看不清字） */
  background:
    linear-gradient(0deg, var(--cb-panel, transparent), var(--cb-panel, transparent)),
    var(--agnes-bg-elevated, #171a26);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 6px;
  border-bottom: 1px solid transparent;
  cursor: grab;
  touch-action: none;
}

.panel-header:active {
  cursor: grabbing;
}

/* 拉伸把手（贴内侧放置：overflow:hidden 会裁掉负偏移） */
.edge-handle {
  position: absolute;
  z-index: 5;
  touch-action: none;
}

.edge-n {
  top: 0;
  left: 0;
  right: 0;
  height: 6px;
  cursor: ns-resize;
}

.edge-s {
  bottom: 0;
  left: 0;
  right: 0;
  height: 6px;
  cursor: ns-resize;
}

.edge-e {
  right: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
}

.edge-w {
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
}

.corner-nw,
.corner-se {
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
}

.corner-ne,
.corner-sw {
  width: 14px;
  height: 14px;
  cursor: nesw-resize;
}

.corner-nw {
  left: 0;
  top: 0;
}

.corner-ne {
  right: 0;
  top: 0;
}

.corner-sw {
  left: 0;
  bottom: 0;
}

.corner-se {
  right: 0;
  bottom: 0;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}

.header-btns {
  display: flex;
  gap: 4px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  opacity: 0.75;
}

.icon-btn:hover {
  opacity: 1;
  background: rgba(128, 128, 128, 0.18);
}

/* 输入行胶囊（模式/模型）与其下拉菜单 */
.agent-menu-anchor {
  position: relative;
  flex: none;
}

.pill-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--cb-pill-text, var(--agnes-text-muted, #8b93a8));
  cursor: pointer;
  font-size: 12px;
  max-width: 130px;
}

.pill-btn:hover {
  background: var(--cb-item-hover, rgba(128, 128, 128, 0.18));
}

/* 小面板自适应：360px 下模式胶囊图标化、模型胶囊限宽，把空间让给输入框 */
.canvas-agent-panel:not(.is-expanded) .pill-btn.mode-pill {
  width: 32px;
  padding: 0;
  justify-content: center;
}

.canvas-agent-panel:not(.is-expanded) .pill-btn.mode-pill .pill-text,
.canvas-agent-panel:not(.is-expanded) .pill-btn.mode-pill .pill-chevron {
  display: none;
}


.pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pill-chevron {
  flex: none;
  opacity: 0.7;
  transition: transform 0.15s ease;
}

.pill-chevron.open {
  transform: rotate(180deg);
}

.pill-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  min-width: 230px;
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 70;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}

.pill-menu-title {
  padding: 6px 10px 4px;
  font-size: 11px;
}

.pill-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.pill-menu-item:hover,
.pill-menu-item.active {
  background: var(--cb-item-hover, rgba(128, 128, 128, 0.18));
}

.pill-menu-icon {
  flex: none;
  color: var(--cb-pill-text, var(--agnes-text-muted, #8b93a8));
}

.pill-menu-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.pill-menu-name {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pill-menu-desc {
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pill-menu-check {
  flex: none;
}

/* 主体（展开态 = 侧栏 + 聊天列） */
.panel-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.panel-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 共享列表/输入条在面板内的密度适配 */
.panel-chat :deep(.cb-list) {
  padding: 6px 12px 12px;
  gap: 10px;
}

.panel-chat :deep(.cb-input) {
  padding: 8px 12px 10px;
}

.empty {
  margin-top: 32px;
  text-align: center;
  font-size: 12px;
}

.thinking-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0 0 4px;
  font-size: 12px;
}

/* 风格卡片（步骤插槽注入） */
.style-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0 2px;
}
.style-card {
  width: 88px;
  border: 1px solid;
  border-radius: 10px;
  padding: 0 0 4px;
  overflow: hidden;
  cursor: pointer;
  background: transparent;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.style-card:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.style-card img,
.style-card-fallback {
  width: 100%;
  height: 56px;
  object-fit: cover;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 600;
}
.style-card-name {
  font-size: 11px;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.style-card-custom {
  height: auto;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border-style: dashed;
  min-height: 74px;
  box-sizing: border-box;
}

/* 确认卡片 */
.confirm-card {
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

.confirm-title {
  font-size: 12px;
  font-weight: 600;
}

.confirm-source {
  font-size: 11px;
}

.confirm-tool {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.confirm-args {
  margin: 0;
  max-height: 140px;
  overflow: auto;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
}

.confirm-summary {
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.confirm-btns {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.confirm-btn {
  padding: 4px 14px;
  font-size: 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.error-line {
  font-size: 12px;
  color: #f87171;
  white-space: pre-wrap;
}

.spin {
  animation: agent-spin 1s linear infinite;
}

@keyframes agent-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 附件预览条（输入条插槽内容） */
.attach-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.attach-item {
  position: relative;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 2px;
}

.attach-thumb {
  display: block;
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 6px;
}

.attach-file {
  display: inline-block;
  max-width: 150px;
  padding: 10px 8px;
  font-size: 11px;
  border-radius: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.attach-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  cursor: pointer;
  padding: 0;
}

</style>

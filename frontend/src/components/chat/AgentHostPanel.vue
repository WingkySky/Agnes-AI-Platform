<template>
  <div
    v-if="visible"
    ref="rootRef"
    class="agent-host-panel"
    :class="{ 'is-expanded': isExpanded }"
    :style="[rootVars, panelPosStyle]"
  >
    <!-- 头部：标题 + 能力清单/展开/清空/关闭（标题区可拖动；双击在大小两档间切换） -->
    <div
      class="panel-header"
      :style="{ borderColor: theme.toolbar.border }"
      @pointerdown="onHeaderPointerDown"
      @dblclick="onHeaderDblClick"
    >
      <div class="panel-title" :style="{ color: theme.node.text }">
        <Bot :size="16" />
        <span>{{ t('agent.drawerTitle') }}</span>
      </div>
      <div class="header-btns">
        <div v-if="chat.mcpCapabilities.length || chat.memoryAvailable" class="cap-anchor">
          <button
            type="button"
            class="icon-btn cap-trigger"
            :aria-label="t('agent.capabilitiesTitle')"
            :title="t('agent.capabilitiesTitle')"
            @pointerdown.stop
            @click="toolsOpen = !toolsOpen"
          >
            <Zap :size="14" />
            <span v-if="chat.memoryPreferences.length" class="cap-dot">{{ chat.memoryPreferences.length }}</span>
          </button>
          <div v-if="toolsOpen" class="cap-dropdown cap-dropdown-down" :style="{ borderColor: theme.toolbar.border, background: theme.toolbar.panel }" @click.stop @pointerdown.stop>
            <template v-if="chat.mcpCapabilities.length">
              <div class="cap-section-title" :style="{ color: theme.node.muted }">{{ t('agent.capabilities') }}</div>
              <div v-for="c in chat.mcpCapabilities" :key="c.name" class="cap-item">
                <div class="cap-item-name" :style="{ color: theme.node.text }">{{ c.name }}</div>
                <div class="cap-item-tools" :style="{ color: theme.node.muted }">{{ c.tools.slice(0, 6).join('、') }}{{ c.tools.length > 6 ? ' …' : '' }}</div>
              </div>
            </template>
            <template v-if="chat.memoryAvailable">
              <div class="cap-section-title" :style="{ color: theme.node.muted }">{{ t('agent.memoryPill') }}</div>
              <template v-if="chat.memoryPreferences.length">
                <div v-for="p in chat.memoryPreferences" :key="p" class="cap-item mem-row">
                  <span class="cap-item-name" :style="{ color: theme.node.text }">{{ p }}</span>
                  <button type="button" class="mem-del" :style="{ color: theme.node.muted }" :title="t('common.delete')" @click="removePreference(p)">×</button>
                </div>
                <button type="button" class="mem-clear" :style="{ color: theme.node.muted }" @click="clearAllPreferences">{{ t('agent.memoryClear') }}</button>
              </template>
              <div v-else class="cap-item-tools" :style="{ color: theme.node.muted }">{{ t('agent.memoryEmpty') }}</div>
            </template>
          </div>
        </div>
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
        <button type="button" class="icon-btn" :aria-label="t('agent.clear')" :title="t('agent.clear')" @click="clearActiveSession">
          <Trash2 :size="14" />
        </button>
        <button type="button" class="icon-btn" :aria-label="t('common.close')" :title="t('common.close')" @click="close">
          <X :size="14" />
        </button>
      </div>
    </div>

    <!-- 无会话时的欢迎页 -->
    <div v-if="!chat.hasActiveSession" class="host-welcome">
      <el-icon :size="36"><ChatDotRound /></el-icon>
      <p>{{ t('chat.welcomeDesc') }}</p>
      <el-button type="primary" @click="handleNewSession">{{ t('chat.startChat') }}</el-button>
    </div>

    <!-- 主体：展开态加会话侧栏 -->
    <div v-else class="panel-body">
      <ChatSessionSidebar
        v-if="isExpanded"
        :title="t('chat.title')"
        :sessions="sessionViews"
        :active-id="chat.activeSessionId"
        :extra-commands="sessionExtraCommands"
        @select="onSelectSession"
        @create="onCreateSession"
        @rename="onRenameSession"
        @delete="onDeleteSession"
        @extra="onSessionExtra"
      />

      <div class="panel-chat">
        <!-- 消息流（共享列表 + store 统一投影；领域渲染经插槽注入） -->
        <ChatMessageList ref="listRef" :items="chat.messageItems" dense>
          <template #empty>
            <div class="empty">{{ t('agent.empty') }}</div>
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
                :disabled="chat.busy"
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
                :disabled="chat.busy"
                @click="customStyle()"
              >+ {{ t('agent.styleCustom') }}</button>
            </div>
          </template>
          <template #footer>
            <div v-if="chat.busy && chat.thinking" class="thinking-row" :style="{ color: theme.node.muted }">
              <Loader2 :size="12" class="spin" />
              <span>{{ t('agent.thinking') }}</span>
            </div>

            <!-- 阶段门确认卡片：阶段成果审阅 -->
            <div v-if="chat.pendingConfirm?.kind === 'stage'" class="confirm-card" :style="confirmCardStyle">
              <div class="confirm-title" :style="{ color: theme.node.text }">{{ t('agent.stageTitle') }}：{{ chat.pendingConfirm.stage }}</div>
              <div v-if="chat.pendingConfirm.source" class="confirm-source" :style="{ color: theme.node.muted }">{{ t('agent.confirmSource') }}：{{ chat.pendingConfirm.source }}</div>
              <div class="confirm-summary" :style="{ color: theme.node.text }">{{ chat.pendingConfirm.summary }}</div>
              <div class="confirm-btns">
                <button
                  type="button"
                  class="confirm-btn"
                  :style="{ color: theme.toolbar.item, borderColor: theme.toolbar.border }"
                  @click="chat.confirmPending(false)"
                >{{ t('agent.stagePause') }}</button>
                <button
                  type="button"
                  class="confirm-btn primary"
                  :style="confirmPrimaryStyle"
                  @click="chat.confirmPending(true)"
                >{{ t('agent.stageContinue') }}</button>
              </div>
            </div>

            <!-- 写操作确认卡片 -->
            <div v-else-if="chat.pendingConfirm" class="confirm-card" :style="confirmCardStyle">
              <div class="confirm-title" :style="{ color: theme.node.text }">{{ t('agent.confirmTitle') }}</div>
              <div class="confirm-tool" :style="{ color: theme.toolbar.activeText }" :title="chat.pendingConfirm.tool">{{ toolStepLabel(chat.pendingConfirm.tool) }}</div>
              <pre class="confirm-args" :style="{ background: theme.toolbar.itemHover, color: theme.node.muted }">{{ prettyArgs }}</pre>
              <div class="confirm-btns">
                <button
                  type="button"
                  class="confirm-btn"
                  :style="{ color: theme.toolbar.item, borderColor: theme.toolbar.border }"
                  @click="chat.confirmPending(false)"
                >{{ t('common.cancel') }}</button>
                <button
                  type="button"
                  class="confirm-btn primary"
                  :style="confirmPrimaryStyle"
                  @click="chat.confirmPending(true)"
                >{{ t('common.confirm') }}</button>
              </div>
            </div>

            <div v-if="chat.activeError" class="error-line">{{ chat.activeError }}</div>
          </template>
        </ChatMessageList>

        <!-- 输入区（共享输入条 + useChatComposer 发送链收口；"/" 技能与附件经插槽注入） -->
        <ChatInputBar
          v-model="inputText"
          :sending="chat.busy"
          stoppable
          :placeholder="t('chat.inputPlaceholder')"
          :has-attachments="pendingAttachments.length > 0"
          :accept="ATTACH_ACCEPT"
          :paste-images="false"
          @keydown="onDraftKeydown"
          @send="handleSend"
          @stop="chat.requestStop()"
          @pick-files="onFilesPicked"
          @drop-files="onFilesPicked"
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
                  :class="{ active: chat.agentMode === m.value }"
                  @click="pickMode(m.value)"
                >
                  <component :is="m.icon" :size="14" class="pill-menu-icon" />
                  <span class="pill-menu-body">
                    <span class="pill-menu-name" :style="{ color: theme.node.text }">{{ m.label }}</span>
                    <span class="pill-menu-desc" :style="{ color: theme.node.muted }">{{ m.hint }}</span>
                  </span>
                  <Check v-if="chat.agentMode === m.value" :size="14" class="pill-menu-check" :style="{ color: theme.node.text }" />
                </button>
              </div>
            </div>
          </template>

          <!-- 对话模型胶囊（共享组件；选择真实生效：内核 model id → BFF 命中 chat 注册表） -->
          <template #trail>
            <ChatModelPill
              :model-id="chat.chatModelId || modelsStore.getDefaultModel('chat')"
              :models="modelsStore.chatModels"
              @select="(id: string) => chat.setChatModel(id)"
            />
          </template>

          <template #attachments>
            <ChatPendingAttachments :attachments="pendingAttachments" @remove="removePendingAttachment" />
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

    <!-- 拉伸把手：四边+四角恒备。贴内侧放置（overflow:hidden 会裁掉负偏移） -->
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
/* =====================================================
 * AgentHostPanel — 全局 Agent 宿主（自绘浮层双形态）
 * 小态右停靠 360 ⇄ 展开态居中 86%（头部拖动/双击切换/位置记忆），
 * 无遮罩：小态点外部收起（页面仍可交互），展开态 Esc/按钮退出。
 * 能力内置（自画布面板迁入）：三档权限胶囊、阶段/工具确认卡、
 * 风格卡片、能力清单（MCP/记忆）、会话侧栏（展开态）+ 画布会话跳转。
 * 发送链走 useChatComposer（与对话页/抽屉同源）；开关态 = chat store
 * agentDrawerOpen（顶栏按钮/Alt+A/粘贴互斥守卫语义不变）。
 * 主题 token 可选注入，缺省映射 agnes 全局变量（自动跟随深浅色）。
 * ===================================================== */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Bot, Trash2, X, Loader2, Maximize2, Minimize2, ChevronDown, Check,
  Eye, Hand, Zap,
} from 'lucide-vue-next'
import { ChatDotRound } from '@element-plus/icons-vue'
import type { CSSProperties } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useChatStore, toStepStatus } from '@/stores/chat'
import type { AgentMode } from '@/lib/agent/policy'
import { useCanvasStore } from '@/stores/canvas'
import { useModelsStore } from '@/stores/models'
import { useConfirm } from '@/composables/useConfirm'
import { useChatComposer } from '@/composables/useChatComposer'
import { toolStepLabel } from '@/lib/agent/tool-labels'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatSkillMenu from '@/components/chat/ChatSkillMenu.vue'
import ChatModelPill from '@/components/chat/ChatModelPill.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import ChatSessionSidebar from '@/components/chat/ChatSessionSidebar.vue'
import ChatPendingAttachments from '@/components/chat/ChatPendingAttachments.vue'
import {
  HOST_GEOM_KEY, HOST_MIN_W, HOST_MIN_H, clampGeom, isExpandedGeom, presetGeom, readGeom, saveGeom,
} from '@/components/chat/agent-host-geom'
import type { PanelGeom } from '@/components/chat/agent-host-geom'
import { DEFAULT_HOST_THEME } from '@/components/chat/agent-host-theme'
import type { HostTheme } from '@/components/chat/agent-host-theme'
import type { ChatSessionCommand, ChatSessionView, ChatStepView } from '@/components/chat/types'

const props = defineProps({
  theme: { type: Object as () => HostTheme, default: () => DEFAULT_HOST_THEME },
})

const { t } = useI18n()
const { confirm } = useConfirm()
const router = useRouter()
const chat = useChatStore()
const canvasStore = useCanvasStore()
const modelsStore = useModelsStore()

const visible = computed({
  get: () => chat.agentDrawerOpen,
  set: (open: boolean) => chat.setAgentDrawerOpen(open),
})

function close() {
  chat.setAgentDrawerOpen(false)
}

// ---------- 发送链路收口（共享组合式：附件/发送/"/"技能；全局粘贴互斥=宿主开着只收宿主的） ----------
const {
  inputText,
  pendingAttachments,
  handleSend,
  onFilesPicked,
  removePendingAttachment,
  onDraftKeydown,
  skillMenuVisible,
  filteredSkills,
  skillHighlight,
  pickSkill,
} = useChatComposer({ enabled: () => chat.agentDrawerOpen })

/** 附件选择器放宽到文本文档（useChatComposer 会解析为文本拼进输入框） */
const ATTACH_ACCEPT = 'image/*,.txt,.md,.markdown,.json,.csv,.log,.ts,.tsx,.js,.mjs,.py,.html,.css,.xml,.yml,.yaml,.pdf,.docx'

const listRef = ref<InstanceType<typeof ChatMessageList> | null>(null)
const rootRef = ref<HTMLElement | null>(null)

// ---------- 面板几何：唯一几何，尺寸决定形态（宽度过阈值即展开态），拖动/拉伸/双击共用（纯函数见 agent-host-geom） ----------
const geom = ref<PanelGeom | null>(readGeom(HOST_GEOM_KEY))

const isExpanded = computed(() => isExpandedGeom(geom.value))

/** 视口钳位后落盘 */
function commitGeom(g: PanelGeom): void {
  geom.value = clampGeom(g, window.innerWidth, window.innerHeight)
  saveGeom(HOST_GEOM_KEY, geom.value)
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

/** 尺寸预设：小面板（右停靠 360）⇄ 展开态（居中 86%×86%），双击头部/展开按钮共用 */
function applyPreset(kind: 'small' | 'expanded'): void {
  commitGeom(presetGeom(kind, window.innerWidth, window.innerHeight))
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
    if (geom.value) saveGeom(HOST_GEOM_KEY, geom.value)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', up)
  e.preventDefault()
}

/** 基准几何：已有记忆用之；否则把当前实际位置换算为显式几何（首次拖动/拉伸时定型；fixed 直接用视口坐标） */
function baseGeom(): PanelGeom | null {
  const current = geom.value
  if (current) return current
  const panel = rootRef.value
  if (!panel) return null
  const rect = panel.getBoundingClientRect()
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
}

/** 头部拖动移位（按钮不触发） */
function onHeaderPointerDown(e: PointerEvent): void {
  if (e.target instanceof Element && e.target.closest('button')) return
  const base = baseGeom()
  if (!base) return
  const startX = e.clientX
  const startY = e.clientY
  beginPointerTracking(e, (ev) => {
    commitGeom({
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
      if (g.width < HOST_MIN_W) {
        g.width = HOST_MIN_W
        g.left = base.left + base.width - HOST_MIN_W
      }
    }
    if (dir.includes('n')) {
      g.height = base.height - dy
      g.top = base.top + dy
      if (g.height < HOST_MIN_H) {
        g.height = HOST_MIN_H
        g.top = base.top + base.height - HOST_MIN_H
      }
    }
    commitGeom(g)
  })
}

// ---------- 主题 token → 共享组件 --cb-* 变量（缺省即 agnes 全局观感） ----------
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

// ---------- 会话侧栏（展开态）+ 画布会话跳转 ----------
const sessionViews = computed<ChatSessionView[]>(() =>
  chat.sessions.map((s) => ({ id: s.id, title: s.title, updatedAt: s.updated_at || '' })),
)

const sessionExtraCommands = computed<ChatSessionCommand[]>(() => [
  { command: 'summarize', label: t('chat.autoSummarize') },
])

/** 切换会话（画布会话跳画布续聊：内核依赖画布上下文，同对话页规则） */
function onSelectSession(id: number | string): void {
  const session = chat.sessions.find((s) => s.id === Number(id))
  if (session?.session_type === 'canvas') {
    close()
    void router.push({
      path: '/canvas',
      query: { workspace: session.workspace_id || '', session: String(session.id) },
    })
    return
  }
  void chat.switchSession(Number(id))
}

/** 新建会话：画布页上带上当前工作区上下文标记（面板同规则），其他页面普通会话 */
function onCreateSession(): void {
  handleNewSession()
}

function handleNewSession() {
  void chat.newSession(undefined, canvasStore.activeWorkspaceId ?? undefined).catch(() => {
    ElMessage.error(t('chat.createFailed'))
  })
}

function clearActiveSession(): void {
  void chat.clearActiveSession()
}

function onRenameSession(id: number | string, title: string): void {
  void chat.updateSessionTitle(Number(id), title)
}

function onSessionExtra(id: number | string, command: string): void {
  if (command === 'summarize') void summarizeSessionTitle(String(id))
}

/** AI 总结会话标题（统一会话即后端会话，直接按 id 总结） */
async function summarizeSessionTitle(sessionId: number | string): Promise<void> {
  try {
    ElMessage.info(t('chat.summarizing'))
    await chat.autoSummarizeSession(Number(sessionId))
    ElMessage.success(t('chat.summarizeSuccess'))
  } catch (e: unknown) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('chat.summarizeFailed'))
  }
}

async function onDeleteSession(id: number | string): Promise<void> {
  try {
    await confirm(t('chat.confirmDelete'), t('common.confirm'))
    await chat.removeSession(Number(id))
  } catch {
    // 取消删除
  }
}

// ---------- "/" 技能菜单外的下拉状态（模式胶囊 + 能力清单） ----------
const toolsOpen = ref(false)

async function removePreference(p: string) {
  try {
    await chat.removeMemoryPreference(p)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function clearAllPreferences() {
  await confirm(t('agent.memoryClearConfirm'), t('common.confirm'))
  try {
    await chat.clearMemory()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

// ---------- 三档权限（胶囊菜单） ----------
const modeOptions = computed(() => [
  { value: 'readonly' as AgentMode, icon: Eye, label: t('agent.modeReadonly'), hint: t('agent.modeReadonlyHint') },
  { value: 'confirm' as AgentMode, icon: Hand, label: t('agent.modeConfirm'), hint: t('agent.modeConfirmHint') },
  { value: 'auto' as AgentMode, icon: Zap, label: t('agent.modeAuto'), hint: t('agent.modeAutoHint') },
])

const currentMode = computed(() => modeOptions.value.find((m) => m.value === chat.agentMode))

const openMenu = ref<'mode' | null>(null)

function toggleMenu(m: 'mode'): void {
  openMenu.value = openMenu.value === m ? null : m
}

function closeMenu(): void {
  openMenu.value = null
}

function pickMode(value: AgentMode): void {
  chat.setAgentMode(value)
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
  if (!chat.pendingConfirm) return ''
  const text = JSON.stringify(chat.pendingConfirm.args, null, 2)
  return text.length > 600 ? `${text.slice(0, 600)}\n…` : text
})

// ---------- 风格卡片（storyboard_list_styles 结果 → 可点选风格卡） ----------
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
  void chat.send(t('agent.stylePickedMsg', { name: entry.name, id: entry.id }))
}

/** 自定义风格：弹窗输入描述，经 storyboard_set_style 走正路（所有提示词统一带此风格段） */
async function customStyle() {
  try {
    const { value } = await ElMessageBox.prompt(
      t('agent.stylePromptPlaceholder'),
      t('agent.stylePromptTitle'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), inputPattern: /\S/, inputErrorMessage: t('agent.stylePromptEmpty') },
    )
    if (value && value.trim()) void chat.send(t('agent.styleCustomMsg', { text: value.trim() }))
  } catch {
    // 用户取消
  }
}

// ---------- 全局监听：Alt+A 唤出/收起 + Esc 分级退出 + 小态点外收起 ----------
function onGlobalKeydown(e: KeyboardEvent): void {
  if (e.defaultPrevented) return
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.key.toLowerCase() === 'a') {
    e.preventDefault()
    e.stopPropagation()
    chat.toggleAgentDrawer()
    return
  }
  if (e.key === 'Escape' && visible.value) {
    if (openMenu.value || toolsOpen.value) {
      e.preventDefault()
      closeMenu()
      toolsOpen.value = false
      return
    }
    if (isExpanded.value) {
      e.preventDefault()
      applyPreset('small')
    }
  }
}

function onGlobalPointerDown(e: PointerEvent): void {
  if (!visible.value) return
  const target = e.target instanceof Element ? e.target : null
  // 下拉菜单外点关闭（模式胶囊/能力清单；组件内部点击已 stop 不至于此）
  if ((openMenu.value || toolsOpen.value) && (!target || (!target.closest('.agent-menu-anchor') && !target.closest('.cap-anchor')))) {
    closeMenu()
    toolsOpen.value = false
  }
  // 小态点外部收起（页面仍可交互；展开态不收）
  if (!isExpanded.value && (!target || !target.closest('.agent-host-panel'))) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('pointerdown', onGlobalPointerDown)
  // 记忆的几何按当前视口钳位一次（窗口可能变小过）
  if (geom.value) geom.value = clampGeom(geom.value, window.innerWidth, window.innerHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('pointerdown', onGlobalPointerDown)
})

// 首开兜底初始化（init 幂等）+ 模型清单拉取（一次）+ 滚底
let configFetched = false
watch(visible, (open) => {
  if (!open) return
  if (!configFetched) {
    configFetched = true
    void modelsStore.fetchConfig().catch(() => {})
  }
  void chat.init().then(() => nextTick(() => listRef.value?.scrollToBottom()))
})

// 确认卡出现/思考指示/错误行：滚动到底部（消息增长由 ChatMessageList 自锚定）
watch(
  () => [chat.pendingConfirm, chat.thinking, chat.activeError],
  () => {
    if (!visible.value) return
    void listRef.value?.scrollToBottom(true)
  },
)
</script>

<style scoped>
.agent-host-panel {
  position: fixed;
  top: 16px;
  right: 16px;
  bottom: 96px;
  width: 360px;
  display: flex;
  flex-direction: column;
  border: 1px solid transparent;
  border-radius: 12px;
  z-index: 1500;
  overflow: hidden;
  /* 小面板浮层：保持主题 token 的半透明（透过可见页面） */
  background: var(--cb-panel, var(--agnes-bg-elevated, #171a26));
}

/* 展开态（宽度 ≥ 阈值推导，布局完全由几何驱动）：阅读面需不透明底 */
.agent-host-panel.is-expanded {
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

.host-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
  color: var(--agnes-text-secondary);
}

.host-welcome p {
  margin: 0;
  font-size: 13px;
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
.agent-host-panel:not(.is-expanded) .pill-btn.mode-pill {
  width: 32px;
  padding: 0;
  justify-content: center;
}

.agent-host-panel:not(.is-expanded) .pill-btn.mode-pill .pill-text,
.agent-host-panel:not(.is-expanded) .pill-btn.mode-pill .pill-chevron {
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

.cap-anchor {
  position: relative;
  display: inline-flex;
}

.cap-trigger {
  position: relative;
}

.cap-dot {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  font-size: 9px;
  line-height: 14px;
  text-align: center;
  border-radius: 999px;
  background: var(--agnes-primary, #6366f1);
  color: #fff;
}

.cap-dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  right: 0;
  z-index: 30;
  min-width: 240px;
  max-width: 320px;
  max-height: 280px;
  overflow: auto;
  padding: 6px;
  border: 1px solid;
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.14);
}

.cap-dropdown-down {
  bottom: auto;
  top: calc(100% + 6px);
}

.cap-section-title {
  font-size: 10px;
  letter-spacing: 0.05em;
  padding: 5px 6px 3px;
}

.cap-item {
  padding: 5px 6px;
  border-radius: 6px;
}

.cap-item:hover {
  background: rgba(127, 127, 127, 0.12);
}

.cap-item-name {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cap-item-tools {
  font-size: 11px;
  margin-top: 2px;
  word-break: break-all;
}

.mem-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mem-del {
  flex-shrink: 0;
  border: none;
  background: transparent;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}

.mem-clear {
  width: 100%;
  margin-top: 4px;
  padding: 4px 0;
  border: none;
  border-top: 1px solid rgba(127, 127, 127, 0.2);
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}
</style>

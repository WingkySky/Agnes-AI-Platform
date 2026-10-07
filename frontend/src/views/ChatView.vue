<!-- =====================================================
     ChatView.vue — AI 聊天界面
     布局壳 + chat store 接线：消息渲染/输入框/会话侧栏由
     components/chat 共享组件承担（与画布 Agent 面板同一套 UI）。
     行为保持不变：
     - 左侧：会话列表（新建/切换/重命名/AI 总结/删除）
     - 右侧：聊天消息区 + 输入框，流式回复逐字显示
     - 图片/视频生成（工具调用）内嵌展示，媒体任务轮询回填
     - 页面切换后状态保持（keep-alive + 从数据库恢复）
     ===================================================== -->

<template>
  <div class="chat-view">
    <!-- 左侧：会话列表（共享侧栏） -->
    <ChatSessionSidebar
      :title="t('chat.title')"
      :sessions="sessionViews"
      :active-id="chatStore.activeSessionId"
      :extra-commands="extraCommands"
      @select="handleSwitchSession"
      @create="handleNewSession"
      @rename="handleRenamed"
      @delete="handleDeleteSession"
      @extra="handleExtraCommand"
    />

    <!-- 右侧：聊天区 -->
    <main class="chat-main">
      <!-- 无会话时的欢迎页 -->
      <div v-if="!chatStore.hasActiveSession" class="chat-welcome">
        <div class="welcome-icon"><el-icon :size="48"><ChatDotRound /></el-icon></div>
        <h2>{{ t('chat.welcomeTitle') }}</h2>
        <p>{{ t('chat.welcomeDesc') }}</p>
        <div class="welcome-actions">
          <el-button type="primary" @click="handleNewSession">
            {{ t('chat.startChat') }}
          </el-button>
        </div>
        <div class="welcome-tips">
          <div class="tip-item" v-for="tip in quickTips" :key="tip" @click="handleQuickTip(tip)">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ tip }}</span>
          </div>
        </div>
      </div>

      <!-- 聊天区域 -->
      <template v-else>
        <ChatMessageList ref="messageListRef" :items="chatStore.messageItems">
          <template #footer>
            <div v-if="chatStore.activeError" class="chat-error">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ chatStore.activeError }}</span>
            </div>
            <div v-if="chatStore.busy && chatStore.thinking" class="chat-thinking">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ t('agent.thinking') }}</span>
            </div>
            <div v-if="chatStore.loadingMessages" class="chat-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ t('common.loading') }}</span>
            </div>
          </template>
        </ChatMessageList>

        <!-- 输入区（待发附件预览/技能清单/提示行经插槽注入） -->
        <ChatInputBar
          v-model="inputText"
          :sending="chatStore.busy"
          :placeholder="t('chat.inputPlaceholder')"
          :has-attachments="pendingAttachments.length > 0"
          accept="image/*"
          :paste-images="false"
          @keydown="onDraftKeydown"
          @send="handleSend"
          @pick-files="onFilesPicked"
        >
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
          <template #trail>
            <ChatModelPill
              :model-id="chatStore.chatModelId || modelsStore.getDefaultModel('chat')"
              :models="modelsStore.chatModels"
              @select="(id: string) => chatStore.setChatModel(id)"
            />
          </template>
          <template #hint>
            <p class="input-hint">{{ t('chat.enterHint') }}</p>
          </template>
        </ChatInputBar>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
// 组件名称（供 keep-alive 缓存识别）
defineOptions({ name: 'ChatView' })

import { ref, onMounted, onActivated, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loading, ChatDotRound, WarningFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useChatStore } from '@/stores/chat'
import { getPreset } from '@/api/presets'
import { ElMessage } from 'element-plus'
import { useConfirm } from '@/composables/useConfirm'
import ChatSessionSidebar from '@/components/chat/ChatSessionSidebar.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import ChatSkillMenu from '@/components/chat/ChatSkillMenu.vue'
import ChatModelPill from '@/components/chat/ChatModelPill.vue'
import ChatPendingAttachments from '@/components/chat/ChatPendingAttachments.vue'
import { useChatComposer } from '@/composables/useChatComposer'
import { useModelsStore } from '@/stores/models'
import type { ChatSessionView, ChatSessionCommand } from '@/components/chat/types'

const { t } = useI18n()
const { confirm } = useConfirm()
const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const modelsStore = useModelsStore()

// 消息列表组件引用（keep-alive 切回时滚底）
const messageListRef = ref<InstanceType<typeof ChatMessageList> | null>(null)

// 输入链路收口在共享组合式（附件/发送/"/" 技能）；全局粘贴互斥：抽屉开着只收抽屉的
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
} = useChatComposer({ enabled: () => route.path === '/chat' && !chatStore.agentDrawerOpen })

// 会话列表视图（共享侧栏数据；画布会话带角标）
const sessionViews = computed<ChatSessionView[]>(() =>
  chatStore.sessions.map((s) => ({
    id: s.id,
    title: s.title,
    updatedAt: s.updated_at,
    canvas: s.session_type === 'canvas',
    generating: chatStore.isRunning(s.id),
  })),
)

// 三点菜单扩展命令：AI 总结标题
const extraCommands = computed<ChatSessionCommand[]>(() => [
  { command: 'summarize', label: t('chat.autoSummarize') },
])

// 快捷提示
const quickTips = computed(() => [
  t('chat.tipImage'),
  t('chat.tipVideo'),
  t('chat.tipChat'),
])

// =====================================================
// 生命周期
// =====================================================
onMounted(async () => {
  // 使用 init() 初始化（从 localStorage 恢复 + 从数据库加载消息）
  await chatStore.init()
  // 预设中心跳转调用：?applyPreset=<id> 触发，加载预设内容填入输入框并缓存 presetId
  await loadPresetFromQuery()
})

/** 从路由 query 读取 applyPreset，加载预设并填充输入框（预设内容随消息发送，无需透传 ID） */
async function loadPresetFromQuery() {
  const presetIdStr = route.query.applyPreset as string | undefined
  if (!presetIdStr) return
  const presetId = Number(presetIdStr)
  if (!Number.isFinite(presetId) || presetId <= 0) return
  try {
    const preset = await getPreset(presetId)
    if (preset.prompt_text) {
      inputText.value = preset.prompt_text
    }
    ElMessage.success(t('presets.applied'))
  } catch (e: unknown) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('presets.applyFailed'))
  }
}

onActivated(() => {
  void messageListRef.value?.scrollToBottom()
})

// =====================================================
// 会话交互（数据动作在 chat store，此处只接线与提示）
// =====================================================

/** 新建会话 */
async function handleNewSession() {
  try {
    await chatStore.newSession()
  } catch {
    ElMessage.error(t('chat.createFailed'))
  }
}

/** 切换会话（画布会话改跳转画布续聊：Agent 内核依赖画布上下文，对话页内无法驱动） */
async function handleSwitchSession(sessionId: number | string) {
  if (typeof sessionId !== 'number') return
  const session = chatStore.sessions.find((s) => s.id === sessionId)
  if (session?.session_type === 'canvas') {
    void router.push({
      path: '/canvas',
      query: { workspace: session.workspace_id || '', session: String(session.id) },
    })
    return
  }
  if (sessionId === chatStore.activeSessionId) return
  try {
    await chatStore.switchSession(sessionId)
  } catch {
    ElMessage.error(t('chat.switchFailed'))
  }
}

/** 删除会话（会话若在生成中，store 会先终止其内核再删） */
async function handleDeleteSession(sessionId: number | string) {
  if (typeof sessionId !== 'number') return
  try {
    await confirm(t('chat.confirmDelete'), t('common.confirm'))
    await chatStore.removeSession(sessionId)
    ElMessage.success(t('chat.deleted'))
  } catch {
    // 取消删除
  }
}

/** 重命名会话（共享侧栏对话框回传） */
async function handleRenamed(sessionId: number | string, title: string) {
  if (typeof sessionId !== 'number' || !title) return
  try {
    await chatStore.updateSessionTitle(sessionId, title)
    ElMessage.success(t('chat.renameSuccess'))
  } catch (e: unknown) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('chat.renameFailed'))
  }
}

/** 三点菜单扩展命令（当前仅 AI 总结标题） */
function handleExtraCommand(sessionId: number | string, command: string) {
  if (command === 'summarize' && typeof sessionId === 'number') {
    void handleAutoSummarize(sessionId)
  }
}

/** AI 自动总结会话标题 */
async function handleAutoSummarize(sessionId: number) {
  try {
    ElMessage.info(t('chat.summarizing'))
    const updated = await chatStore.autoSummarizeSession(sessionId)
    ElMessage.success(t('chat.summarizeSuccess') + ': ' + updated.title)
  } catch (e: unknown) {
    ElMessage.error((e instanceof Error ? e.message : '') || t('chat.summarizeFailed'))
  }
}

// =====================================================
// 发送与附件（输入链路收口在 useChatComposer）
// =====================================================

/** 快捷提示点击 */
async function handleQuickTip(tip: string) {
  if (!chatStore.hasActiveSession) {
    await chatStore.newSession()
  }
  inputText.value = tip
  handleSend()
}
</script>

<style scoped>
/* =====================================================
 * 聊天界面布局壳样式（消息/输入/侧栏样式在共享组件内）
 * ===================================================== */

.chat-view {
  display: flex;
  height: calc(100vh - 160px);
  min-height: 500px;
  gap: 0;
  background: var(--agnes-bg-inset);
  border-radius: 16px;
  border: 1px solid rgba(100, 150, 220, 0.15);
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

/* ---- 欢迎页 ---- */
.chat-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
}

.welcome-icon {
  font-size: 56px;
  margin-bottom: 20px;
  filter: drop-shadow(0 0 20px rgba(120, 180, 255, 0.4));
  color: var(--agnes-primary-soft);
}

.chat-welcome h2 {
  font-size: 22px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0 0 8px;
}

.chat-welcome p {
  color: var(--agnes-text-muted);
  font-size: 14px;
  margin: 0 0 24px;
  max-width: 400px;
}

.welcome-actions {
  margin-bottom: 32px;
}

.welcome-tips {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 400px;
  width: 100%;
}

.tip-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--agnes-bg-hover);
  border: 1px solid rgba(100, 150, 220, 0.15);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--agnes-text-secondary);
  font-size: 13px;
  text-align: left;
}

.tip-item:hover {
  background: var(--agnes-nav-hover-bg);
  border-color: var(--agnes-border-strong);
  color: var(--agnes-text-primary);
}

/* 加载中 */
.chat-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--agnes-text-muted);
  font-size: 13px;
  padding: 16px;
  justify-content: center;
}

.chat-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-danger, #f56c6c);
  font-size: 13px;
  padding: 12px 16px;
  justify-content: center;
}

.chat-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--agnes-text-muted);
  font-size: 13px;
  padding: 16px;
  justify-content: center;
}

/* --- 待发送附件预览（输入条插槽内容） --- */
.input-hint {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--agnes-text-faint);
}
</style>

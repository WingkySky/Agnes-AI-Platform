<template>
  <el-drawer
    v-model="visible"
    direction="rtl"
    size="440px"
    :with-header="false"
    :append-to-body="false"
    class="agent-drawer"
  >
    <div class="agent-drawer-body">
      <header class="drawer-header">
        <el-icon class="drawer-brand"><ChatDotRound /></el-icon>
        <span class="drawer-title">{{ t('agent.drawerTitle') }}</span>
        <el-select
          v-if="chatStore.sessions.length > 0"
          class="session-select"
          :model-value="chatStore.activeSessionId"
          :placeholder="t('agent.drawerSelectSession')"
          size="small"
          @change="handleSwitchSession"
        >
          <el-option
            v-for="s in sessionOptions"
            :key="s.id"
            :label="s.label"
            :value="s.id"
          />
        </el-select>
        <el-button circle text :icon="Plus" :title="t('agent.drawerNew')" @click="handleNewSession" />
        <el-button circle text :icon="Close" :title="t('common.close')" @click="close" />
      </header>

      <!-- 无会话时的迷你欢迎页 -->
      <div v-if="!chatStore.hasActiveSession" class="drawer-welcome">
        <el-icon :size="36"><ChatDotRound /></el-icon>
        <p>{{ t('chat.welcomeDesc') }}</p>
        <el-button type="primary" @click="handleNewSession">{{ t('chat.startChat') }}</el-button>
      </div>

      <!-- 聊天区域（与对话页同一 store：消息/流式/确认卡全量同源） -->
      <template v-else>
        <ChatMessageList ref="messageListRef" :items="chatStore.messageItems">
          <template #footer>
            <div v-if="chatStore.activeError" class="drawer-hint is-error">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ chatStore.activeError }}</span>
            </div>
            <div v-if="chatStore.busy && chatStore.thinking" class="drawer-hint">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ t('agent.thinking') }}</span>
            </div>
          </template>
        </ChatMessageList>

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
        </ChatInputBar>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
/* =====================================================
 * AgentDrawer — 全局侧边抽屉（Agent 一级公民）
 * 任意页面经顶栏按钮 / Alt+A 唤出；组合共享聊天组件，
 * 绑定与对话页同一 chat store（会话/消息/内核全量同源）。
 * 开关态收敛在 chat store（ChatView 粘贴互斥守卫也读它）。
 * ===================================================== */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Close, Loading, Plus, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useChatStore } from '@/stores/chat'
import { useModelsStore } from '@/stores/models'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import ChatSkillMenu from '@/components/chat/ChatSkillMenu.vue'
import ChatModelPill from '@/components/chat/ChatModelPill.vue'
import ChatPendingAttachments from '@/components/chat/ChatPendingAttachments.vue'
import { useChatComposer } from '@/composables/useChatComposer'

const { t } = useI18n()
const router = useRouter()
const chatStore = useChatStore()
const modelsStore = useModelsStore()

const visible = computed({
  get: () => chatStore.agentDrawerOpen,
  set: (open: boolean) => chatStore.setAgentDrawerOpen(open),
})

// 输入链路收口在共享组合式；全局粘贴互斥：抽屉开着只收抽屉的
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
} = useChatComposer({ enabled: () => chatStore.agentDrawerOpen })

const messageListRef = ref<InstanceType<typeof ChatMessageList> | null>(null)

const sessionOptions = computed(() =>
  chatStore.sessions.map((s) => ({
    id: s.id,
    label: s.session_type === 'canvas' ? `${s.title}（${t('agent.drawerCanvasTag')}）` : s.title,
  })),
)

// 首开兜底初始化（init 幂等）+ 滚底
watch(visible, (open) => {
  if (!open) return
  void chatStore.init().then(() => nextTick(() => messageListRef.value?.scrollToBottom()))
})

function close() {
  chatStore.setAgentDrawerOpen(false)
}

/** 新建会话 */
async function handleNewSession() {
  try {
    await chatStore.newSession()
  } catch {
    ElMessage.error(t('chat.createFailed'))
  }
}

/** 切换会话（画布会话跳画布续聊：内核依赖画布上下文，同对话页规则） */
async function handleSwitchSession(sessionId: number) {
  const session = chatStore.sessions.find((s) => s.id === sessionId)
  if (session?.session_type === 'canvas') {
    close()
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

/** 全局快捷键 Alt+A 唤出/收起（输入框聚焦同样生效；Option 组合无字符插入风险） */
function onGlobalKeydown(e: KeyboardEvent) {
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.key.toLowerCase() === 'a') {
    e.preventDefault()
    e.stopPropagation()
    chatStore.toggleAgentDrawer()
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<style scoped>
.agent-drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--agnes-border);
  flex-shrink: 0;
}

.drawer-brand {
  color: var(--agnes-primary);
}

.drawer-title {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
}

.session-select {
  flex: 1;
  min-width: 0;
}

.drawer-welcome {
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

.drawer-welcome p {
  margin: 0;
  font-size: 13px;
}

.drawer-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
}

.drawer-hint.is-error {
  color: var(--el-color-danger);
}

/* 抽屉内容贴边（append-to-body=false，scoped :deep 可达；默认 body 有内边距） */
:deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}
</style>

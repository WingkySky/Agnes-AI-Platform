<!--
  ChatSessionSidebar.vue — 共享会话列表侧栏（components/chat）

  数据与动作全部外部传入：sessions/activeId 由宿主给，
  select/create/rename/delete/extra 事件回传宿主 store。
  重命名对话框内聚；三点菜单支持宿主扩展命令（如「AI 总结标题」）。
-->
<template>
  <aside class="cb-sidebar">
    <div class="cb-sidebar-header">
      <h3>{{ title }}</h3>
      <el-button type="primary" size="small" :icon="Plus" circle @click="emit('create')" />
    </div>

    <div class="cb-sidebar-list">
      <div
        v-for="s in sessions"
        :key="s.id"
        class="cb-session"
        :class="{ active: s.id === activeId }"
        @click="emit('select', s.id)"
      >
        <div class="cb-session-info">
          <span class="cb-session-title" :title="s.title || t('chat.newChat')">
            <Cpu v-if="s.canvas" class="cb-session-canvas-tag" :title="t('chat.canvasSession')" />
            {{ s.title || t('chat.newChat') }}
          </span>
          <span class="cb-session-time">{{ formatTime(s.updatedAt) }}</span>
        </div>
        <div class="cb-session-actions" @click.stop>
          <el-dropdown trigger="click" @command="(cmd: string | number | object) => onCommand(String(cmd), s)">
            <button type="button" class="cb-session-menu" :title="t('chat.moreActions')">
              <el-icon :size="14"><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="x in extraCommands"
                  :key="x.command"
                  :command="x.command"
                >{{ x.label }}</el-dropdown-item>
                <el-dropdown-item :icon="Edit" command="__rename">{{ t('chat.renameSession') }}</el-dropdown-item>
                <el-dropdown-item :icon="Delete" command="__delete" divided>{{ t('chat.deleteSession') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div v-if="sessions.length === 0" class="cb-sidebar-empty">
        <p>{{ t('chat.noSessions') }}</p>
      </div>
    </div>

    <!-- 重命名对话框 -->
    <el-dialog
      v-model="renameVisible"
      :title="t('chat.renameSession')"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-input
        v-model="renameInput"
        :placeholder="t('chat.enterNewTitle')"
        maxlength="200"
        show-word-limit
        @keyup.enter="confirmRename"
      />
      <template #footer>
        <el-button @click="renameVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!renameInput.trim()" @click="confirmRename">
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Plus, Edit, Delete, MoreFilled, Cpu } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { ChatSessionView, ChatSessionCommand } from './types'

withDefaults(defineProps<{
  title: string
  sessions: ChatSessionView[]
  activeId: number | string | null
  /** 三点菜单里的宿主扩展命令（排在重命名之前） */
  extraCommands?: ChatSessionCommand[]
}>(), { extraCommands: () => [] })

const emit = defineEmits<{
  (e: 'select', id: number | string): void
  (e: 'create'): void
  (e: 'rename', id: number | string, title: string): void
  (e: 'delete', id: number | string): void
  (e: 'extra', id: number | string, command: string): void
}>()

const { t } = useI18n()

// 重命名对话框状态
const renameVisible = ref(false)
const renameInput = ref('')
const renamingId = ref<number | string | null>(null)

function onCommand(cmd: string, s: ChatSessionView): void {
  if (cmd === '__rename') {
    renamingId.value = s.id
    renameInput.value = s.title || ''
    renameVisible.value = true
    return
  }
  if (cmd === '__delete') {
    emit('delete', s.id)
    return
  }
  emit('extra', s.id, cmd)
}

function confirmRename(): void {
  const title = renameInput.value.trim()
  if (!title || renamingId.value === null) return
  emit('rename', renamingId.value, title)
  renameVisible.value = false
}

/** 时间显示：当天给时分，否则给月日 */
function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.cb-sidebar {
  width: 240px;
  min-width: 240px;
  background: var(--cb-sidebar-bg, var(--agnes-bg-elevated, #171a26));
  border-right: 1px solid var(--cb-sidebar-border, rgba(100, 150, 220, 0.12));
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cb-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--cb-sidebar-border, var(--agnes-border-faint, rgba(100, 150, 220, 0.1)));
}

.cb-sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--cb-text-secondary, var(--agnes-text-secondary, #aab2c5));
}

.cb-sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  min-height: 0;
}

.cb-session {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 2px;
}

.cb-session:hover {
  background: var(--cb-item-hover, var(--agnes-nav-hover-bg, #1e2334));
}

.cb-session.active {
  background: var(--cb-item-active, var(--agnes-nav-active-bg, #232946));
  border: 1px solid var(--cb-item-active-border, rgba(100, 150, 220, 0.2));
}

.cb-session-info {
  flex: 1;
  min-width: 0;
}

.cb-session-title {
  display: block;
  font-size: 13px;
  color: var(--cb-text-secondary, var(--agnes-text-secondary, #aab2c5));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-session-canvas-tag {
  /* element-plus 图标无内在尺寸（size prop 无效），必须显式定宽高 */
  width: 11px;
  height: 11px;
  color: var(--agnes-primary, #4d80f0);
  vertical-align: -1px;
  margin-right: 3px;
}

.cb-session-time {
  display: block;
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
  margin-top: 2px;
}

.cb-session-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
  flex-shrink: 0;
  margin-left: 8px;
}

.cb-session:hover .cb-session-actions {
  opacity: 1;
}

.cb-session-menu {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--cb-muted, var(--agnes-text-muted, #8b93a8));
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  padding: 0;
}

.cb-session-menu:hover {
  background: var(--agnes-info-bg, rgba(80, 140, 255, 0.12));
  color: var(--agnes-primary, #4d80f0);
}

.cb-sidebar-empty {
  text-align: center;
  padding: 32px 12px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
  font-size: 12px;
}
</style>

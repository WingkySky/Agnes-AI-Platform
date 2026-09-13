<!--
  ChatMessageBubble.vue — 共享消息气泡（components/chat）

  两种形态：
  - 默认：全局对话页样式（头像 + 内容卡，深浅由全局 --agnes-* 决定）
  - dense：画布 Agent 面板样式（无头像、紧凑，配色经宿主注入的 --cb-* 覆盖）
  数据只来自 ChatBubbleItem 视图模型；领域化内容（风格卡片等）经 #step-extra 插槽注入
-->
<template>
  <div class="cb-item" :class="[`is-${item.role}`, { 'is-dense': dense }]">
    <div v-if="!dense" class="cb-avatar" :class="item.role">
      <el-icon :size="18">
        <User v-if="item.role === 'user'" />
        <Monitor v-else />
      </el-icon>
    </div>

    <div class="cb-main">
      <div class="cb-bubble">
        <!-- ===== 用户消息 ===== -->
        <template v-if="item.role === 'user'">
          <!-- 附件卡（视频块 / 文档卡 / 图片缩略，对话页 URL 识别附件） -->
          <div v-if="item.attachments?.length" class="cb-attachments">
            <template v-for="(att, idx) in item.attachments" :key="'att-' + idx">
              <video
                v-if="att.kind === 'video'"
                :src="att.url"
                controls
                preload="metadata"
                class="cb-att-video"
              />
              <a
                v-else-if="att.kind === 'document'"
                :href="att.url"
                target="_blank"
                rel="noopener noreferrer"
                class="cb-att-doc"
              >
                <el-icon :size="22"><Document /></el-icon>
                <span class="cb-att-doc-name">{{ att.name }}</span>
              </a>
              <el-image
                v-else
                :src="att.url"
                :preview-src-list="attachmentImageUrls"
                :initial-index="attachmentImageIndex(idx)"
                fit="cover"
                class="cb-att-thumb"
                :preview-teleported="true"
              >
                <template #error>
                  <div class="cb-att-thumb-fallback"><el-icon><WarningFilled /></el-icon></div>
                </template>
              </el-image>
            </template>
          </div>
          <!-- 附图缩略（画布 Agent base64 图，点击预览） -->
          <div v-if="item.images?.length" class="cb-images">
            <el-image
              v-for="(img, idx) in item.images"
              :key="'img-' + idx"
              class="cb-image-thumb"
              :src="img.src"
              :preview-src-list="item.images.map((i) => i.src)"
              :initial-index="idx"
              :hide-on-click-modal="true"
              fit="cover"
              preview-teleported
            />
          </div>
          <p v-if="item.content.trim()" class="cb-text">{{ item.content }}</p>
        </template>

        <!-- ===== assistant 消息 ===== -->
        <template v-else>
          <div v-if="item.content.trim()" class="cb-md" v-html="html"></div>
          <span v-if="item.streaming" class="cb-cursor">▊</span>

          <!-- 工具步骤时间线（领域渲染经 #step-extra 注入） -->
          <div v-if="item.steps?.length" class="cb-steps">
            <template v-for="step in item.steps" :key="step.callId">
              <div class="cb-step" :title="step.tooltip">
                <el-icon v-if="step.status === 'running' || step.status === 'pending'" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="step.status === 'done'" class="cb-step-done"><CircleCheck /></el-icon>
                <el-icon v-else-if="step.status === 'error'" class="cb-step-error"><CircleClose /></el-icon>
                <el-icon v-else class="cb-step-rejected"><Remove /></el-icon>
                <span class="cb-step-label">{{ step.label }}</span>
                <span class="cb-step-status">{{ statusText(step.status) }}</span>
              </div>
              <div v-if="step.progress" class="cb-step-progress">{{ step.progress }}</div>
              <slot name="step-extra" :step="step" />
            </template>
          </div>

          <!-- 生成产物媒体（多图/多视频，三态） -->
          <template v-if="item.media?.length">
            <div v-for="(m, idx) in item.media" :key="m.taskId || 'media-' + idx" class="cb-media">
              <template v-if="m.type === 'image'">
                <el-image
                  v-if="m.url && m.status === 'success'"
                  :src="m.url"
                  :preview-src-list="mediaImageUrls"
                  :initial-index="mediaImageIndex(idx)"
                  fit="contain"
                  class="cb-media-image"
                  :preview-teleported="true"
                >
                  <template #error>
                    <div class="cb-media-state"><el-icon class="is-loading"><Loading /></el-icon><span>{{ t('chat.mediaLoading') }}</span></div>
                  </template>
                </el-image>
                <div v-else-if="m.status === 'pending' || m.status === 'processing'" class="cb-media-state is-active">
                  <el-icon class="is-loading"><Loading /></el-icon><span>{{ t('chat.imageGenerating') }}</span>
                </div>
                <div v-else-if="m.status === 'failed'" class="cb-media-state is-failed">
                  <el-icon><WarningFilled /></el-icon><span>{{ t('chat.mediaFailed') }}</span>
                </div>
              </template>
              <template v-else>
                <video v-if="m.url && m.status === 'success'" :src="m.url" controls class="cb-media-video">
                  {{ t('chat.videoNotSupported') }}
                </video>
                <div v-else-if="m.status === 'pending' || m.status === 'processing'" class="cb-media-state is-active">
                  <el-icon class="is-loading"><Loading /></el-icon><span>{{ t('chat.videoGenerating') }}</span>
                </div>
                <div v-else-if="m.status === 'failed'" class="cb-media-state is-failed">
                  <el-icon><WarningFilled /></el-icon><span>{{ t('chat.mediaFailed') }}</span>
                </div>
              </template>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { User, Monitor, Document, WarningFilled, Loading, CircleCheck, CircleClose, Remove } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { renderMarkdown } from './markdown'
import type { ChatBubbleItem, ChatStepView } from './types'

const props = withDefaults(defineProps<{
  item: ChatBubbleItem
  /** 紧凑形态（画布面板）：无头像、小字号、配色走宿主 --cb-* 变量 */
  dense?: boolean
}>(), { dense: false })

const { t } = useI18n()

const html = computed(() => (props.item.role === 'assistant' ? renderMarkdown(props.item.content) : ''))

function statusText(status: ChatStepView['status']): string {
  const map: Record<ChatStepView['status'], string> = {
    pending: t('chat.stepWaiting'),
    running: t('chat.stepRunning'),
    done: t('chat.stepDone'),
    error: t('chat.stepFailed'),
    rejected: t('chat.stepRejected'),
  }
  return map[status]
}

/** 附件卡中的图片预览列表与当前索引（跳过视频/文档卡） */
const attachmentImageUrls = computed(() =>
  (props.item.attachments ?? []).filter((a) => a.kind === 'image').map((a) => a.url),
)

function attachmentImageIndex(currentIdx: number): number {
  const atts = props.item.attachments ?? []
  let imageIdx = 0
  for (let i = 0; i < currentIdx; i++) {
    if (atts[i]?.kind === 'image') imageIdx++
  }
  return imageIdx
}

/** 生成媒体中的图片预览列表与当前索引 */
const mediaImageUrls = computed(() =>
  (props.item.media ?? []).filter((m) => m.type === 'image' && m.url && m.status === 'success').map((m) => m.url),
)

function mediaImageIndex(currentIdx: number): number {
  const media = props.item.media ?? []
  const current = media[currentIdx]
  const idx = mediaImageUrls.value.indexOf(current.url)
  return idx >= 0 ? idx : 0
}
</script>

<style scoped>
.cb-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  max-width: 85%;
}

.cb-item.is-user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.cb-item.is-assistant {
  align-self: flex-start;
}

.cb-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.is-user .cb-main {
  align-items: flex-end;
}

/* ---- 头像（默认形态） ---- */
.cb-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cb-avatar.user {
  background: linear-gradient(135deg, var(--agnes-primary, #4d80f0) 0%, var(--agnes-accent, #8a63e8) 100%);
  color: var(--agnes-text-primary, #e6e9f2);
}

.cb-avatar.assistant {
  background: var(--agnes-bg-elevated, #171a26);
  color: var(--agnes-primary-soft, #7ea2f5);
  border: 1px solid var(--agnes-border, rgba(100, 150, 220, 0.18));
}

/* ---- 气泡容器 ---- */
.cb-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  background: var(--cb-ai-bg, var(--agnes-bg-hover, #1c2030));
  color: var(--cb-ai-text, var(--agnes-text-primary, #e6e9f2));
  border: 1px solid var(--cb-ai-border, var(--agnes-border-faint, rgba(100, 150, 220, 0.1)));
}

.is-user .cb-bubble {
  background: var(--cb-user-bg, var(--agnes-nav-active-bg, #232946));
  color: var(--cb-user-text, var(--agnes-text-primary, #e6e9f2));
  border: 1px solid var(--cb-user-border, rgba(100, 150, 220, 0.2));
}

.cb-text {
  margin: 0;
  white-space: pre-wrap;
}

/* ---- markdown（assistant） ---- */
.cb-md {
  white-space: normal;
}

.cb-md :deep(p) {
  margin: 0 0 6px;
}

.cb-md :deep(p:last-child) {
  margin-bottom: 0;
}

.cb-md :deep(code) {
  background: var(--agnes-info-bg, rgba(80, 140, 255, 0.12));
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--agnes-primary, #4d80f0);
}

.cb-md :deep(pre) {
  background: var(--agnes-bg-elevated, #171a26);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.cb-md :deep(pre code) {
  background: none;
  padding: 0;
}

.cb-md :deep(ul),
.cb-md :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.cb-md :deep(a) {
  color: var(--agnes-primary, #4d80f0);
}

.cb-md :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}

.cb-md :deep(th),
.cb-md :deep(td) {
  border: 1px solid var(--agnes-border, rgba(100, 150, 220, 0.18));
  padding: 4px 8px;
}

/* ---- 流式光标 ---- */
.cb-cursor {
  display: inline-block;
  animation: cb-blink 1s infinite;
  color: var(--agnes-primary, #4d80f0);
  font-size: 14px;
  margin-left: 2px;
}

@keyframes cb-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ---- 工具步骤时间线 ---- */
.cb-steps {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 6px;
}

.is-dense .cb-steps {
  margin-top: 2px;
}

.cb-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--cb-muted, var(--agnes-text-muted, #8b93a8));
}

.cb-step-progress {
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-muted, #8b93a8));
  padding-left: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-step .el-icon {
  flex-shrink: 0;
}

.cb-step-done {
  color: var(--agnes-success, #4ade80);
}

.cb-step-error {
  color: var(--agnes-error, #f87171);
}

.cb-step-rejected {
  color: var(--agnes-text-faint, #5c6478);
}

.cb-step-status {
  opacity: 0.8;
}

/* ---- 用户附图 ---- */
.cb-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cb-image-thumb {
  width: 88px;
  height: 88px;
  border-radius: 8px;
  overflow: hidden;
}

/* ---- 用户附件卡 ---- */
.cb-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

.cb-att-thumb {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--agnes-border-strong, rgba(100, 150, 220, 0.3));
}

.cb-att-thumb-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-error-bg, rgba(248, 113, 113, 0.12));
  color: var(--agnes-error, #f87171);
}

.cb-att-video {
  max-width: 280px;
  max-height: 200px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border-strong, rgba(100, 150, 220, 0.3));
  background: var(--agnes-bg-dark-surface, #10131c);
  display: block;
}

.cb-att-doc {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--agnes-nav-hover-bg, #1e2334);
  border: 1px solid var(--agnes-border, rgba(100, 150, 220, 0.18));
  border-radius: 8px;
  color: var(--agnes-text-secondary, #aab2c5);
  text-decoration: none;
  font-size: 13px;
  transition: all 0.2s ease;
  max-width: 280px;
}

.cb-att-doc:hover {
  background: var(--agnes-nav-active-bg, #232946);
}

.cb-att-doc-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--agnes-primary, #4d80f0);
}

/* ---- 生成媒体 ---- */
.cb-media {
  margin-top: 10px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(100, 150, 220, 0.15);
}

.is-dense .cb-media {
  border: none;
}

.cb-media-image {
  max-width: 400px;
  max-height: 400px;
  display: block;
}

.cb-media-video {
  max-width: 480px;
  max-height: 360px;
  display: block;
}

.cb-media-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: var(--cb-muted, var(--agnes-text-muted, #8b93a8));
  font-size: 13px;
}

.cb-media-state.is-active {
  color: var(--agnes-primary, #4d80f0);
}

.cb-media-state.is-failed {
  color: var(--agnes-error, #f87171);
}

/* ---- dense 形态（画布面板）：去头像、缩内边距、正文自持气泡底 ---- */
.is-dense {
  max-width: 88%;
}

.is-dense .cb-bubble {
  padding: 0;
  border: none;
  background: transparent;
  font-size: 13px;
}

.is-dense .cb-text,
.is-dense .cb-md {
  background: var(--cb-ai-bg, var(--agnes-bg-hover, #1c2030));
  color: var(--cb-ai-text, var(--agnes-text-primary, #e6e9f2));
  border-radius: 10px;
  padding: 7px 10px;
}

.is-dense.is-user .cb-text {
  background: var(--cb-user-bg, var(--agnes-nav-active-bg, #232946));
  color: var(--cb-user-text, var(--agnes-text-primary, #e6e9f2));
}

.is-dense .cb-step {
  font-size: 11px;
  padding-left: 2px;
}

.is-dense .cb-media-state {
  padding: 8px 0;
}
</style>

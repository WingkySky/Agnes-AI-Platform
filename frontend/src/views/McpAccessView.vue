<!-- =====================================================
     MCP 接入页
     - 把平台画布/剪辑器/生成能力以 MCP Server 形态开放给外部 Agent
     - PAT 令牌管理（自个人资料页迁入）：清单/新建/一次性明文/吊销
     - 复制即用指引：配置文件 / 命令行 / 发给 Agent，全部嵌入真实令牌
     - 工具面简介：16 个工具分组摘要
     ===================================================== -->

<template>
  <div class="mcp-access-page">
    <header class="page-header">
      <h2 class="page-title">
        <el-icon><Connection /></el-icon>
        {{ t('mcpAccess.title') }}
      </h2>
      <p class="page-subtitle">{{ t('mcpAccess.subtitle') }}</p>
    </header>

    <!-- ============ API 访问令牌 ============ -->
    <section class="mcp-card">
      <div class="pat-header">
        <h3 class="card-title">{{ t('profile.patSection') }}</h3>
        <div class="pat-header-actions">
          <el-button size="small" @click="guideVisible = true">
            <el-icon><Guide /></el-icon>
            {{ t('profile.patGuide') }}
          </el-button>
          <el-button type="primary" size="small" @click="patDialogVisible = true">
            <el-icon><Plus /></el-icon>
            {{ t('profile.patNew') }}
          </el-button>
        </div>
      </div>
      <p class="pat-subtitle">{{ t('profile.patSubtitle') }}</p>

      <el-table :data="pats" size="small" class="pat-table">
        <el-table-column prop="name" :label="t('profile.patColName')" min-width="140" show-overflow-tooltip />
        <el-table-column :label="t('profile.patColPermission')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.permission === 'full' ? 'warning' : 'info'" effect="plain" size="small">
              {{ row.permission === 'full' ? t('profile.patPermissionFull') : t('profile.patPermissionReadonly') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('profile.patColCreatedAt')" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at, { emptyText: '-' }) }}</template>
        </el-table-column>
        <el-table-column :label="t('profile.patColLastUsed')" width="170">
          <template #default="{ row }">{{ row.last_used_at ? formatTime(row.last_used_at, { emptyText: t('profile.patNever') }) : t('profile.patNever') }}</template>
        </el-table-column>
        <el-table-column :label="t('profile.patColStatus')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.revoked_at ? 'danger' : 'success'" effect="plain" size="small">
              {{ row.revoked_at ? t('profile.patStatusRevoked') : t('profile.patStatusActive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="80" align="right">
          <template #default="{ row }">
            <el-button v-if="!row.revoked_at" link type="danger" size="small" @click="handleRevokePat(row)">
              {{ t('profile.patRevoke') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新建弹窗：创建后展示一次性明文 + 复制即用接入配置 -->
      <el-dialog v-model="patDialogVisible" :title="t('profile.patCreateTitle')" width="560px" @closed="resetPatDialog">
        <template v-if="!createdToken">
          <el-form label-position="top">
            <el-form-item :label="t('profile.patNameLabel')">
              <el-input v-model="patName" :placeholder="t('profile.patNamePlaceholder')" maxlength="100" />
            </el-form-item>
            <el-form-item :label="t('profile.patPermissionLabel')">
              <el-radio-group v-model="patPermission">
                <el-radio value="readonly">{{ t('profile.patPermissionReadonly') }}</el-radio>
                <el-radio value="full">{{ t('profile.patPermissionFull') }}</el-radio>
              </el-radio-group>
              <p class="form-hint">{{ patPermission === 'full' ? t('profile.patPermissionFullHint') : t('profile.patPermissionReadonlyHint') }}</p>
            </el-form-item>
          </el-form>
        </template>
        <template v-else>
          <el-alert
            type="warning"
            :title="t('profile.patCreateSuccess')"
            :description="t('profile.patTokenOnce')"
            show-icon
            :closable="false"
            class="pat-token-alert"
          />
          <div class="pat-token-row">
            <code class="pat-token">{{ createdToken }}</code>
            <el-button size="small" @click="copyCreatedToken">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopy') }}
            </el-button>
          </div>
          <el-divider class="pat-divider" />
          <p class="pat-config-hint">{{ t('profile.patConfigHint') }}</p>
          <el-tabs v-model="guideTab" class="pat-guide-tabs">
            <el-tab-pane :label="t('profile.patGuideTabConfig')" name="config">
              <div class="pat-token-row">
                <code class="pat-token pat-token-tall pat-token-block">{{ liveConfig }}</code>
                <el-button size="small" type="primary" @click="copyLiveConfig">
                  <el-icon><CopyDocument /></el-icon>
                  {{ t('profile.patCopyConfig') }}
                </el-button>
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('profile.patGuideTabCli')" name="cli">
              <p class="pat-guide-hint">{{ t('profile.patCliHint') }}</p>
              <div class="pat-token-row">
                <code class="pat-token pat-token-tall pat-token-block">{{ liveCli }}</code>
                <el-button size="small" type="primary" @click="copyLiveCli">
                  <el-icon><CopyDocument /></el-icon>
                  {{ t('profile.patCopy') }}
                </el-button>
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('profile.patGuideTabPrompt')" name="prompt">
              <p class="pat-guide-hint">{{ t('profile.patPromptHint') }}</p>
              <div class="pat-token-row">
                <code class="pat-token pat-token-tall pat-token-block">{{ livePrompt }}</code>
                <el-button size="small" type="primary" @click="copyLivePrompt">
                  <el-icon><CopyDocument /></el-icon>
                  {{ t('profile.patCopyPrompt') }}
                </el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
        </template>
        <template #footer>
          <el-button @click="patDialogVisible = false">{{ t('common.close') }}</el-button>
          <el-button v-if="!createdToken" type="primary" :loading="patCreating" @click="handleCreatePat">
            {{ t('profile.patCreate') }}
          </el-button>
        </template>
      </el-dialog>

      <!-- 接入指引弹窗：无可用明文时先一键创建并填入，所有复制项嵌入真实令牌 -->
      <el-dialog v-model="guideVisible" :title="t('profile.patGuideTitle')" width="560px">
        <el-alert
          v-if="hasLiveToken"
          type="success"
          :title="t('profile.patGuideHasToken')"
          :closable="false"
          class="pat-token-alert"
        />
        <el-alert v-else type="warning" :title="t('profile.patGuideNeedToken')" :closable="false" class="pat-token-alert">
          <div class="pat-guide-quick">
            <el-button size="small" type="primary" :loading="quickCreating" @click="quickCreatePat('readonly')">
              {{ t('profile.patQuickCreateReadonly') }}
            </el-button>
            <el-button size="small" type="warning" :loading="quickCreating" @click="quickCreatePat('full')">
              {{ t('profile.patQuickCreateFull') }}
            </el-button>
          </div>
        </el-alert>

        <div class="pat-guide">
          <p class="pat-guide-step">{{ t('profile.patGuideStep1') }}</p>
          <div class="pat-token-row">
            <code class="pat-token">{{ mcpUrl }}</code>
            <el-button size="small" @click="copyMcpUrl">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopy') }}
            </el-button>
          </div>
          <template v-if="hasLiveToken">
            <p class="pat-guide-step">{{ t('profile.patGuideStep2') }}</p>
            <el-tabs v-model="guideTab" class="pat-guide-tabs">
              <el-tab-pane :label="t('profile.patGuideTabConfig')" name="config">
                <div class="pat-token-row">
                  <code class="pat-token pat-token-tall pat-token-block">{{ liveConfig }}</code>
                  <el-button size="small" @click="copyLiveConfig">
                    <el-icon><CopyDocument /></el-icon>
                    {{ t('profile.patCopyConfig') }}
                  </el-button>
                </div>
              </el-tab-pane>
              <el-tab-pane :label="t('profile.patGuideTabCli')" name="cli">
                <p class="pat-guide-hint">{{ t('profile.patCliHint') }}</p>
                <div class="pat-token-row">
                  <code class="pat-token pat-token-tall pat-token-block">{{ liveCli }}</code>
                  <el-button size="small" @click="copyLiveCli">
                    <el-icon><CopyDocument /></el-icon>
                    {{ t('profile.patCopy') }}
                  </el-button>
                </div>
              </el-tab-pane>
              <el-tab-pane :label="t('profile.patGuideTabPrompt')" name="prompt">
                <p class="pat-guide-hint">{{ t('profile.patPromptHint') }}</p>
                <div class="pat-token-row">
                  <code class="pat-token pat-token-tall pat-token-block">{{ livePrompt }}</code>
                  <el-button size="small" @click="copyLivePrompt">
                    <el-icon><CopyDocument /></el-icon>
                    {{ t('profile.patCopyPrompt') }}
                  </el-button>
                </div>
              </el-tab-pane>
            </el-tabs>
            <p class="pat-guide-step">{{ t('profile.patGuideStep3') }}</p>
          </template>
          <el-alert type="info" :title="t('profile.patGuideTierNote')" :closable="false" class="pat-token-alert" />
          <p class="pat-guide-more">{{ t('profile.patGuideHint') }}</p>
        </div>
        <template #footer>
          <el-button type="primary" @click="guideVisible = false">{{ t('common.close') }}</el-button>
        </template>
      </el-dialog>
    </section>

    <!-- ============ 工具面简介 ============ -->
    <section class="mcp-card">
      <h3 class="card-title">{{ t('mcpAccess.toolsTitle') }}</h3>
      <p class="tools-hint">{{ t('mcpAccess.toolsHint') }}</p>
      <div v-for="group in toolGroups" :key="group.label" class="tool-group">
        <span class="tool-group-label">{{ group.label }}</span>
        <code class="tool-group-items">{{ group.items.join(' · ') }}</code>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Plus, CopyDocument, Guide } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { formatTime } from '@/lib/format'
import { useCopyText } from '@/composables/useCopyText'
import { useConfirm } from '@/composables/useConfirm'
import { createPat, listPats, revokePat, type PatInfo } from '@/api/pat'

const { t } = useI18n()

// ============ PAT 令牌 ============
const pats = ref<PatInfo[]>([])
const patDialogVisible = ref(false)
const patName = ref('')
const patPermission = ref<'readonly' | 'full'>('readonly')
const patCreating = ref(false)
const createdToken = ref('')

const { copyText } = useCopyText()
const { confirm } = useConfirm()

onMounted(loadPats)

async function loadPats() {
  try {
    pats.value = await listPats()
  } catch {
    ElMessage.error(t('profile.patLoadFailed'))
  }
}

function resetPatDialog() {
  patName.value = ''
  patPermission.value = 'readonly'
  createdToken.value = ''
}

async function handleCreatePat() {
  patCreating.value = true
  try {
    const created = await createPat(patName.value.trim() || 'CLI', patPermission.value)
    createdToken.value = created.token
    await loadPats()
  } catch {
    ElMessage.error(t('profile.patCreateFailed'))
  } finally {
    patCreating.value = false
  }
}

function copyCreatedToken() {
  copyText(createdToken.value, t('common.copied'))
}

async function handleRevokePat(row: PatInfo) {
  await confirm(t('profile.patRevokeConfirm'))
  try {
    await revokePat(row.id)
    ElMessage.success(t('profile.patRevokeSuccess'))
    await loadPats()
  } catch {
    ElMessage.error(t('profile.patLoadFailed'))
  }
}

// ============ 接入指引（令牌明文只在创建时存在：所有复制项统一嵌入「本次创建」的真实令牌，
// 没有可用明文时先走一键创建并填入，绝不展示占位符——复制出来必须整套可直接使用） ============
const guideVisible = ref(false)
const guideTab = ref('config')
const quickCreating = ref(false)

// 端点 URL：dev 由后端直连（vite 只代理 /api，不代理 /mcp）；配了 API base 用之；生产同源
const mcpUrl = computed(() => {
  const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined
  if (envBase) return `${envBase.replace(/\/+$/, '')}/mcp`
  if (import.meta.env.DEV) return 'http://localhost:8000/mcp'
  return `${window.location.origin}/mcp`
})

function mcpConfigSnippet(token: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        'agnes-platform': {
          type: 'http',
          url: mcpUrl.value,
          headers: { Authorization: `Bearer ${token}` },
        },
      },
    },
    null,
    2,
  )
}

function agentPromptSnippet(token: string): string {
  return [
    '请把以下 MCP 服务器添加到你的配置中（streamable HTTP），添加后重载并调用 tools/list 列出工具确认接入成功：',
    '- 名称：agnes-platform',
    `- URL：${mcpUrl.value}`,
    `- 请求头：Authorization: Bearer ${token}`,
  ].join('\n')
}

const hasLiveToken = computed(() => !!createdToken.value)
const liveConfig = computed(() => mcpConfigSnippet(createdToken.value))
const liveCli = computed(() =>
  `claude mcp add --transport http --scope user agnes-platform ${mcpUrl.value} --header "Authorization: Bearer ${createdToken.value}"`,
)
const livePrompt = computed(() => agentPromptSnippet(createdToken.value))

/** 指引内快捷创建（免表单）：创建后真实令牌自动填入全部复制项 */
async function quickCreatePat(permission: 'readonly' | 'full') {
  quickCreating.value = true
  try {
    const created = await createPat(t('profile.patQuickName'), permission)
    createdToken.value = created.token
    guideTab.value = 'config'
    await loadPats()
  } catch {
    ElMessage.error(t('profile.patCreateFailed'))
  } finally {
    quickCreating.value = false
  }
}

function copyMcpUrl() {
  copyText(mcpUrl.value, t('common.copied'))
}
function copyLiveConfig() {
  copyText(liveConfig.value, t('profile.patConfigCopied'))
}
function copyLiveCli() {
  copyText(liveCli.value, t('profile.patCliCopied'))
}
function copyLivePrompt() {
  copyText(livePrompt.value, t('profile.patPromptCopied'))
}

// ============ 工具面简介（静态摘要，与 mcp_gateway 注册表同步） ============
const toolGroups = computed(() => [
  { label: t('mcpAccess.groupCanvas'), items: ['canvas_list', 'canvas_create', 'canvas_get_overview', 'canvas_apply_ops'] },
  {
    label: t('mcpAccess.groupEditor'),
    items: [
      'editor_list_projects', 'editor_create_project', 'editor_get_document', 'editor_put_document',
      'editor_render_submit', 'editor_render_status', 'editor_rough_cut_analyze',
    ],
  },
  { label: t('mcpAccess.groupGeneration'), items: ['asset_list', 'model_list', 'image_generate', 'video_generate', 'generation_get'] },
])
</script>

<style scoped>
.mcp-access-page {
  max-width: 960px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 24px;
}
.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--agnes-text-primary);
}
.page-title .el-icon {
  color: var(--agnes-primary);
}
.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

.mcp-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 14px;
  padding: 24px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.mcp-card + .mcp-card {
  margin-top: 20px;
}
.card-title {
  margin: 0 0 18px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.pat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pat-header .card-title {
  margin-bottom: 0;
  border-bottom: none;
  padding-bottom: 0;
}
.pat-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pat-subtitle {
  margin: 8px 0 14px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}
.pat-token-alert {
  margin-bottom: 12px;
}
.pat-token-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pat-token {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
  color: var(--agnes-text-primary);
}
.pat-token-tall {
  padding: 10px 12px;
  line-height: 1.5;
  white-space: pre;
  overflow-x: auto;
}
.pat-token-block {
  max-height: 180px;
  overflow-y: auto;
}
.pat-divider {
  margin: 14px 0 10px;
}
.pat-config-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.pat-guide-step {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.pat-guide-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}
.pat-guide-tabs :deep(.el-tabs__content) {
  overflow: visible;
}
.pat-guide-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}
.pat-guide-quick {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.pat-guide .pat-guide-step:first-child {
  margin-top: 0;
}
.pat-guide .pat-token-row {
  margin-bottom: 16px;
}
.pat-guide-more {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--agnes-text-faint);
}

.tools-hint {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.tool-group {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
}
.tool-group + .tool-group {
  border-top: 1px dashed var(--agnes-border-faint);
}
.tool-group-label {
  flex-shrink: 0;
  width: 88px;
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-secondary);
}
.tool-group-items {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--agnes-text-primary);
  word-break: break-all;
  line-height: 1.6;
}
</style>

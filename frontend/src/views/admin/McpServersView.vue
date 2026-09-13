<!-- =====================================================
     MCP 服务器管理视图 McpServersView（管理员）
     - 「已安装」：服务器 CRUD / 启停 / 连接测试（工具清单预览）
     - 「市场」：官方内置目录 + 自建源（URL → manifest JSON）一键安装
     - stdio：command+args+env；http：url+headers；密钥写入后不回显（留空=保留原值）
     ===================================================== -->

<template>
  <div class="mcp-servers-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.mcp.title') }}</h2>
        <p class="muted">{{ t('admin.mcp.desc') }}</p>
      </div>
      <el-button v-if="activeTab === 'installed'" type="primary" :icon="Plus" @click="openCreate">{{ t('admin.mcp.add') }}</el-button>
    </header>

    <el-tabs v-model="activeTab">
      <!-- ============ 已安装 ============ -->
      <el-tab-pane :label="t('admin.mcp.tabInstalled')" name="installed">
        <el-card shadow="never">
          <el-table :data="servers" v-loading="loading" row-key="id">
            <el-table-column :label="t('admin.mcp.colName')" prop="name" min-width="140" />
            <el-table-column :label="t('admin.mcp.colTransport')" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="row.transport === 'stdio' ? 'warning' : 'success'" size="small">{{ row.transport }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.mcp.colTarget')" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <code class="target-code">{{ row.transport === 'stdio' ? row.command : row.url }}</code>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.mcp.colSecrets')" min-width="160">
              <template #default="{ row }">
                <template v-if="secretKeyNames(row).length">
                  <el-tag v-for="k in secretKeyNames(row)" :key="k" size="small" type="info" class="secret-tag">{{ k }}</el-tag>
                </template>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.mcp.colEnabled')" width="90" align="center">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="(v: boolean) => toggleEnabled(row, v)" />
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.mcp.colActions')" width="230" fixed="right">
              <template #default="{ row }">
                <el-button size="small" :loading="testingId === row.id" @click="testServer(row)">{{ t('admin.mcp.test') }}</el-button>
                <el-button size="small" @click="openEdit(row)">{{ t('common.edit') }}</el-button>
                <el-button size="small" type="danger" plain @click="removeServer(row)">{{ t('common.delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <p class="muted hint">{{ t('admin.mcp.hint') }}</p>
        </el-card>
      </el-tab-pane>

      <!-- ============ 市场 ============ -->
      <el-tab-pane :label="t('admin.mcp.tabMarket')" name="market">
        <el-card shadow="never" class="market-card">
          <!-- 源管理条 -->
          <div class="source-bar">
            <div class="source-list">
              <el-tag
                v-for="src in marketSources"
                :key="src.id"
                :closable="true"
                type="info"
                class="source-tag"
                @close="removeSource(src)"
              >
                <span class="source-tag-name" :title="src.url">{{ src.name }}（{{ src.item_count }}）</span>
                <el-icon class="source-refresh" :class="{ spinning: refreshingId === src.id }" @click="refreshSource(src)"><Refresh /></el-icon>
              </el-tag>
              <span v-if="!marketSources.length" class="muted">{{ t('admin.mcp.marketNoSources') }}</span>
            </div>
            <el-button size="small" :icon="Plus" @click="sourceDialogOpen = true">{{ t('admin.mcp.marketAddSource') }}</el-button>
          </div>

          <!-- 分类分组卡片 -->
          <div v-loading="marketLoading">
            <template v-for="(items, cat) in itemsByCategory" :key="cat">
              <h3 class="market-cat">{{ cat }}</h3>
              <div class="market-grid">
                <div v-for="item in items" :key="item.slug" class="market-item">
                  <div class="market-item-icon">{{ iconOf(item) }}</div>
                  <div class="market-item-body">
                    <div class="market-item-name">
                      {{ item.name }}
                      <el-tag size="small" :type="item.transport === 'stdio' ? 'warning' : 'success'" class="transport-tag">{{ item.transport }}</el-tag>
                      <el-tag v-if="item.installed" size="small" type="success">{{ t('admin.mcp.marketInstalled') }}</el-tag>
                    </div>
                    <div class="market-item-desc">{{ item.description }}</div>
                    <div class="market-item-meta">
                      <span v-if="item.tools_preview.length">{{ t('admin.mcp.marketToolCount', { n: item.tools_preview.length }) }}</span>
                      <span v-if="item.source_type === 'remote'" class="muted">{{ t('admin.mcp.marketFromSource') }}</span>
                    </div>
                  </div>
                  <el-button
                    size="small"
                    :type="item.installed ? 'default' : 'primary'"
                    :disabled="item.installed"
                    @click="openInstall(item)"
                  >{{ item.installed ? t('admin.mcp.marketInstalled') : t('admin.mcp.marketInstall') }}</el-button>
                </div>
              </div>
            </template>
            <p v-if="!marketItems.length && !marketLoading" class="muted">{{ t('admin.mcp.marketEmpty') }}</p>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 创建/编辑弹窗（已安装） -->
    <el-dialog v-model="dialogOpen" :title="editingId ? t('admin.mcp.editTitle') : t('admin.mcp.createTitle')" width="560px" destroy-on-close>
      <el-form :model="form" label-width="110px">
        <el-form-item :label="t('admin.mcp.formName')" required>
          <el-input v-model="form.name" :placeholder="t('admin.mcp.formNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('admin.mcp.formTransport')" required>
          <el-radio-group v-model="form.transport" :disabled="!!editingId">
            <el-radio value="stdio">stdio</el-radio>
            <el-radio value="http">http</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.transport === 'stdio'">
          <el-form-item :label="t('admin.mcp.formCommand')" required>
            <el-input v-model="form.command" placeholder="npx / python / uvx …" />
          </el-form-item>
          <el-form-item :label="t('admin.mcp.formArgs')">
            <el-input v-model="form.argsText" type="textarea" :rows="2" :placeholder="t('admin.mcp.formArgsPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('admin.mcp.formEnv')">
            <el-input v-model="form.envText" type="textarea" :rows="3" :placeholder="secretPlaceholder" />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item :label="t('admin.mcp.formUrl')" required>
            <el-input v-model="form.url" placeholder="https://…" />
          </el-form-item>
          <el-form-item :label="t('admin.mcp.formHeaders')">
            <el-input v-model="form.headersText" type="textarea" :rows="3" :placeholder="secretPlaceholder" />
          </el-form-item>
        </template>

        <el-form-item :label="t('admin.mcp.formEnabled')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <p class="muted hint">{{ t('admin.mcp.secretHint') }}</p>
      <template #footer>
        <el-button @click="dialogOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 连接测试结果弹窗 -->
    <el-dialog v-model="toolsOpen" :title="t('admin.mcp.toolsTitle', { name: testedName })" width="640px">
      <el-table :data="testedTools" size="small" max-height="420">
        <el-table-column prop="name" :label="t('admin.mcp.toolName')" width="200" show-overflow-tooltip />
        <el-table-column prop="description" :label="t('admin.mcp.toolDesc')" show-overflow-tooltip />
      </el-table>
      <p v-if="!testedTools.length" class="muted">{{ t('admin.mcp.noTools') }}</p>
    </el-dialog>

    <!-- 添加市场源弹窗 -->
    <el-dialog v-model="sourceDialogOpen" :title="t('admin.mcp.sourceTitle')" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item :label="t('admin.mcp.sourceName')">
          <el-input v-model="sourceForm.name" :placeholder="t('admin.mcp.sourceNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('admin.mcp.sourceUrl')" required>
          <el-input v-model="sourceForm.url" placeholder="https://example.com/mcp-market.json" />
        </el-form-item>
      </el-form>
      <p class="muted hint">{{ t('admin.mcp.sourceHint') }}</p>
      <template #footer>
        <el-button @click="sourceDialogOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="sourceSaving" @click="addSource">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 市场项安装弹窗 -->
    <el-dialog v-model="installOpen" :title="t('admin.mcp.installTitle', { name: installingItem?.name ?? '' })" width="560px" destroy-on-close>
      <template v-if="installingItem">
        <p class="market-item-desc install-desc">{{ installingItem.description }}</p>
        <el-form label-width="110px">
          <el-form-item :label="t('admin.mcp.formName')" required>
            <el-input v-model="installForm.name" />
          </el-form-item>
          <template v-if="installingItem.transport === 'stdio'">
            <el-form-item :label="t('admin.mcp.formCommand')" required>
              <el-input v-model="installForm.command" />
            </el-form-item>
            <el-form-item :label="t('admin.mcp.formArgs')">
              <el-input v-model="installForm.argsText" type="textarea" :rows="2" :placeholder="t('admin.mcp.formArgsPlaceholder')" />
            </el-form-item>
            <el-form-item v-for="f in installingItem.env_fields" :key="f.key" :label="f.key">
              <el-input v-model="installForm.env[f.key]" type="password" show-password :placeholder="fieldPlaceholder(f)" />
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item :label="t('admin.mcp.formUrl')" required>
              <el-input v-model="installForm.url" />
            </el-form-item>
            <el-form-item v-for="f in installingItem.headers_fields" :key="f.key" :label="f.key">
              <el-input v-model="installForm.headers[f.key]" type="password" show-password :placeholder="fieldPlaceholder(f)" />
            </el-form-item>
          </template>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="installOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="installing" @click="install">{{ t('admin.mcp.marketInstall') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import {
  listMcpServers, createMcpServer, updateMcpServer, deleteMcpServer, testMcpServer,
  listMarketSources, createMarketSource, deleteMarketSource, refreshMarketSource,
  listMarketItems, installMarketItem,
} from '@/api/mcp'
import type { McpServerSafe, McpMarketSourceInfo, McpMarketItemInfo, McpSecretField } from '@/api/mcp'

const { t } = useI18n()
const { confirm } = useConfirm()

const activeTab = ref<'installed' | 'market'>('installed')

// ---------- 已安装 ----------
const servers = ref<McpServerSafe[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogOpen = ref(false)
const editingId = ref<number | null>(null)
const toolsOpen = ref(false)
const testedName = ref('')
const testedTools = ref<Array<{ name: string; description: string }>>([])
const testingId = ref<number | null>(null)

const secretPlaceholder = 'KEY=value'

interface ServerForm {
  name: string
  transport: 'stdio' | 'http'
  command: string
  argsText: string
  envText: string
  url: string
  headersText: string
  enabled: boolean
}
const emptyForm = (): ServerForm => ({ name: '', transport: 'stdio', command: '', argsText: '', envText: '', url: '', headersText: '', enabled: true })
const form = ref<ServerForm>(emptyForm())

const secretKeyNames = (row: McpServerSafe): string[] => [...Object.keys(row.env_keys ?? {}), ...Object.keys(row.header_keys ?? {})]

/** KV 文本（每行 KEY=value）→ 对象；解析失败返回 null 并提示 */
function parseKvText(text: string): Record<string, string> | null {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const idx = trimmed.indexOf('=')
    if (idx <= 0) {
      ElMessage.warning(t('admin.mcp.kvFormatError', { line: trimmed }))
      return null
    }
    out[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim()
  }
  return out
}

async function load() {
  loading.value = true
  try {
    servers.value = await listMcpServers()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  dialogOpen.value = true
}

function openEdit(row: McpServerSafe) {
  editingId.value = row.id
  form.value = {
    name: row.name,
    transport: row.transport,
    command: row.command ?? '',
    argsText: (row.args ?? []).join('\n'),
    envText: '',
    url: row.url ?? '',
    headersText: '',
    enabled: row.enabled,
  }
  dialogOpen.value = true
}

async function save() {
  if (!form.value.name.trim()) {
    ElMessage.warning(t('admin.mcp.nameRequired'))
    return
  }
  saving.value = true
  try {
    const env = form.value.envText.trim() ? parseKvText(form.value.envText) : null
    const headers = form.value.headersText.trim() ? parseKvText(form.value.headersText) : null
    if (env === null || headers === null) return
    const body = {
      name: form.value.name.trim(),
      transport: form.value.transport,
      enabled: form.value.enabled,
      command: form.value.transport === 'stdio' ? form.value.command.trim() : undefined,
      args: form.value.transport === 'stdio' ? form.value.argsText.split('\n').map((x) => x.trim()).filter(Boolean) : undefined,
      env: form.value.transport === 'stdio' ? (env ?? undefined) : undefined,
      url: form.value.transport === 'http' ? form.value.url.trim() : undefined,
      headers: form.value.transport === 'http' ? (headers ?? undefined) : undefined,
    }
    if (editingId.value) await updateMcpServer(editingId.value, body)
    else await createMcpServer(body as never)
    ElMessage.success(t('admin.mcp.saved'))
    dialogOpen.value = false
    await Promise.all([load(), activeTab.value === 'market' ? loadMarket() : Promise.resolve()])
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row: McpServerSafe, enabled: boolean) {
  try {
    await updateMcpServer(row.id, {
      name: row.name, transport: row.transport, enabled,
      command: row.command ?? undefined,
      args: row.args ?? undefined,
      url: row.url ?? undefined,
    })
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function testServer(row: McpServerSafe) {
  testingId.value = row.id
  try {
    const r = await testMcpServer(row.id)
    testedName.value = r.name
    testedTools.value = r.tools
    toolsOpen.value = true
    if (!r.tools.length) ElMessage.info(t('admin.mcp.noTools'))
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    testingId.value = null
  }
}

async function removeServer(row: McpServerSafe) {
  await confirm(t('admin.mcp.deleteConfirm', { name: row.name }), t('common.confirm'))
  try {
    await deleteMcpServer(row.id)
    ElMessage.success(t('admin.mcp.deleted'))
    await Promise.all([load(), activeTab.value === 'market' ? loadMarket() : Promise.resolve()])
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

// ---------- 市场 ----------
const marketSources = ref<McpMarketSourceInfo[]>([])
const marketItems = ref<McpMarketItemInfo[]>([])
const marketLoading = ref(false)
const refreshingId = ref<number | null>(null)
const sourceDialogOpen = ref(false)
const sourceSaving = ref(false)
const sourceForm = ref({ name: '', url: '' })
const installOpen = ref(false)
const installing = ref(false)
const installingItem = ref<McpMarketItemInfo | null>(null)
const installForm = ref<{ name: string; command: string; argsText: string; url: string; env: Record<string, string>; headers: Record<string, string> }>({
  name: '', command: '', argsText: '', url: '', env: {}, headers: {},
})

const itemsByCategory = computed(() => {
  const groups: Record<string, McpMarketItemInfo[]> = {}
  for (const item of marketItems.value) {
    const cat = item.category || t('admin.mcp.marketUncategorized')
    ;(groups[cat] ??= []).push(item)
  }
  return groups
})

function iconOf(item: McpMarketItemInfo): string {
  if (item.transport === 'http') return '🌐'
  if (item.slug.includes('file')) return '📁'
  if (item.slug.includes('fetch') || item.slug.includes('web')) return '🕸'
  if (item.slug.includes('memory')) return '🧠'
  return '🧩'
}

function fieldPlaceholder(f: McpSecretField): string {
  return f.required ? t('admin.mcp.secretRequiredPlaceholder') : t('admin.mcp.secretOptionalPlaceholder')
}

async function loadMarket() {
  marketLoading.value = true
  try {
    const [srcs, items] = await Promise.all([listMarketSources(), listMarketItems()])
    marketSources.value = srcs
    marketItems.value = items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    marketLoading.value = false
  }
}

async function addSource() {
  if (!sourceForm.value.url.trim().startsWith('http')) {
    ElMessage.warning(t('admin.mcp.sourceUrlInvalid'))
    return
  }
  sourceSaving.value = true
  try {
    await createMarketSource(sourceForm.value.name.trim(), sourceForm.value.url.trim())
    sourceDialogOpen.value = false
    sourceForm.value = { name: '', url: '' }
    await loadMarket()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    sourceSaving.value = false
  }
}

async function removeSource(src: McpMarketSourceInfo) {
  await confirm(t('admin.mcp.sourceDeleteConfirm', { name: src.name }), t('common.confirm'))
  try {
    await deleteMarketSource(src.id)
    await loadMarket()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function refreshSource(src: McpMarketSourceInfo) {
  refreshingId.value = src.id
  try {
    const r = await refreshMarketSource(src.id)
    ElMessage.success(t('admin.mcp.sourceRefreshed', { n: r.count }))
    await loadMarket()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    refreshingId.value = null
  }
}

function openInstall(item: McpMarketItemInfo) {
  installingItem.value = item
  installForm.value = {
    name: item.name,
    command: item.command ?? '',
    argsText: (item.args ?? []).join('\n'),
    url: item.url ?? '',
    env: {},
    headers: {},
  }
  installOpen.value = true
}

async function install() {
  const item = installingItem.value
  if (!item) return
  installing.value = true
  try {
    await installMarketItem({
      slug: item.slug,
      name: installForm.value.name.trim(),
      command: item.transport === 'stdio' ? installForm.value.command.trim() : undefined,
      args: item.transport === 'stdio' ? installForm.value.argsText.split('\n').map((x) => x.trim()).filter(Boolean) : undefined,
      url: item.transport === 'http' ? installForm.value.url.trim() : undefined,
      env: item.transport === 'stdio' && Object.keys(installForm.value.env).length ? installForm.value.env : undefined,
      headers: item.transport === 'http' && Object.keys(installForm.value.headers).length ? installForm.value.headers : undefined,
    })
    ElMessage.success(t('admin.mcp.installDone', { name: installForm.value.name }))
    installOpen.value = false
    await Promise.all([load(), loadMarket()])
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    installing.value = false
  }
}

onMounted(() => {
  void load()
  void loadMarket()
})
</script>

<style scoped>
.mcp-servers-wrap {
  padding: 20px 24px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.page-head h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.muted {
  color: var(--agnes-text-muted, #8b93a8);
  font-size: 13px;
  margin: 0;
}
.hint {
  margin-top: 10px;
}
.target-code {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
.secret-tag {
  margin-right: 4px;
}

/* 市场标签 */
.source-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.source-tag {
  height: 28px;
  padding-left: 6px;
}
.source-tag-name {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.source-refresh {
  margin-left: 4px;
  cursor: pointer;
  vertical-align: middle;
}
.source-refresh.spinning {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.market-cat {
  margin: 14px 0 10px;
  font-size: 14px;
}
.market-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.market-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid var(--agnes-border, #e4e7ed);
  border-radius: 8px;
}
.market-item-icon {
  font-size: 22px;
  line-height: 1.2;
}
.market-item-body {
  flex: 1;
  min-width: 0;
}
.market-item-name {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.transport-tag {
  font-weight: 400;
}
.market-item-desc {
  font-size: 12px;
  color: var(--agnes-text-muted, #8b93a8);
  margin: 4px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.market-item-meta {
  font-size: 12px;
  display: flex;
  gap: 10px;
}
.install-desc {
  margin-bottom: 12px;
}
</style>

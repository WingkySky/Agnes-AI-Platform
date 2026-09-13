<!-- =====================================================
     MCP 服务器管理视图 McpServersView（管理员）
     - 服务器 CRUD / 启停 / 连接测试（工具清单预览）
     - stdio：command+args+env；http：url+headers；密钥写入后不回显（留空=保留原值）
     ===================================================== -->

<template>
  <div class="mcp-servers-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.mcp.title') }}</h2>
        <p class="muted">{{ t('admin.mcp.desc') }}</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">{{ t('admin.mcp.add') }}</el-button>
    </header>

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

    <!-- 创建/编辑弹窗 -->
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from '@/i18n'
import { useConfirm } from '@/composables/useConfirm'
import {
  listMcpServers, createMcpServer, updateMcpServer, deleteMcpServer, testMcpServer,
} from '@/api/mcp'
import type { McpServerSafe } from '@/api/mcp'

const { t } = useI18n()
const { confirm } = useConfirm()

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
    await load()
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
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(load)
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
</style>

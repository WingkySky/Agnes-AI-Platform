<!-- =====================================================
     SkillImportDialog — 技能整包上传（zip / 文件夹）
     - 压缩包或文件夹须含 SKILL.md（YAML frontmatter：name/description）
     - 其余文本文件存为附件资源（脚本仅存档不执行，二进制跳过）
     - 解析预览 → 确认后直接落库并刷新技能缓存，导入即用
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('presets.skillImport.title')" width="640px" destroy-on-close @closed="reset">
    <el-alert :title="t('presets.skillImport.trustHint')" type="warning" :closable="false" style="margin-bottom: 12px" />

    <div class="upload-area" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
      <input ref="folderInputRef" type="file" webkitdirectory multiple style="display: none" @change="onFolderPick" />
      <input ref="zipInputRef" type="file" accept=".zip" style="display: none" @change="onZipPick" />
      <p class="hint">{{ t('presets.skillImport.fileHint') }}</p>
      <div class="upload-btns">
        <el-button :icon="FolderOpened" :loading="parsing" @click="folderInputRef?.click()">
          {{ t('presets.skillImport.folderBtn') }}
        </el-button>
        <el-button :icon="Files" :loading="parsing" @click="zipInputRef?.click()">
          {{ t('presets.skillImport.zipBtn') }}
        </el-button>
      </div>
    </div>

    <div v-if="result" class="preview">
      <el-divider content-position="left"><span class="section-title">{{ t('presets.skillImport.preview') }}</span></el-divider>
      <p class="kv"><b>{{ result.name }}</b></p>
      <p class="kv muted">{{ result.description || t('presets.skillImport.noDesc') }}</p>
      <p class="kv" v-if="result.tag">{{ t('presets.skillImport.tagLabel').replace('{tag}', result.tag) }}</p>
      <p class="kv">{{ t('presets.skillImport.contentChars').replace('{n}', String(result.content.length)) }}</p>
      <template v-if="result.resources.length > 0">
        <p class="kv">{{ t('presets.skillImport.resourceCount').replace('{n}', String(result.resources.length)) }}</p>
        <div class="resource-list">
          <el-tag v-for="r in result.resources" :key="r.path" size="small" type="info" class="resource-tag">{{ r.path }}</el-tag>
        </div>
      </template>
      <el-alert v-for="w in result.warnings" :key="w" :title="w" type="warning" :closable="false" style="margin-top: 6px" />
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="!result" @click="confirmImport">
        {{ t('presets.skillImport.confirmImport') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Files } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { unzipSync } from 'fflate'
import { createPreset } from '@/api/presets'
import { listAgentSkills } from '@/lib/agent/skills'
import { parseSkillPackage, type SkillImportInput, type SkillImportResult } from '@/utils/skillImport'

const props = defineProps<{
  modelValue: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported'): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const folderInputRef = ref<HTMLInputElement | null>(null)
const zipInputRef = ref<HTMLInputElement | null>(null)
const parsing = ref(false)
const saving = ref(false)
const result = ref<SkillImportResult | null>(null)

function reset() {
  result.value = null
}

async function parseInputs(inputs: SkillImportInput[]) {
  parsing.value = true
  try {
    result.value = parseSkillPackage(inputs)
  } catch (e) {
    result.value = null
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    parsing.value = false
  }
}

async function onFolderPick(e: Event) {
  if (!(e.target instanceof HTMLInputElement)) return
  const files = Array.from(e.target.files ?? [])
  e.target.value = ''
  if (files.length === 0) return
  await parseInputs(
    await collectInputs(files.map((f) => ({ file: f, path: f.webkitRelativePath || f.name })))
  )
}

async function onZipPick(e: Event) {
  if (!(e.target instanceof HTMLInputElement)) return
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  await parseInputs(await inputsFromZip(file, file.name))
}

/** ZIP → 解析输入（路径带 ZIP 名前缀，防与其他来源重名） */
async function inputsFromZip(file: File, path: string): Promise<SkillImportInput[]> {
  const entries = unzipSync(new Uint8Array(await file.arrayBuffer()))
  const prefix = path.replace(/\.zip$/i, '')
  const inputs: SkillImportInput[] = []
  for (const [inner, data] of Object.entries(entries)) {
    if (inner.endsWith('/')) continue
    inputs.push({ path: `${prefix}/${inner}`, text: new TextDecoder().decode(data) })
  }
  return inputs
}

// ---------- 拖拽导入（文件夹/ZIP/零散文件） ----------

const dragging = ref(false)

function isFileEntry(entry: FileSystemEntry): entry is FileSystemFileEntry {
  return entry.isFile
}

function isDirectoryEntry(entry: FileSystemEntry): entry is FileSystemDirectoryEntry {
  return entry.isDirectory
}

function entryFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

/** readEntries 每次最多返回 100 条，循环读到空为止 */
async function readDirEntries(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  const reader = dir.createReader()
  const all: FileSystemEntry[] = []
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (batch.length === 0) return all
    all.push(...batch)
  }
}

async function walkEntry(entry: FileSystemEntry, path: string, inputs: SkillImportInput[]): Promise<void> {
  if (isFileEntry(entry)) {
    const file = await entryFile(entry)
    if (file.name.toLowerCase().endsWith('.zip')) {
      inputs.push(...(await inputsFromZip(file, path)))
    } else {
      inputs.push({ path, text: await file.text() })
    }
    return
  }
  if (!isDirectoryEntry(entry)) return
  for (const child of await readDirEntries(entry)) {
    await walkEntry(child, `${path}/${child.name}`, inputs)
  }
}

async function onDrop(e: DragEvent) {
  dragging.value = false
  if (parsing.value || !e.dataTransfer) return
  const items = Array.from(e.dataTransfer.items)
  const roots: Array<{ entry: FileSystemEntry; path: string }> = []
  for (const item of items) {
    const entry = item.webkitGetAsEntry()
    if (entry) roots.push({ entry, path: entry.name })
  }
  // 无 entries 支持时退回普通文件列表（ZIP 或零散文件）
  if (roots.length === 0) {
    const files = Array.from(e.dataTransfer.files)
    if (files.length === 0) return
    await parseInputs(await collectInputs(files.map((f) => ({ file: f, path: f.name }))))
    return
  }
  const inputs: SkillImportInput[] = []
  for (const { entry, path } of roots) await walkEntry(entry, path, inputs)
  if (inputs.length > 0) await parseInputs(inputs)
}

async function collectInputs(files: Array<{ file: File; path: string }>): Promise<SkillImportInput[]> {
  const inputs: SkillImportInput[] = []
  for (const { file, path } of files) {
    if (file.name.toLowerCase().endsWith('.zip')) {
      inputs.push(...(await inputsFromZip(file, path)))
    } else {
      inputs.push({ path, text: await file.text() })
    }
  }
  return inputs
}

/** 直接落库（同名拒重对齐 agent_save_skill 语义），成功后刷新 Agent 技能缓存即用 */
async function confirmImport() {
  const r = result.value
  if (!r || saving.value) return
  saving.value = true
  try {
    const existing = await listAgentSkills(true)
    if (existing.some((s) => s.name.toLowerCase() === r.name.toLowerCase())) {
      ElMessage.error(t('presets.skillImport.nameConflict').replace('{name}', r.name))
      return
    }
    await createPreset({
      type: 'skill',
      name: r.name,
      description: r.description || undefined,
      prompt_text: r.content,
      category: '技能',
      prompt_config: {
        tag: r.tag || undefined,
        import_meta: r.importMeta,
        resources: r.resources.length ? r.resources : undefined,
        allowed_tools: r.allowedTools.length ? r.allowedTools : undefined,
      },
      source: 'skill_md',
    })
    await listAgentSkills(true).catch(() => {})
    ElMessage.success(t('presets.skillImport.importSuccess').replace('{name}', r.name))
    emit('imported')
    visible.value = false
  } catch {
    /* 错误已由拦截器提示 */
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.upload-area {
  padding: 24px 16px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  text-align: center;
  transition: border-color 0.15s, background-color 0.15s;
}
.upload-area.dragging {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}
.upload-area .hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.upload-btns {
  display: flex;
  justify-content: center;
  gap: 8px;
}
.preview .kv {
  margin: 4px 0;
  font-size: 13px;
}
.preview .muted {
  color: var(--el-text-color-secondary);
}
.resource-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 6px 0;
}
.resource-tag {
  max-width: 100%;
}
.section-title {
  font-weight: 600;
  font-size: 13px;
}
</style>

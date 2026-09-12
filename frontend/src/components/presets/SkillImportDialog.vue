<!-- =====================================================
     SkillImportDialog — SKILL.md 技能导入
     - 两种输入：多选 .md/.txt 文件 / 粘贴文本
     - 解析预览（frontmatter 映射 + 附件并入 + 跳过清单）→ 确认创建 type=skill
     - 同名技能拒绝（按名加载不允许歧义）
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('presets.skillImport.title')" width="640px" destroy-on-close @closed="reset">
    <el-radio-group v-model="mode" style="margin-bottom: 12px">
      <el-radio-button value="file">{{ t('presets.skillImport.modeFile') }}</el-radio-button>
      <el-radio-button value="paste">{{ t('presets.skillImport.modePaste') }}</el-radio-button>
    </el-radio-group>

    <div v-if="mode === 'file'" class="file-area">
      <input ref="fileInputRef" type="file" multiple accept=".md,.markdown,.txt" style="display: none" @change="onFilePick" />
      <el-button :icon="Document" @click="fileInputRef?.click()">{{ t('presets.skillImport.fileBtn') }}</el-button>
      <p class="hint">{{ t('presets.skillImport.fileHint') }}</p>
    </div>

    <div v-else class="paste-area">
      <el-input v-model="pasteName" :placeholder="t('presets.skillImport.pasteName')" style="margin-bottom: 8px" />
      <el-input v-model="pasteText" type="textarea" :rows="8" :placeholder="t('presets.skillImport.pasteText')" />
    </div>

    <div v-if="result" class="preview">
      <el-divider content-position="left"><span class="section-title">{{ t('presets.skillImport.preview') }}</span></el-divider>
      <p class="kv"><b>{{ result.name }}</b></p>
      <p class="kv muted">{{ result.description || t('presets.skillImport.noDesc') }}</p>
      <p class="kv" v-if="result.tag">{{ t('presets.skillImport.tagLabel').replace('{tag}', result.tag) }}</p>
      <p class="kv">{{ t('presets.skillImport.contentChars').replace('{n}', String(result.content.length)) }}</p>
      <el-alert v-for="w in result.warnings" :key="w" :title="w" type="warning" :closable="false" style="margin-top: 6px" />
    </div>

    <template #footer>
      <el-button v-if="mode === 'paste'" :disabled="!pasteText.trim()" @click="parseInputs">{{ t('presets.skillImport.parse') }}</el-button>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :disabled="!result" :loading="creating" @click="confirmImport">
        {{ t('presets.skillImport.confirmImport') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { createPreset } from '@/api/presets'
import { parseSkillImport, type SkillImportInput, type SkillImportResult } from '@/utils/skillImport'
import { listAgentSkills } from '@/lib/agent/skills'

const props = defineProps<{
  modelValue: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported', presetName: string): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const mode = ref<'file' | 'paste'>('file')
const fileInputRef = ref<HTMLInputElement | null>(null)
const pasteName = ref('')
const pasteText = ref('')
const inputs = ref<SkillImportInput[]>([])
const result = ref<SkillImportResult | null>(null)
const creating = ref(false)

function reset() {
  mode.value = 'file'
  pasteName.value = ''
  pasteText.value = ''
  inputs.value = []
  result.value = null
  creating.value = false
}

async function onFilePick(e: Event) {
  if (!(e.target instanceof HTMLInputElement)) return
  const files = Array.from(e.target.files ?? [])
  e.target.value = ''
  if (files.length === 0) return
  const list: SkillImportInput[] = []
  for (const f of files) {
    list.push({ name: f.name, text: await f.text() })
  }
  inputs.value = list
  parseInputs()
}

function parseInputs() {
  try {
    result.value = parseSkillImport(inputs.value)
  } catch (e: any) {
    result.value = null
    ElMessage.error(e?.message || '解析失败')
  }
}

async function confirmImport() {
  if (!result.value) return
  creating.value = true
  try {
    // 同名查重（按名加载不允许歧义；大小写不敏感，对齐 getCachedSkill 匹配语义）
    const existing = await listAgentSkills(true)
    if (existing.some((s) => s.name.trim().toLowerCase() === result.value!.name.toLowerCase())) {
      ElMessage.error(t('presets.skillImport.conflict').replace('{name}', result.value.name))
      return
    }
    await createPreset({
      type: 'skill',
      name: result.value.name,
      description: result.value.description,
      prompt_text: result.value.content,
      category: '技能',
      prompt_config: { tag: result.value.tag || undefined, import_meta: result.value.importMeta },
      source: 'skill_md',
    })
    // 刷新技能缓存：当前画布会话的 load_skill 立即可用
    await listAgentSkills(true)
    ElMessage.success(t('presets.skillImport.importSuccess'))
    emit('imported', result.value.name)
    visible.value = false
  } catch {
    /* 错误已由拦截器提示 */
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.file-area .hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.preview .kv {
  margin: 4px 0;
  font-size: 13px;
}
.preview .muted {
  color: var(--el-text-color-secondary);
}
.section-title {
  font-weight: 600;
  font-size: 13px;
}
</style>

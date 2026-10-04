<!-- =====================================================
  PromptOptimizeDialog 提示词优化弹窗（共享组件）
  - 5 模式 = 5 个独立面板：首次切到某模式自动跑，结果与用户编辑缓存在各自面板，
    来回切换立即呈现（不同模式各自保留编辑与选中变体），「应用」取当前面板内容
  - 结果区（正向可编辑/负向/变化说明/假设声明/变体切换）+ 应用回填
  - 挂载点：生成页输入区 / 画布 composer / 批量创作表行提示词
  - el-dialog append-to-body + 全局 CSS 变量（不依赖画布主题子树）
  - 任何情况下不直接改调用方输入：应用时 emit('apply') 由调用方回填
===================================================== -->

<template>
  <el-dialog
    :model-value="visible"
    :title="t('promptOptimizer.title')"
    width="560px"
    append-to-body
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
    @closed="resetPanels"
  >
    <!-- 输入区：模式选择（切换即看各自面板） -->
    <div class="opt-modes">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button v-for="m in MODES" :key="m" :value="m">{{ t(`promptOptimizer.mode_${m}`) }}</el-radio-button>
      </el-radio-group>
    </div>

    <div class="opt-origin">
      <span class="opt-label">{{ t('promptOptimizer.originPrompt') }}</span>
      <p class="opt-origin-text">{{ initialPrompt || t('promptOptimizer.emptyPrompt') }}</p>
    </div>

    <!-- 当前模式面板：加载 / 错误 / 结果 -->
    <div v-if="current?.loading" class="opt-state" v-loading="true" :element-loading-text="t('promptOptimizer.loading')" />
    <div v-else-if="current && current.error" class="opt-state">
      <el-alert :title="current.error" type="error" :closable="false" />
      <el-button size="small" class="opt-retry" @click="runOptimize(mode)">{{ t('promptOptimizer.retry') }}</el-button>
    </div>
    <template v-else-if="current && current.result">
      <div v-if="current.result.assumptions.length" class="opt-notes">
        <el-alert type="info" :closable="false">
          <p v-for="a in current.result.assumptions" :key="a" class="opt-note-item">· {{ a }}</p>
        </el-alert>
      </div>
      <div class="opt-field">
        <div class="opt-field-head">
          <span class="opt-label">{{ t('promptOptimizer.positive') }}</span>
          <el-radio-group
            v-if="current.result.variants.length"
            :model-value="current.variantIndex" size="small"
            @update:model-value="setVariant"
          >
            <el-radio-button :value="-1">{{ t('promptOptimizer.mainResult') }}</el-radio-button>
            <el-radio-button
              v-for="(v, i) in current.result.variants" :key="i" :value="i"
            >{{ v.label || t('promptOptimizer.variant', { n: i + 1 }) }}</el-radio-button>
          </el-radio-group>
        </div>
        <el-input v-model="positiveModel" type="textarea" :rows="5" />
      </div>
      <div v-if="current.result.negative || current.negative" class="opt-field">
        <span class="opt-label">{{ t('promptOptimizer.negative') }}</span>
        <el-input v-model="negativeModel" type="textarea" :rows="2" />
      </div>
      <div v-if="current.result.changes.length" class="opt-field">
        <span class="opt-label">{{ t('promptOptimizer.changes') }}</span>
        <p v-for="c in current.result.changes" :key="c" class="opt-note-item">· {{ c }}</p>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">{{ t('common.cancel') }}</el-button>
      <el-button :disabled="!current?.result" type="primary" @click="onApply">
        {{ t('promptOptimizer.apply') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { optimizePrompt, type PromptOptimizeResult } from '@/api/prompts'
import { getErrorMessage } from '@/lib/type-helpers'

const MODES = ['expand', 'refine', 'style', 'model-adapt', 'reference'] as const
type Mode = (typeof MODES)[number]

const props = defineProps<{
  visible: boolean
  initialPrompt: string
  target: 'image' | 'video'
  /** model-adapt 模式注入方言规则；reference 模式注入参考素材名 */
  modelId?: string
  referenceNames?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'apply', payload: { positive: string; negative: string }): void
}>()

const { t } = useI18n()

/** 每个模式一份独立面板状态：结果、用户编辑、选中的变体各自保留 */
interface PanelState {
  loading: boolean
  error: string
  result: PromptOptimizeResult | null
  /** 正向编辑区内容：variantIndex=-1 时是主结果，否则是所选变体的文本 */
  positive: string
  negative: string
  /** 主结果独立保存：编辑主结果后切走再切回不丢失，也不串进变体 */
  mainPositive: string
  variantIndex: number
  /** 防竞态序号：快速切换/重试时旧响应不覆盖新状态 */
  seq: number
}

const panels = reactive<Record<string, PanelState>>({})
const mode = ref<Mode>('refine')

function ensurePanel(m: Mode): PanelState {
  if (!panels[m]) {
    panels[m] = { loading: false, error: '', result: null, positive: '', negative: '', mainPositive: '', variantIndex: -1, seq: 0 }
  }
  return panels[m]!
}

const current = computed<PanelState | undefined>(() => panels[mode.value])

watch(mode, (m) => {
  const panel = ensurePanel(m)
  // 首次访问该模式自动跑；跑过（含失败）保留原状，失败用面板内重试
  if (!panel.result && !panel.loading && !panel.error) {
    void runOptimize(m)
  }
})

watch(() => props.visible, (v) => {
  if (v) {
    resetPanels()
    mode.value = 'refine'
    const panel = ensurePanel('refine')
    void runOptimize('refine', panel)
  }
})

function resetPanels() {
  for (const key of Object.keys(panels)) delete panels[key]
}

/** 跑指定模式（seq 防竞态：响应只写入发起时的面板） */
async function runOptimize(m: Mode, panelOverride?: PanelState) {
  const panel = panelOverride ?? ensurePanel(m)
  panel.seq += 1
  const seq = panel.seq
  panel.loading = true
  panel.error = ''
  try {
    const data = await optimizePrompt({
      prompt: props.initialPrompt,
      mode: m,
      target: props.target,
      context: {
        model_id: props.modelId || '',
        reference_asset_names: props.referenceNames || [],
      },
    })
    if (panel.seq !== seq) return
    panel.result = data
    panel.positive = data.positive
    panel.negative = data.negative
    panel.mainPositive = data.positive
    panel.variantIndex = -1
  } catch (err) {
    if (panel.seq !== seq) return
    panel.error = getErrorMessage(err) || t('promptOptimizer.retryFailed')
  } finally {
    if (panel.seq === seq) panel.loading = false
  }
}

/* ---------- 当前面板的可编辑绑定 ---------- */

const positiveModel = computed({
  get: () => current.value?.positive ?? '',
  set: (v: string) => {
    const panel = current.value
    if (!panel) return
    panel.positive = v
    // 编辑主结果时同步回主结果槽位，切变体再切回不丢
    if (panel.variantIndex === -1) panel.mainPositive = v
  },
})

const negativeModel = computed({
  get: () => current.value?.negative ?? '',
  set: (v: string) => {
    if (current.value) current.value.negative = v
  },
})

/** 变体切换：主结果/变体各自呈现，主结果编辑不受影响 */
function setVariant(index: number | string | boolean | undefined) {
  const panel = current.value
  if (!panel?.result) return
  const i = typeof index === 'number' ? index : -1
  panel.variantIndex = i
  panel.positive = i === -1 ? panel.mainPositive : (panel.result.variants[i]?.prompt ?? panel.mainPositive)
}

function onApply() {
  const panel = current.value
  if (!panel?.result) return
  emit('apply', { positive: panel.positive, negative: panel.negative })
  emit('update:visible', false)
}
</script>

<style scoped>
.opt-modes {
  margin-bottom: 12px;
}

.opt-label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.opt-origin {
  margin-bottom: 12px;
}

.opt-origin-text {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  background: var(--agnes-bg-inset, var(--el-fill-color-light));
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 88px;
  overflow-y: auto;
  white-space: pre-wrap;
}

.opt-state {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.opt-retry {
  margin: 0 auto;
}

.opt-notes {
  margin-bottom: 10px;
}

.opt-note-item {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.opt-field {
  margin-bottom: 12px;
}

.opt-field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
  gap: 8px;
}
</style>

<!-- =====================================================
  ScriptWizardDialog 分镜向导（无限画布 script 节点，LibTV 复刻）
  - 全屏覆盖层向导：①确认镜头（全屏表格）→ ②准备资产（角色/场景图卡）→ ③批量生成
  - 剧情概述在节点悬浮 AI 对话框（CanvasNodeComposer）中输入并生成分镜
  - 数据读写 script 节点 content（shots/assets/style，localforage 本地持久化）
  - 资产图：调 createGenerationTask + pollImageTask 生成，或本地上传（dataURL）
  - 批量生成复用 lib/canvas-storyboard（积分确认/并发/派生节点/连线）
===================================================== -->

<template>
  <Teleport to="body">
    <div v-if="visible && panel" class="wizard-overlay" :style="overlayStyle">
      <!-- 顶部：三步指示条 + 关闭 -->
      <div class="wizard-header" :style="headerStyle">
        <div class="wizard-steps">
          <template v-for="(s, i) in stepDefs" :key="s.no">
            <div
              class="wizard-step"
              :class="{ active: step === s.no }"
              @click="step = s.no"
            >
              <span class="step-dot" :style="stepDotStyle(s)">{{ step > s.no ? '✓' : s.no }}</span>
              <span class="step-texts">
                <span class="step-title" :style="stepTitleStyle(s)">{{ s.title }}</span>
                <span class="step-hint" :style="mutedStyle">{{ s.hint }}</span>
              </span>
            </div>
            <div v-if="i < stepDefs.length - 1" class="step-line" :style="lineStyle"></div>
          </template>
        </div>
        <button type="button" class="wizard-close" :style="mutedStyle" @click="emitClose">×</button>
      </div>

      <!-- 步骤1：确认镜头（全屏表格）；剧情概述在节点悬浮对话框中输入 -->
      <div v-if="step === 1" class="wizard-body">
        <table class="shot-table">
          <thead>
            <tr :style="mutedStyle">
              <th class="col-no">{{ t('canvas.script.wizard.colNo') }}</th>
              <th class="col-duration">{{ t('canvas.script.wizard.colDuration') }}</th>
              <th class="col-size">{{ t('canvas.script.wizard.colSize') }}</th>
              <th class="col-camera">{{ t('canvas.script.wizard.colCamera') }}</th>
              <th class="col-scene">{{ t('canvas.script.wizard.colScene') }}</th>
              <th class="col-characters">{{ t('canvas.script.wizard.colCharacters') }}</th>
              <th>{{ t('canvas.script.wizard.colDesc') }}</th>
              <th>{{ t('canvas.script.wizard.colDialogue') }}</th>
              <th class="col-action"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(shot, idx) in shots" :key="shot.id" :style="rowStyle">
              <td class="col-no" :style="mutedStyle">#{{ shot.no }}</td>
              <td class="col-duration">
                <input
                  v-model.number="shot.duration"
                  type="number" min="4" max="12"
                  class="wiz-input" :style="inputStyle"
                  @input="persistShots"
                >
              </td>
              <td class="col-size">
                <select v-model="shot.shotSize" class="wiz-input" :style="inputStyle" @change="persistShots">
                  <option v-for="s in shotSizes" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
              </td>
              <td class="col-camera">
                <input v-model="shot.camera" class="wiz-input" :style="inputStyle" :placeholder="t('canvas.script.cameraPlaceholder')" @input="persistShots">
              </td>
              <td class="col-scene">
                <input v-model="shot.location" class="wiz-input" :style="inputStyle" :placeholder="t('canvas.script.wizard.scenePlaceholder')" @input="persistShots">
              </td>
              <td class="col-characters">
                <input :value="shot.characters.join('，')" class="wiz-input" :style="inputStyle" :placeholder="t('canvas.script.wizard.charactersPlaceholder')" @input="onCharactersInput(shot, $event)">
              </td>
              <td>
                <textarea v-model="shot.description" rows="2" class="wiz-input" :style="inputStyle" :placeholder="t('canvas.script.descPlaceholder')" @input="persistShots"></textarea>
              </td>
              <td>
                <textarea v-model="shot.dialogue" rows="2" class="wiz-input" :style="inputStyle" :placeholder="t('canvas.script.dialoguePlaceholder')" @input="persistShots"></textarea>
              </td>
              <td class="col-action">
                <button type="button" class="wiz-del" :title="t('canvas.script.deleteShot')" @click="removeShot(idx)">×</button>
              </td>
            </tr>
          </tbody>
        </table>
        <button type="button" class="wiz-btn" :style="btnStyle" @click="addShot">+ {{ t('canvas.script.wizard.addShot') }}</button>
      </div>

      <!-- 步骤2：准备资产（全局风格 + 角色/场景图卡） -->
      <div v-else-if="step === 2" class="wizard-body">
        <!-- 全局风格 -->
        <div class="style-row">
          <span class="style-label" :style="accentStyle">{{ t('canvas.script.wizard.globalStyle') }}</span>
          <input v-model="style" class="wiz-input style-input" :style="inputStyle" :placeholder="t('canvas.script.stylePlaceholder')" @input="persistStyle">
        </div>

        <!-- 资产参考图生成参数：存脚本节点 content，重开向导保留 -->
        <div class="style-row">
          <span class="style-label" :style="accentStyle">{{ t('canvas.script.wizard.assetParams') }}</span>
          <ComposerParamBar v-if="panel" :panel="panel" mode="image" :content-key="ASSET_IMAGE_PARAMS_KEY" />
        </div>

        <!-- 角色/场景资产卡区块 -->
        <div v-for="section in assetSections" :key="section.kind" class="asset-section">
          <div class="asset-section-head">
            <h3 class="asset-title">{{ section.title }}</h3>
            <button type="button" class="wiz-btn small" :style="btnStyle" @click="addAsset(section.kind)">+ {{ section.addLabel }}</button>
          </div>
          <div class="asset-grid">
            <div
              v-for="a in section.list"
              :key="a.id"
              class="asset-card"
              :style="cardStyle"
            >
              <!-- 参考图区：预览（点击放大查看）/ 空态 / 生成中，悬浮操作 -->
              <div class="asset-img">
                <img v-if="a.imageUrl" :src="a.imageUrl" alt="" @click="openAssetViewer(a)">
                <span v-else class="asset-empty" :style="mutedStyle">{{ t('canvas.script.wizard.emptyImage') }}</span>
                <span v-if="generatingAssets.has(a.id)" class="asset-loading">⟳</span>
                <div class="asset-actions">
                  <button type="button" class="asset-act" :disabled="generatingAssets.has(a.id)" @click="generateAssetImage(a, section.kind)">{{ t('canvas.script.wizard.genImage') }}</button>
                  <button type="button" class="asset-act" @click="openUpload(a, section.kind)">{{ t('canvas.script.wizard.upload') }}</button>
                  <button type="button" class="asset-act danger" @click="removeAsset(section.kind, a.id)">{{ t('canvas.script.wizard.delete') }}</button>
                </div>
              </div>
              <input
                v-model="a.name"
                class="wiz-input asset-name" :style="inputStyle"
                :placeholder="t('canvas.script.wizard.namePlaceholder')"
                @input="persistAssets"
              >
              <textarea
                v-model="a.description"
                rows="3"
                class="wiz-input asset-desc" :style="inputStyle"
                :placeholder="t('canvas.script.wizard.descPlaceholder')"
                @input="persistAssets"
              ></textarea>
              <span v-if="assetShotLabel(section.kind, a.name)" class="asset-shots" :style="mutedStyle">
                {{ t('canvas.script.wizard.assocShots', { nos: assetShotLabel(section.kind, a.name) }) }}
              </span>
            </div>
            <button type="button" class="asset-add" :style="addCardStyle" @click="addAsset(section.kind)">+ {{ section.addLabel }}</button>
          </div>
        </div>

        <input ref="fileInputRef" type="file" accept="image/*" class="wiz-file" @change="handleFileSelect">
      </div>

      <!-- 步骤3：批量生成（最终提示词预览 + 分镜图结果关联 + 批量派生） -->
      <div v-else class="wizard-body">
        <div class="gen-list">
          <div v-for="row in genRows" :key="row.shot.id" class="gen-row" :style="cardStyle">
            <div class="gen-info">
              <div class="gen-row-head">
                <span class="gen-no" :style="badgeStyle">#{{ row.shot.no }}</span>
                <span class="gen-status" :class="{ ready: shotStatus.image.has(row.shot.id) }">
                  {{ shotStatus.image.has(row.shot.id) ? t('canvas.script.wizard.shotReady') : t('canvas.script.wizard.shotPending') }}
                </span>
                <span v-if="row.promptEdited" class="gen-edited">{{ t('canvas.script.wizard.promptEdited') }}</span>
                <span class="gen-duration" :style="mutedStyle">{{ row.shot.duration }}s</span>
              </div>
              <div class="gen-prompt" :style="mutedStyle">{{ row.prompt }}</div>
            </div>
            <div class="gen-media">
              <div v-if="row.imagePanel" class="gen-thumb">
                <img
                  v-if="row.thumbUrl"
                  :src="row.thumbUrl"
                  :alt="`#${row.shot.no}`"
                  @click="openGenViewer(row.thumbUrl)"
                >
                <span v-else class="gen-thumb-empty" :style="mutedStyle">
                  {{ row.thumbFailed ? t('canvas.node.generateFailed') : t('canvas.node.generating') }}
                </span>
                <div class="gen-thumb-actions">
                  <button type="button" class="gen-act" @click="locateShotPanel(row.imagePanel)">
                    {{ t('canvas.script.wizard.locateNode') }}
                  </button>
                  <button type="button" class="gen-act" :disabled="row.generating" @click="reshootShotImage(row.imagePanel)">
                    {{ t('canvas.script.wizard.reshoot') }}
                  </button>
                </div>
              </div>
              <span v-else class="gen-none" :style="mutedStyle">{{ t('canvas.script.wizard.noImage') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作区 -->
      <div class="wizard-footer" :style="headerStyle">
        <div class="footer-left">
          <button v-if="step > 1" type="button" class="wiz-btn" :style="btnStyle" @click="step--">{{ t('canvas.script.wizard.prev') }}</button>
        </div>
        <div class="footer-right">
          <!-- 步骤1：下一步 -->
          <button
            v-if="step === 1"
            type="button"
            class="wiz-btn primary" :style="primaryBtnStyle"
            @click="step = 2"
          >
            {{ t('canvas.script.wizard.nextAsset') }}
          </button>
          <!-- 步骤2：一键生成资产 + 下一步 -->
          <template v-else-if="step === 2">
            <button type="button" class="wiz-btn" :style="btnStyle" :disabled="generatingAssets.size > 0" @click="generateAllAssets">
              {{ t('canvas.script.wizard.genAllAssets') }}
            </button>
            <button type="button" class="wiz-btn primary" :style="primaryBtnStyle" @click="step = 3">
              {{ t('canvas.script.wizard.nextGen') }}
            </button>
          </template>
          <!-- 步骤3：批量生成（参数作为派生 config 节点的初值，派生后逐镜头可再改） -->
          <template v-else>
            <div class="gen-params">
              <span class="gen-params-label" :style="accentStyle">{{ t('canvas.script.wizard.imageParams') }}</span>
              <ComposerParamBar v-if="panel" :panel="panel" mode="image" :content-key="SHOT_IMAGE_PARAMS_KEY" />
              <span class="gen-params-label" :style="accentStyle">{{ t('canvas.script.wizard.videoParams') }}</span>
              <ComposerParamBar v-if="panel" :panel="panel" mode="video" :content-key="SHOT_VIDEO_PARAMS_KEY" />
            </div>
            <button type="button" class="wiz-btn primary" :style="primaryBtnStyle" @click="onBatchImages">
              {{ t('canvas.script.wizard.batchImages') }}
            </button>
            <button type="button" class="wiz-btn" :style="btnStyle" @click="onBatchVideos">
              {{ t('canvas.script.wizard.batchVideos') }}
            </button>
          </template>
        </div>
      </div>

      <!-- 图片放大查看（复用历史页 ImageViewer 模块：滚轮缩放/拖动/旋转） -->
      <ImageViewer v-model:visible="viewerVisible" :url="viewerUrl" />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { useCanvasStore, type CanvasPanel } from '@/stores/canvas'
import ComposerParamBar from '@/components/canvas/ComposerParamBar.vue'
import { checkCreditsBeforeGenerate } from '@/lib/canvas-credits'
import { createGenerationTask, pollImageTask, getUpstreamNodes, readPanelGenParams } from '@/lib/canvas-generation'
import { getErrorMessage } from '@/lib/type-helpers'
import ImageViewer from '@/components/ImageViewer.vue'
import {
  deriveStoryboardImages,
  deriveStoryboardVideos,
  findDerivedPanels,
  getDerivedShotIds,
  ASSET_IMAGE_PARAMS_KEY,
  SHOT_IMAGE_PARAMS_KEY,
  SHOT_VIDEO_PARAMS_KEY,
  readAssets,
  readShots,
  reshootImagePanel,
  buildAssetImagePrompt,
  buildShotContexts,
  buildShotImagePrompt,
  shotNosForAsset,
  type CanvasShot,
  type ScriptAssets,
  type ShotAsset,
} from '@/lib/canvas-storyboard'

const props = defineProps<{ panelId: string; visible: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
const store = useCanvasStore()

/** 当前脚本节点 */
const panel = computed(() => store.panels.find((p) => p.id === props.panelId) || null)

/* ---------- 常量 ---------- */
const MAX_SHOTS = 30

const shotSizes = computed(() => [
  { value: '远景', label: t('canvas.script.sizeFar') },
  { value: '全景', label: t('canvas.script.sizeFull') },
  { value: '中景', label: t('canvas.script.sizeMid') },
  { value: '近景', label: t('canvas.script.sizeClose') },
  { value: '特写', label: t('canvas.script.sizeExtreme') },
])

/* ---------- 向导状态（打开时从节点 content 初始化，编辑即持久化） ---------- */
const step = ref(1)
const shots = ref<CanvasShot[]>([])
const assets = ref<ScriptAssets>({ characters: [], scenes: [] })
const style = ref('')
const generatingAssets = ref<Set<string>>(new Set())
const uploadTarget = ref<{ kind: 'characters' | 'scenes'; id: string } | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

/** 图片放大查看（复用历史页 ImageViewer 模块） */
const viewerVisible = ref(false)
const viewerUrl = ref('')

function openAssetViewer(asset: ShotAsset) {
  if (!asset.imageUrl) return
  viewerUrl.value = asset.imageUrl
  viewerVisible.value = true
}

watch(() => props.visible, (v) => {
  if (!v || !panel.value) return
  step.value = 1
  shots.value = readShots(panel.value)
  const a = readAssets(panel.value)
  assets.value = { characters: a.characters, scenes: a.scenes }
  style.value = typeof panel.value.content?.style === 'string' ? panel.value.content.style : ''
})

function updateContent(patch: Record<string, unknown>) {
  if (panel.value) store.updatePanel(panel.value.id, { content: patch })
}

function persistShots() {
  updateContent({ shots: JSON.parse(JSON.stringify(shots.value)) })
}

function persistAssets() {
  updateContent({ assets: JSON.parse(JSON.stringify(assets.value)) })
}

function persistStyle() {
  updateContent({ style: style.value })
}

/* ---------- 步骤指示条（标题/提示随数据动态） ---------- */
const stepDefs = computed(() => [
  { no: 1, title: t('canvas.script.wizard.stepShot'), hint: t('canvas.script.wizard.hintShots', { n: shots.value.length }) },
  {
    no: 2,
    title: t('canvas.script.wizard.stepAsset'),
    hint: t('canvas.script.wizard.hintAssets', { n: assets.value.characters.length + assets.value.scenes.length }),
  },
  {
    no: 3,
    title: t('canvas.script.wizard.stepGen'),
    hint: t('canvas.script.wizard.hintGen', { done: shotStatus.value.image.size, total: shots.value.length }),
  },
])

/* ---------- 步骤2：资产卡区块（角色/场景共用一套渲染） ---------- */
const assetSections = computed(() => [
  { kind: 'characters' as const, list: assets.value.characters, title: t('canvas.script.wizard.characters'), addLabel: t('canvas.script.wizard.addCharacter') },
  { kind: 'scenes' as const, list: assets.value.scenes, title: t('canvas.script.wizard.scenes'), addLabel: t('canvas.script.wizard.addScene') },
])

/* ---------- 步骤1：镜头表格编辑 ---------- */
function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
}

function addShot() {
  if (shots.value.length >= MAX_SHOTS) return
  shots.value.push({
    id: newId('shot'),
    no: shots.value.length + 1,
    duration: 5,
    shotSize: '中景',
    camera: '',
    description: '',
    dialogue: '',
    characters: [],
    location: '',
  })
  persistShots()
}

/** 出场角色输入：逗号分隔文本 ↔ 字符串数组 */
function onCharactersInput(shot: CanvasShot, event: Event) {
  const raw = (event.target as HTMLInputElement)?.value || ''
  shot.characters = raw.split(/[，,]/).map((s) => s.trim()).filter(Boolean)
  persistShots()
}

/** 资产卡在分镜中的出场镜头标签（"#1、#3"，无关联返回空） */
function assetShotLabel(kind: 'characters' | 'scenes', name: string): string {
  return shotNosForAsset(shots.value, kind, name).map((n) => `#${n}`).join('、')
}

function removeShot(idx: number) {
  shots.value.splice(idx, 1)
  shots.value.forEach((s, i) => { s.no = i + 1 })
  persistShots()
}

/* ---------- 步骤2：资产卡编辑 ---------- */
function addAsset(kind: 'characters' | 'scenes') {
  assets.value[kind].push({ id: newId('asset'), name: '', description: '', imageUrl: '' })
  persistAssets()
}

function removeAsset(kind: 'characters' | 'scenes', id: string) {
  assets.value[kind] = assets.value[kind].filter((a) => a.id !== id)
  persistAssets()
}

/** 生成资产参考图（角色/场景设定图：名称 + 描述 + 全局风格） */
async function generateAssetImage(asset: ShotAsset, kind: 'characters' | 'scenes') {
  if (generatingAssets.value.has(asset.id)) return
  const desc = asset.description.trim() || asset.name.trim()
  if (!desc) {
    ElMessage.warning(t('canvas.script.wizard.needDesc'))
    return
  }
  const params = readPanelGenParams(panel.value, 'image', ASSET_IMAGE_PARAMS_KEY)
  const ok = await checkCreditsBeforeGenerate({ type: 'image', mode: 'text2image', size: params.size })
  if (!ok) return

  generatingAssets.value = new Set([...generatingAssets.value, asset.id])
  try {
    const label = kind === 'characters' ? t('canvas.script.wizard.characterLabel') : t('canvas.script.wizard.sceneLabel')
    const ctx = {
      prompt: buildAssetImagePrompt(panel.value!, asset, kind, label),
      referenceImages: [] as string[],
      referenceTexts: [] as string[],
      inputSummary: { textCount: 0, imageCount: 0, videoCount: 0, total: 0 },
    }
    const resp = await createGenerationTask(ctx, { model: params.model, size: params.size }, {
      source: 'canvas',
      container_type: 'canvas_script',
      container_id: panel.value?.id || null,
      container_name: (panel.value?.name as string) || undefined,
      asset_type: kind === 'characters' ? 'character' : 'scene',
      asset_name: asset.name || desc,
    })
    const result = await pollImageTask(resp.task_id)
    asset.imageUrl = result.resultUrl
    persistAssets()
  } catch (err) {
    ElMessage.error(getErrorMessage(err) || t('canvas.script.wizard.genFailed'))
  } finally {
    const next = new Set(generatingAssets.value)
    next.delete(asset.id)
    generatingAssets.value = next
  }
}

/** 一键生成全部缺失参考图（顺序执行，逐张回填） */
async function generateAllAssets() {
  const pending = [...assets.value.characters, ...assets.value.scenes].filter((a) => !a.imageUrl)
  if (pending.length === 0) {
    ElMessage.info(t('canvas.script.wizard.assetsReady'))
    return
  }
  for (const asset of pending) {
    const kind = assets.value.characters.includes(asset) ? 'characters' : 'scenes'
    await generateAssetImage(asset, kind)
  }
}

/** 本地上传参考图（dataURL 存节点 content，localforage 持久化） */
function openUpload(asset: ShotAsset, kind: 'characters' | 'scenes') {
  uploadTarget.value = { kind, id: asset.id }
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement)?.files?.[0]
  if (!file || !uploadTarget.value) return
  const { kind, id } = uploadTarget.value
  const reader = new FileReader()
  reader.onload = () => {
    const asset = assets.value[kind].find((a) => a.id === id)
    if (asset) {
      asset.imageUrl = reader.result as string
      persistAssets()
    }
  }
  reader.readAsDataURL(file)
}

/* ---------- 步骤3：最终提示词预览 + 批量派生 ---------- */
const shotStatus = computed(() =>
  panel.value
    ? getDerivedShotIds(panel.value.id)
    : { image: new Set<string>(), video: new Set<string>() },
)

/** 各镜头最终提示词（画面描述 + 景别/运镜 + 风格 + 按镜头命中的角色/场景设定，与实际派生一致） */
const shotPrompts = computed(() => {
  const map = new Map<string, string>()
  if (!panel.value) return map
  const upstreams = getUpstreamNodes(panel.value.id, store.panels, store.connections)
  const upstreamTexts = upstreams
    .filter((p) => p.type === 'text')
    .map((p) => (typeof p.content?.content === 'string' ? p.content.content : ''))
  for (const shot of shots.value) {
    const contexts = buildShotContexts(shot, assets.value, upstreamTexts)
    map.set(shot.id, buildShotImagePrompt(panel.value, shot, contexts))
  }
  return map
})

/* ---------- 步骤3：分镜图结果关联（缩略图 / 定位 / 重拍） ---------- */

/** 每行渲染数据：镜头 + 最终提示词 + 已派生的分镜图节点（直出 image 节点，取首个） */
const genRows = computed(() => {
  if (!panel.value) return []
  const imagePanels = new Map<string, CanvasPanel>()
  for (const d of findDerivedPanels(panel.value.id, 'image')) {
    if (d.panel.type !== 'image' || imagePanels.has(d.lineage.shotId)) continue
    imagePanels.set(d.lineage.shotId, d.panel)
  }
  return shots.value.map((shot) => {
    const p = imagePanels.get(shot.id) || null
    const rawUrl = p?.content?.content
    const status = p?.content?.status
    // 派生节点上被手动编辑过的 prompt 是重新生成的实际依据，优先于按镜头数据拼装的预览
    const nodePromptRaw = p?.content?.prompt
    const nodePrompt = typeof nodePromptRaw === 'string' && nodePromptRaw.trim() ? nodePromptRaw : ''
    const assembled = shotPrompts.value.get(shot.id) || '—'
    return {
      shot,
      prompt: nodePrompt || assembled,
      promptEdited: Boolean(nodePrompt) && nodePrompt !== shotPrompts.value.get(shot.id),
      imagePanel: p,
      thumbUrl: typeof rawUrl === 'string' ? rawUrl : '',
      generating: status === 'loading' || status === 'pending',
      thumbFailed: status === 'error',
    }
  })
})

/** 关闭向导并定位到画布上的分镜图节点 */
function locateShotPanel(target: CanvasPanel | null) {
  if (!target) return
  emitClose()
  store.selectPanel(target.id, { append: false })
  store.centerOnPanel(target.id)
}

/** 单镜头重拍（就地重新生成，保留模型/参数/参考图） */
function reshootShotImage(target: CanvasPanel | null) {
  if (!target) return
  void reshootImagePanel(target)
}

/** 放大查看分镜图结果 */
function openGenViewer(url: string) {
  if (!url) return
  viewerUrl.value = url
  viewerVisible.value = true
}

function onBatchImages() {
  if (panel.value) void deriveStoryboardImages(panel.value)
}

function onBatchVideos() {
  if (panel.value) void deriveStoryboardVideos(panel.value)
}

function emitClose() {
  emit('close')
}

/* ---------- 主题样式 ---------- */
const theme = computed(() => store.canvasTheme)
const overlayStyle = computed(() => ({ background: theme.value.node.panel, color: theme.value.node.text }))
const headerStyle = computed(() => ({ borderColor: theme.value.node.stroke }))
const mutedStyle = computed(() => ({ color: theme.value.node.muted }))
const accentStyle = computed(() => ({ color: theme.value.node.activeStroke }))
const inputStyle = computed(() => ({
  background: theme.value.node.fill,
  borderColor: theme.value.node.stroke,
  color: theme.value.node.text,
}))
const cardStyle = computed(() => ({ borderColor: theme.value.node.stroke }))
const addCardStyle = computed(() => ({ borderColor: theme.value.node.stroke, color: theme.value.node.muted }))
const badgeStyle = computed(() => ({
  background: theme.value.node.fill,
  color: theme.value.node.activeStroke,
}))
const rowStyle = computed(() => ({ borderColor: theme.value.node.faint }))
const lineStyle = computed(() => ({ background: theme.value.node.faint }))
const btnStyle = computed(() => ({
  background: theme.value.node.fill,
  borderColor: theme.value.node.stroke,
  color: theme.value.node.text,
}))
const primaryBtnStyle = computed(() => ({
  background: theme.value.node.activeStroke,
  borderColor: theme.value.node.activeStroke,
  color: '#fff',
}))

function stepDotStyle(s: { no: number }) {
  if (step.value === s.no) {
    return { background: theme.value.node.activeStroke, color: '#fff', borderColor: theme.value.node.activeStroke }
  }
  return { background: 'transparent', color: theme.value.node.muted, borderColor: theme.value.node.faint }
}

function stepTitleStyle(s: { no: number }) {
  return { color: step.value === s.no ? theme.value.node.text : theme.value.node.muted }
}
</script>

<style scoped>
/* 向导为 Teleport 到 body 的全屏覆盖层；scoped 不影响 Teleport（data-v 仍打在本组件模板元素上），
   必须保持 scoped，否则 .asset-card/.asset-grid 等通用类名会泄漏污染素材库面板 */
.wizard-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wizard-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid;
}
.wizard-steps {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}
.wizard-step {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex: none;
}
.step-texts {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.step-title {
  font-size: 13px;
  font-weight: 600;
}
.step-hint {
  font-size: 11px;
}
.step-line {
  flex: 1;
  max-width: 120px;
  height: 1px;
  opacity: 0.5;
}
.wizard-close {
  border: none;
  background: transparent;
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.wizard-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.wizard-footer {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-top: 1px solid;
  gap: 12px;
}
.footer-left,
.footer-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 通用输入/按钮 */
.wiz-input {
  width: 100%;
  border: 1px solid;
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 12px;
  line-height: 1.5;
  outline: none;
  resize: vertical;
  box-sizing: border-box;
  font-family: inherit;
}
.wiz-btn {
  border: 1px solid;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.wiz-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.wiz-btn.primary {
  font-weight: 600;
}
.wiz-btn.small {
  padding: 4px 10px;
  font-size: 11px;
}
.wiz-del {
  border: none;
  background: transparent;
  color: #e5484d;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.wiz-file {
  display: none;
}

/* 步骤1：镜头表格 */
.shot-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.shot-table th {
  text-align: left;
  font-size: 11px;
  font-weight: 500;
  padding: 6px 8px;
  white-space: nowrap;
}
.shot-table td {
  border-top: 1px solid;
  padding: 8px 6px;
  vertical-align: top;
}
.shot-table .col-no {
  width: 48px;
  text-align: center;
  font-size: 12px;
}
.shot-table .col-duration {
  width: 72px;
}
.shot-table .col-size {
  width: 96px;
}
.shot-table .col-camera {
  width: 140px;
}
.shot-table .col-scene {
  width: 110px;
}
.shot-table .col-characters {
  width: 140px;
}
.shot-table .col-action {
  width: 36px;
  text-align: center;
}

/* 步骤2：资产 */
.style-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.style-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.style-input {
  max-width: 640px;
}
.asset-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.asset-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.asset-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}
.asset-card {
  border: 1px solid;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.asset-img {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(120, 150, 200, 0.06);
}
.asset-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  cursor: zoom-in;
}
.asset-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.asset-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  animation: wiz-spin 1s linear infinite;
}
@keyframes wiz-spin {
  to { transform: rotate(360deg); }
}
.asset-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 6px;
  padding: 6px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  opacity: 0;
  transition: opacity 0.15s;
}
.asset-img:hover .asset-actions {
  opacity: 1;
}
.asset-act {
  border: none;
  border-radius: 6px;
  background: rgba(20, 28, 46, 0.85);
  color: #fff;
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
}
.asset-act:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.asset-act.danger {
  color: #ff7b81;
}
.asset-name {
  font-weight: 600;
}
.asset-desc {
  resize: none;
}
.asset-shots {
  font-size: 11px;
  line-height: 1.4;
}
.asset-add {
  min-height: 160px;
  border: 1px dashed;
  border-radius: 12px;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}

/* 步骤3：批量参数区（底栏宽不足时整块换行，不挤压批量按钮） */
.gen-params {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.gen-params-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

/* 步骤3：生成列表（左信息右缩略图） */
.gen-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 1100px;
}
.gen-row {
  border: 1px solid;
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 14px;
}
.gen-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gen-media {
  flex: none;
  width: 220px;
  display: flex;
}
.gen-thumb {
  position: relative;
  width: 100%;
  min-height: 110px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(120, 150, 200, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
}
.gen-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  cursor: zoom-in;
}
.gen-thumb-empty {
  font-size: 12px;
  padding: 16px 10px;
}
.gen-thumb-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 6px;
  padding: 6px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  opacity: 0;
  transition: opacity 0.15s;
}
.gen-thumb:hover .gen-thumb-actions {
  opacity: 1;
}
.gen-act {
  flex: 1;
  border: none;
  border-radius: 6px;
  background: rgba(20, 28, 46, 0.85);
  color: #fff;
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
}
.gen-act:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gen-none {
  align-self: center;
  font-size: 12px;
}
.gen-row-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gen-no {
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  padding: 1px 8px;
}
.gen-status {
  font-size: 11px;
  color: #e5a03c;
}
.gen-status.ready {
  color: #4cc38a;
}
.gen-edited {
  font-size: 11px;
  color: #e5a03c;
}
.gen-duration {
  font-size: 11px;
  margin-left: auto;
}
.gen-prompt {
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

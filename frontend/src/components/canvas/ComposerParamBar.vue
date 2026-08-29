<!-- =====================================================
     ComposerParamBar：画布悬浮 Composer 底栏参数条
     - 复用 ParamSelector 的选项与交互，只做字段适配 + 持久化
     - ParamSelector 用驼峰（aspectRatio/frameRate），节点 content 用蛇形（aspect_ratio/frame_rate）
     - 字段名与 Config 节点 content 完全一致，合并生成链路（executeMerge*）零改动
     - 写入走 canvasStore.updatePanel（content 深合并），调用方一行接入：
         <ComposerParamBar :panel="panel" mode="video" />
     - contentKey：传值时读写 content[contentKey] 子对象，供 script 节点同时存放
       多套参数（资产图 / 分镜图 / 分镜视频）互不覆盖
===================================================== -->

<template>
  <ParamSelector
    :mode="mode"
    :model="model"
    :size="size"
    :aspect-ratio="aspectRatio"
    :resolution="resolution"
    :seconds="seconds"
    :frame-rate="frameRate"
    @update:model="persist('model', $event)"
    @update:size="persist('size', $event)"
    @update:aspect-ratio="persist('aspect_ratio', $event)"
    @update:resolution="persist('resolution', $event)"
    @update:seconds="persist('seconds', $event)"
    @update:frame-rate="persist('frame_rate', $event)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ParamSelector from '@/components/ParamSelector.vue'
import { useCanvasStore, type CanvasPanel } from '@/stores/canvas'
import { useModelsStore } from '@/stores/models'

const props = defineProps<{
  panel: CanvasPanel
  mode: 'image' | 'video'
  /** 多套参数共存时的分区键，不传则读写 content 根字段 */
  contentKey?: string
}>()

const store = useCanvasStore()
const modelsStore = useModelsStore()

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 参数读写所在的 content 对象：分区键存在时取子对象，取不到视为全部未选择 */
const content = computed<Record<string, unknown>>(() => {
  const root = props.panel.content || {}
  const scoped = props.contentKey ? root[props.contentKey] : root
  return isRecord(scoped) ? scoped : {}
})

/** 读 content 字段；未选或值非法时回落该类型默认值（只影响展示，不写回 content） */
const model = computed(() => {
  const stored = String(content.value.model ?? '')
  const list = props.mode === 'video' ? modelsStore.videoModels : modelsStore.imageModels
  return list.some((m) => m.id === stored) ? stored : modelsStore.getDefaultModel(props.mode)
})
const size = computed(() => String(content.value.size ?? '') || modelsStore.defaultImageSize)
const aspectRatio = computed(
  () => String(content.value.aspect_ratio ?? '') || modelsStore.defaultVideoAspectRatio,
)
const resolution = computed(
  () => Number(content.value.resolution) || modelsStore.defaultVideoResolution,
)
const seconds = computed(() => Number(content.value.seconds) || modelsStore.defaultVideoDuration)
const frameRate = computed(() => Number(content.value.frame_rate) || modelsStore.defaultFrameRate)

/** 参数变更即时持久化到节点 content，下次打开/重跑继承该选择 */
function persist(key: string, value: string | number) {
  const patch = props.contentKey ? { [props.contentKey]: { [key]: value } } : { [key]: value }
  store.updatePanel(props.panel.id, { content: patch })
}
</script>

<style scoped>
/* 底栏宽约 300-520px：限制单个标签宽度，超长模型名省略而不是撑破对话框 */
.param-selector :deep(.param-tag) {
  max-width: 160px;
}
.param-selector :deep(.param-tag__text) {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

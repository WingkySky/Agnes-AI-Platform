<!-- =====================================================
     PresetDetailDialog — 预设详情弹层
     - 大封面 + 名称/作者/热度/标签/描述 + 提示词内容
     - 动作：收藏 / Fork / 应用（按类型应用行为不同）
     ===================================================== -->

<template>
  <el-dialog
    :model-value="!!preset"
    width="760px"
    :close-on-click-modal="true"
    destroy-on-close
    @close="emit('close')"
  >
    <div class="detail-body" v-if="preset">
      <!-- 左：封面（特效/运镜为动态封面循环播放） -->
      <div class="detail-cover">
        <video
          v-if="preset.cover_video"
          class="detail-video"
          :src="preset.cover_video"
          :poster="preset.cover_image || undefined"
          muted
          loop
          autoplay
          playsinline
        ></video>
        <img v-else-if="preset.cover_image" :src="preset.cover_image" :alt="preset.name" />
        <div v-else class="cover-placeholder">
          <el-icon :size="48"><component :is="typeIcon(preset.type)" /></el-icon>
        </div>
      </div>

      <!-- 右：信息 -->
      <div class="detail-info">
        <div class="detail-name">
          {{ preset.name }}
          <span v-if="preset.is_official" class="official-badge">{{ t('presets.plaza.official') }}</span>
        </div>
        <div class="detail-meta">
          <span>
            <el-icon :size="13"><User /></el-icon>
            {{ preset.author_nickname || t('presets.plaza.officialAuthor') }}
          </span>
          <span>
            <el-icon :size="13"><View /></el-icon>
            {{ preset.usage_count }} {{ t('presets.plaza.uses') }}
          </span>
          <span class="meta-type">{{ typeLabel(preset.type) }}</span>
        </div>

        <div class="detail-tags" v-if="preset.tags && preset.tags.length">
          <el-tag v-for="tag in preset.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
        </div>

        <p class="detail-desc" v-if="preset.description">{{ preset.description }}</p>

        <!-- 可应用内容预览 -->
        <div class="detail-prompt" v-if="applyableText">
          <div class="prompt-head">
            <span>{{ t('presets.plaza.contentTitle') }}</span>
            <el-button link size="small" @click="copyText(applyableText)">
              {{ t('presets.plaza.copy') }}
            </el-button>
          </div>
          <pre class="prompt-text">{{ applyableText }}</pre>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button
        v-if="canGenerateCover"
        :loading="generatingCover"
        @click="onGenerateCover"
      >
        {{ isVideoCoverPreset ? t('presets.plaza.generateCoverVideo') : t('presets.plaza.generateCover') }}
      </el-button>
      <el-button @click="onFork" :loading="forking" v-if="preset && !preset.is_official">
        {{ t('presets.plaza.fork') }}
      </el-button>
      <el-button @click="onToggleFavorite" v-if="preset">
        <el-icon style="margin-right: 4px">
          <StarFilled v-if="preset.is_favorite" />
          <Star v-else />
        </el-icon>
        {{ preset.is_favorite ? t('presets.plaza.favorited') : t('presets.plaza.favorite') }}
      </el-button>
      <el-button type="primary" @click="emit('apply', preset!)" v-if="showApply && preset">
        {{ t('presets.plaza.apply') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { ElMessage } from 'element-plus'
import { Star, StarFilled, User, View, Brush, MagicStick, VideoCamera, EditPen, Document } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { forkPreset, generatePresetCover } from '@/api/presets'
import { usePresetStore } from '@/stores/presets'
import { useUserStore } from '@/stores/user'
import { useCopyText } from '@/composables/useCopyText'
import type { PromptPreset } from '@/types/preset'

const props = withDefaults(
  defineProps<{
    preset: PromptPreset | null
    showApply?: boolean
  }>(),
  { showApply: true }
)

const emit = defineEmits<{
  close: []
  apply: [preset: PromptPreset]
}>()

const { t } = useI18n()
const store = usePresetStore()
const userStore = useUserStore()
const { copyText } = useCopyText()
const forking = ref(false)
const generatingCover = ref(false)

/** 官方卡封面生成入口：仅管理员可见（AI 生图，覆盖旧封面） */
const canGenerateCover = computed(() => !!props.preset?.is_official && userStore.isAdmin)

/** 特效/运镜类型走动态封面（视频） */
const isVideoCoverPreset = computed(() =>
  !!props.preset && ['effect', 'camera'].includes(props.preset.type)
)

// 切换到其他预设时重置生成中状态（生成请求仍在后台进行，完成后写回原预设）
watch(
  () => props.preset?.id,
  () => {
    generatingCover.value = false
  }
)

const applyableText = computed(() => {
  const p = props.preset
  if (!p) return ''
  if (p.type === 'style' || p.type === 'effect') {
    return p.prompt_config?.suffix || p.prompt_text || ''
  }
  if (p.type === 'script') return p.script_text || ''
  if (p.type === 'prompt') return p.prompt_text || ''
  return ''
})

function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.plaza.typeCamera',
    prompt: 'presets.plaza.typePrompt',
    style: 'presets.plaza.typeStyle',
    effect: 'presets.plaza.typeEffect',
    script: 'presets.plaza.typeScript',
  }
  return keyMap[type] ? t(keyMap[type]) : type
}

function typeIcon(type: string): Component {
  const map: Record<string, Component> = {
    style: Brush,
    effect: MagicStick,
    camera: VideoCamera,
    prompt: EditPen,
    script: Document,
  }
  return map[type] || Brush
}

async function onToggleFavorite() {
  if (!props.preset) return
  try {
    await store.toggleFavorite(props.preset)
  } catch {
    /* 错误已由拦截器提示 */
  }
}

async function onFork() {
  if (!props.preset) return
  forking.value = true
  try {
    await forkPreset(props.preset.id)
    ElMessage.success(t('presets.plaza.forkSuccess'))
  } catch {
    /* 错误已由拦截器提示 */
  } finally {
    forking.value = false
  }
}

/** AI 生成封面（管理员）：点击时捕获目标预设，生成完成后写回原对象——
 * 即使期间切换/关闭了详情弹层，封面也落到正确的预设上（后端异步落库）。
 * 特效/运镜返回 cover_video（动态封面），其余返回 cover_image */
async function onGenerateCover() {
  const target = props.preset
  if (!target) return
  generatingCover.value = true
  try {
    const res = await generatePresetCover(target.id)
    if (res.cover_video) {
      target.cover_video = res.cover_video
      ElMessage.success(t('presets.plaza.coverVideoGenerated'))
    } else if (res.cover_image) {
      target.cover_image = res.cover_image
      ElMessage.success(t('presets.plaza.coverGenerated'))
    }
  } catch {
    /* 错误已由拦截器提示 */
  } finally {
    if (props.preset?.id === target.id) {
      generatingCover.value = false
    }
  }
}
</script>

<style scoped>
.detail-body {
  display: flex;
  gap: 20px;
}

.detail-cover {
  width: 240px;
  flex-shrink: 0;
  aspect-ratio: 3 / 4;
  border-radius: 10px;
  overflow: hidden;
  background: var(--el-fill-color-light);
}

.detail-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.detail-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  border-radius: 10px;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #7f7fd5, #86a8e7 55%, #91eae4);
}

.detail-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.official-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 400;
  color: var(--el-color-primary);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 4px;
  padding: 0 5px;
  margin-left: 6px;
  vertical-align: 2px;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.detail-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-type {
  color: var(--el-color-primary);
}

.detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.detail-prompt {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 10px 12px;
}

.prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.prompt-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 140px;
  overflow-y: auto;
  font-family: inherit;
}
</style>

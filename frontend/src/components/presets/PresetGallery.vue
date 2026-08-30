<!-- =====================================================
     PresetGallery — 统一预设广场画廊（核心组件）
     - 主 tab：广场 / 我的收藏 / 最近使用
     - 类型 chips（按 context 过滤）+ 分类 chips + 搜索 + 排序
     - 卡片网格：封面 / 名称 / 作者 / 使用数 / 收藏星标 / 官方角标
     - 点击卡片打开详情弹层，应用动作向上 emit
     ===================================================== -->

<template>
  <div class="preset-gallery">
    <!-- 顶部：主 tab + 搜索 -->
    <div class="gallery-header">
      <el-radio-group v-model="activeTab" class="main-tabs" @change="onTabChange">
        <el-radio-button value="plaza">{{ t('presets.plaza.tabPlaza') }}</el-radio-button>
        <el-radio-button value="favorites">{{ t('presets.plaza.tabFavorites') }}</el-radio-button>
        <el-radio-button value="recent">{{ t('presets.plaza.tabRecent') }}</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="searchText"
        class="search-input"
        :placeholder="t('presets.plaza.searchPlaceholder')"
        :prefix-icon="Search"
        clearable
        @input="onSearchInput"
      />
    </div>

    <!-- 类型 chips -->
    <div class="chips-row">
      <button
        v-for="opt in typeOptions"
        :key="'type-' + (opt.value ?? 'all')"
        type="button"
        class="chip"
        :class="{ active: store.presetType === opt.value }"
        @click="onTypeClick(opt.value)"
      >
        {{ opt.label }}
      </button>

      <span class="chips-spacer" />

      <el-select
        v-if="store.tab === 'plaza'"
        :model-value="store.sort"
        size="small"
        style="width: 92px"
        @change="(v: string) => store.setSort(v as any)"
      >
        <el-option :label="t('presets.plaza.sortNew')" value="new" />
        <el-option :label="t('presets.plaza.sortHot')" value="hot" />
        <el-option :label="t('presets.plaza.sortName')" value="name" />
      </el-select>
    </div>

    <!-- 分类 chips（推荐 / 全部 / 按类型分类） -->
    <div class="chips-row" v-if="store.tab === 'plaza' && categoryOptions.length > 0">
      <button
        type="button"
        class="chip"
        :class="{ active: isRecommendActive }"
        @click="onRecommendClick"
      >
        {{ t('presets.plaza.recommend') }}
      </button>
      <button
        type="button"
        class="chip"
        :class="{ active: isCategoryClearActive }"
        @click="onCategoryClick(undefined)"
      >
        {{ t('presets.plaza.all') }}
      </button>
      <button
        v-for="cat in categoryOptions"
        :key="'cat-' + cat.value"
        type="button"
        class="chip"
        :class="{ active: store.category === cat.value }"
        @click="onCategoryClick(cat.value)"
      >
        {{ t(cat.key) }}
      </button>
    </div>

    <!-- 卡片网格 -->
    <div class="gallery-grid" v-loading="store.loading && store.items.length === 0">
      <div
        v-for="preset in store.items"
        :key="preset.id"
        class="preset-card"
        :class="{ 'is-mounted': isMountable(preset) && isMountedHere(preset) }"
        @click="detailPreset = preset"
      >
        <div class="card-cover">
          <!-- 特效/运镜：动态封面，悬停循环播放（静止显示首帧/图片封面） -->
          <video
            v-if="preset.cover_video"
            class="cover-video"
            :src="preset.cover_video"
            :poster="preset.cover_image || undefined"
            muted
            loop
            playsinline
            preload="metadata"
            @mouseenter="onCoverHover($event, true)"
            @mouseleave="onCoverHover($event, false)"
          ></video>
          <img
            v-else-if="preset.cover_image"
            :src="preset.cover_image"
            :alt="preset.name"
            loading="lazy"
          />
          <div v-else class="cover-placeholder">
            <el-icon :size="34"><component :is="typeIcon(preset.type)" /></el-icon>
          </div>
          <span class="type-badge">{{ typeLabel(preset.type) }}</span>
          <button
            type="button"
            class="fav-btn"
            :class="{ active: preset.is_favorite }"
            @click.stop="onToggleFavorite(preset)"
          >
            <el-icon :size="16">
              <StarFilled v-if="preset.is_favorite" />
              <Star v-else />
            </el-icon>
          </button>
          <!-- 悬浮"使用"：一键挂载到当前生成模块（风格/特效/运镜） -->
          <button
            v-if="isMountable(preset)"
            type="button"
            class="use-btn"
            :class="{ active: isMountedHere(preset) }"
            @click.stop="emit('apply', preset)"
          >
            {{ isMountedHere(preset) ? t('presets.plaza.mountedBadge') : t('presets.plaza.mountUse') }}
          </button>
        </div>
        <div class="card-info">
          <div class="card-name" :title="preset.name">
            {{ preset.name }}
            <span v-if="preset.is_official" class="official-badge">{{ t('presets.plaza.official') }}</span>
          </div>
          <div class="card-meta">
            <span class="meta-author">
              <el-icon :size="12"><User /></el-icon>
              {{ preset.author_nickname || t('presets.plaza.officialAuthor') }}
            </span>
            <span class="meta-usage">
              <el-icon :size="12"><View /></el-icon>
              {{ formatUsage(preset.usage_count) }}
            </span>
          </div>
        </div>
      </div>

      <el-empty
        v-if="!store.loading && store.items.length === 0"
        :description="t('presets.plaza.empty')"
        class="gallery-empty"
      />
    </div>

    <!-- 加载更多 -->
    <div class="load-more" v-if="store.hasMore">
      <el-button size="small" :loading="store.loading" @click="store.loadMore()">
        {{ t('presets.plaza.loadMore') }}
      </el-button>
    </div>

    <!-- 详情弹层 -->
    <PresetDetailDialog
      :preset="detailPreset"
      :show-apply="showApply"
      @close="detailPreset = null"
      @apply="onApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, type Component } from 'vue'
import { Search, Star, StarFilled, User, View, Brush, MagicStick, VideoCamera, EditPen, Document } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { usePresetStore, CONTEXT_TYPES } from '@/stores/presets'
import type { PromptPreset, PresetContext, PresetTab } from '@/types/preset'
import PresetDetailDialog from './PresetDetailDialog.vue'

const props = defineProps<{
  /** 上下文：决定可见类型与默认选中类型 */
  context: PresetContext
  /** 是否展示"应用"动作（管理页传 false） */
  showApply?: boolean
}>()

const emit = defineEmits<{
  apply: [preset: PromptPreset]
}>()

const { t } = useI18n()
const store = usePresetStore()

const activeTab = ref<PresetTab>('plaza')
const detailPreset = ref<PromptPreset | null>(null)
const searchText = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

// 类型选项（全部 + 上下文可见类型）
const typeOptions = computed(() => [
  { value: undefined as string | undefined, label: t('presets.plaza.all') },
  ...CONTEXT_TYPES[props.context].types.map((tp) => ({ value: tp, label: typeLabel(tp) })),
])

// 当前类型下的分类选项（value 为数据库存储的中文分类值）
const CATEGORY_OPTIONS: Record<string, { value: string; key: string }[]> = {
  style: [
    { value: '摄影写真', key: 'presets.plaza.catPhotography' },
    { value: '动漫游戏', key: 'presets.plaza.catAnime' },
    { value: '风格插画', key: 'presets.plaza.catIllust' },
    { value: '国风水墨', key: 'presets.plaza.catInk' },
  ],
  effect: [
    { value: '运镜', key: 'presets.plaza.catCameraMove' },
    { value: '氛围', key: 'presets.plaza.catMood' },
    { value: '转场', key: 'presets.plaza.catTransition' },
  ],
  camera: [],
  prompt: [],
  script: [],
}
const categoryOptions = computed(() =>
  store.presetType ? CATEGORY_OPTIONS[store.presetType] || [] : []
)

const isRecommendActive = computed(() => store.sort === 'hot' && !store.category)
const isCategoryClearActive = computed(() => store.sort !== 'hot' && !store.category)

function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.plaza.typeCamera',
    prompt: 'presets.plaza.typePrompt',
    style: 'presets.plaza.typeStyle',
    effect: 'presets.plaza.typeEffect',
    script: 'presets.plaza.typeScript',
    pipeline: 'presets.editor.typePipeline',
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

function formatUsage(count: number): string {
  if (count >= 10000) return `${(count / 10000).toFixed(1)}w`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`
  return String(count)
}

/** 是否支持挂载式使用（风格/特效/运镜一键挂载；script=复制、prompt=追加走详情） */
function isMountable(preset: PromptPreset): boolean {
  return ['style', 'effect', 'camera'].includes(preset.type)
}

/** 动态封面悬停播放 / 离开暂停并回到首帧 */
function onCoverHover(e: MouseEvent, play: boolean) {
  const el = e.currentTarget
  if (el instanceof HTMLVideoElement) {
    if (play) {
      el.play().catch(() => {})
    } else {
      el.pause()
      el.currentTime = 0
    }
  }
}

/** 当前上下文的挂载查询（admin 管理页不挂载，恒为 false） */
function isMountedHere(preset: PromptPreset): boolean {
  if (props.context === 'admin') return false
  return store.isMountedIn(props.context, preset.id)
}

async function onTabChange(tab: string | number | boolean | undefined) {
  searchText.value = ''
  activeTab.value = tab as PresetTab
  await store.setTab(activeTab.value)
}

async function onTypeClick(value: string | undefined) {
  await store.setType(value)
  // "全部"类型时默认回到推荐排序
  if (!value) await store.setSort('hot')
}

async function onRecommendClick() {
  await store.setCategory(undefined)
  await store.setSort('hot')
}

async function onCategoryClick(value: string | undefined) {
  await store.setCategory(value)
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    await store.setSearch(searchText.value)
  }, 300)
}

async function onToggleFavorite(preset: PromptPreset) {
  try {
    await store.toggleFavorite(preset)
  } catch {
    /* 错误已由 axios 拦截器提示 */
  }
}

function onApply(preset: PromptPreset) {
  detailPreset.value = null
  emit('apply', preset)
}

onMounted(async () => {
  store.tab = 'plaza'
  store.presetType = CONTEXT_TYPES[props.context].defaultType
  store.category = undefined
  store.q = ''
  searchText.value = ''
  store.sort = 'new'
  await store.refresh()
})
</script>

<style scoped>
.preset-gallery {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 320px;
}

.gallery-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.search-input {
  width: 280px;
}

.chips-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chips-spacer {
  flex: 1;
}

.chip {
  border: none;
  background: transparent;
  color: var(--agnes-text-secondary, #909399);
  font-size: 13px;
  padding: 5px 12px;
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.chip:hover {
  color: var(--el-color-primary);
  background: var(--el-fill-color-light);
}

.chip.active {
  color: #fff;
  background: var(--el-color-primary);
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 14px;
  min-height: 200px;
}

.preset-card {
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  transition: transform 0.15s, box-shadow 0.15s;
}

.preset-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--el-box-shadow-light);
}

.card-cover {
  position: relative;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: var(--el-fill-color-light);
}

.card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cover-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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

.type-badge {
  position: absolute;
  left: 8px;
  top: 8px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
}

.fav-btn {
  position: absolute;
  right: 8px;
  top: 8px;
  border: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #fff;
  background: rgba(0, 0, 0, 0.35);
  transition: all 0.15s;
}

.fav-btn:hover {
  background: rgba(0, 0, 0, 0.55);
}

.fav-btn.active {
  color: var(--el-color-warning);
}

/* 悬浮"使用"按钮：hover 时出现在封面底部 */
.use-btn {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%) translateY(6px);
  border: none;
  padding: 5px 16px;
  border-radius: 14px;
  font-size: 12px;
  cursor: pointer;
  color: #fff;
  background: var(--el-color-primary);
  opacity: 0;
  transition: all 0.15s;
  white-space: nowrap;
}

.preset-card:hover .use-btn {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.use-btn.active {
  background: var(--el-color-success);
}

.preset-card.is-mounted {
  border-color: var(--el-color-success);
}

.card-info {
  padding: 8px 10px 10px;
}

.card-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.official-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 400;
  color: var(--el-color-primary);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 4px;
  padding: 0 4px;
  margin-left: 4px;
  vertical-align: 1px;
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.meta-author,
.meta-usage {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}

.meta-author {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 4px 0 8px;
}

.gallery-empty {
  grid-column: 1 / -1;
}
</style>

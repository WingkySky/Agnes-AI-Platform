<!-- =====================================================
     作品广场视图 PlazaView（已接入 i18n 国际化）
     - 头部：标题 + 描述 + 类型筛选 Tab（全部/图片/视频）+ 排序选择器（最新/最热）
     - 网格：响应式 auto-fill 卡片墙，含缩略图、视频角标、作者、点赞、我的作品角标
     - 详情弹窗：左侧大图/视频播放器，右侧 Prompt/模型/参数/作者/时间/点赞/浏览
     - 分页：底部「加载更多」按钮（非无限滚动）
     - 点赞需登录，未登录提示「请先登录后再操作」
     - 组件名 PlazaView，用于 keep-alive 缓存
     ===================================================== -->

<template>
  <div class="plaza-view">
    <!-- 头部：标题 + 描述 -->
    <h2 class="page-title">{{ t('plaza.title') }}</h2>
    <p class="page-desc">{{ t('plaza.desc') }}</p>

    <!-- 筛选区：类型 Tab + 排序选择器 -->
    <div class="filter-wrap">
      <el-radio-group v-model="filterType" @change="reload">
        <el-radio-button value="all">{{ t('plaza.all') }}</el-radio-button>
        <el-radio-button value="image">{{ t('plaza.image') }}</el-radio-button>
        <el-radio-button value="video">{{ t('plaza.video') }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="sortType" class="sort-select" @change="reload">
        <el-option value="latest" :label="t('plaza.latest')" />
        <el-option value="popular" :label="t('plaza.popular')" />
      </el-select>
    </div>

    <!-- 首次加载中 -->
    <div v-if="loading && list.length === 0" class="state-box loading-state">
      <el-icon :size="32" class="spinner"><Loading /></el-icon>
      <div class="state-text">{{ t('common.loading') }}</div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="list.length === 0" class="state-box empty-state">
      <el-icon :size="48"><Picture /></el-icon>
      <p class="state-text">{{ t('plaza.emptyTip') }}</p>
    </div>

    <!-- 作品网格 -->
    <div v-else class="plaza-grid">
      <div
        v-for="work in list"
        :key="work.id"
        class="plaza-card"
        @click="openDetail(work)">
        <div class="card-thumb">
          <!-- 模糊背景层：放大铺满，填充留白区域（所有卡片都有） -->
          <div
            v-if="work.type === 'image' || (work.type === 'video' && !thumbFailed[work.id])"
            class="img-bg-blur"
            :style="{
              backgroundImage: work.type === 'image'
                ? `url(${work.result_url})`
                : `url(/api/history/video/${work.id}/thumbnail)`
            }"
          />

          <!-- 图片缩略图（带水印） -->
          <ImageWithWatermark
            v-if="work.type === 'image'"
            :src="work.result_url ?? ''"
            :alt="work.prompt"
            :img-class="'card-img-contain'"
            loading="lazy"
            fit="cover" />
          <!-- 视频缩略图：首帧静态图 + 悬停 GIF 动态预览 -->
          <div
            v-else
            class="video-thumb"
            @mouseenter="onVideoCardHover(work)"
            @mouseleave="onVideoCardLeave(work)">
            <!-- 首帧缩略图（静态） -->
            <img
              v-if="!thumbFailed[work.id]"
              :src="`/api/history/video/${work.id}/thumbnail`"
              :alt="work.prompt"
              class="card-img-contain"
              loading="lazy"
              @error="thumbFailed[work.id] = true" />
            <div v-else class="thumb-placeholder">
              <el-icon :size="40"><VideoPlay /></el-icon>
            </div>
            <!-- 悬停时的 GIF 动态预览 -->
            <img
              v-if="hoveredVideoId === work.id && videoPreviews[work.id]"
              :src="videoPreviews[work.id]"
              :alt="work.prompt"
              class="video-preview-gif"
            />
            <!-- 视频播放蒙层图标 -->
            <div class="video-play-overlay">
              <el-icon :size="32"><VideoPlay /></el-icon>
            </div>
          </div>

          <!-- 视频类型角标 -->
          <div v-if="work.type === 'video'" class="type-badge">
            <el-icon><VideoPlay /></el-icon>
          </div>
          <!-- 我的作品角标 -->
          <div v-if="work.is_mine" class="mine-badge">{{ t('plaza.myWork') }}</div>

          <!-- 底部信息条：作者（左）+ 点赞（右） -->
          <div class="card-overlay">
            <span class="author">
              <el-avatar :size="24" :src="avatarFullUrl(work.author_avatar_url)" :icon="UserFilled" />
              <span class="author-name">{{ work.author_nickname || t('plaza.anonymous') }}</span>
            </span>
            <div
              class="like-btn"
              :class="{ liked: work.is_liked }"
              @click.stop="toggleLike(work)">
              <el-icon><StarFilled v-if="work.is_liked" /><Star v-else /></el-icon>
              <span class="like-count">{{ work.likes_count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载更多 / 没有更多 -->
    <div v-if="list.length > 0" class="load-more-wrap">
      <el-button
        v-if="hasMore"
        type="primary"
        :loading="loading"
        :icon="ArrowDown"
        @click="loadMore">
        {{ t('plaza.loadMore') }}
      </el-button>
      <span v-else class="no-more">{{ t('plaza.noMore') }}</span>
    </div>

    <!-- 详情弹窗：左媒体 + 右信息 -->
    <el-dialog
      v-model="detailVisible"
      :title="t('plaza.detail')"
      width="80%"
      top="5vh"
      destroy-on-close
      class="plaza-detail-dialog">
      <div v-if="detail" class="detail-content">
        <!-- 左：大图 / 视频播放器 -->
        <div class="detail-media">
          <ImageWithWatermark
            v-if="detail.type === 'image'"
            :src="detail.result_url ?? ''"
            :alt="detail.prompt"
            :img-class="'detail-image'"
            fit="contain" />
          <!-- 视频：result_url 为公开 CDN，<video> 可直接播放（代理流需鉴权无法携带 JWT） -->
          <video
            v-else
            :src="detail.result_url ?? ''"
            :poster="detail.type === 'video' && !thumbFailed[detail.id] ? `/api/history/video/${detail.id}/thumbnail` : ''"
            controls
            playsinline
            preload="metadata" />
        </div>

        <!-- 右：详情信息 -->
        <div class="detail-info">
          <!-- Prompt + 复制按钮 -->
          <div class="info-block">
            <div class="info-label-row">
              <span class="info-label">Prompt</span>
              <el-button
                size="small"
                link
                type="primary"
                :icon="CopyDocument"
                @click="copyText(detail.prompt, t('plaza.copied'))">
                {{ t('plaza.copyPrompt') }}
              </el-button>
            </div>
            <div class="prompt-text">{{ detail.prompt }}</div>
          </div>

          <!-- 元信息：作者 / 模型 / 模式 / 时间 -->
          <div class="info-row author-row" v-if="detail.author_nickname">
            <span class="info-label">{{ t('plaza.by') }}</span>
            <el-avatar :size="24" :src="avatarFullUrl(detail.author_avatar_url)" :icon="UserFilled" />
            <span class="info-value">{{ detail.author_nickname }}</span>
          </div>
          <div class="info-row" v-if="detail.model">
            <span class="info-label">Model</span>
            <span class="info-value">{{ detail.model }}</span>
          </div>
          <div class="info-row" v-if="detail.mode">
            <span class="info-label">Mode</span>
            <span class="info-value">{{ detail.mode }}</span>
          </div>
          <div class="info-row" v-if="detail.public_shared_at">
            <el-icon class="row-icon"><Clock /></el-icon>
            <span class="info-value">{{ formatTime(detail.public_shared_at) }}</span>
          </div>

          <!-- 参数（折叠展示原始 JSON） -->
          <div class="info-block" v-if="detail.params">
            <div class="info-label-row">
              <span class="info-label">Params</span>
              <el-button
                size="small"
                link
                type="primary"
                :icon="CopyDocument"
                @click="copyText(formatParams(detail.params), t('plaza.copied'))">
                {{ t('plaza.copyParams') }}
              </el-button>
            </div>
            <pre class="params-text">{{ formatParams(detail.params) }}</pre>
          </div>

          <!-- 统计：点赞 + 浏览 -->
          <div class="stats-row">
            <el-button
              :type="detail.is_liked ? 'primary' : 'default'"
              :icon="detail.is_liked ? StarFilled : Star"
              @click="toggleLike(detail)">
              {{ t('plaza.likes') }} {{ detail.likes_count }}
            </el-button>
            <span class="stat-views">
              <el-icon><View /></el-icon>
              {{ t('plaza.views') }} {{ detail.views_count }}
            </span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading, Picture, VideoPlay, User, UserFilled, Star, StarFilled,
  CopyDocument, View, ArrowDown, Clock,
} from '@element-plus/icons-vue'
import {
  getPlazaWorks, getPlazaWorkDetail, likePlazaWork, unlikePlazaWork,
  type PlazaWork,
} from '@/api/plaza'
import { useUserStore } from '@/stores/user'
import { useI18n } from '@/i18n'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'

// keep-alive 缓存匹配依赖组件名
defineOptions({ name: 'PlazaView' })

const { t } = useI18n()
const userStore = useUserStore()

// ---------- 列表状态 ----------
const list = ref<PlazaWork[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 24
const total = ref(0)
const filterType = ref<'all' | 'image' | 'video'>('all')
const sortType = ref<'latest' | 'popular'>('latest')
// 视频缩略图加载失败标记（按 work.id 隔离）
const thumbFailed = reactive<Record<number, boolean>>({})
// 视频 GIF 预览（hover 时动态加载）
const videoPreviews = reactive<Record<number, string>>({})
const previewLoading = reactive<Record<number, boolean>>({})
const hoveredVideoId = ref<number | null>(null)

// 是否还有更多：已加载数量小于总数
const hasMore = computed(() => list.value.length < total.value)

// ---------- 详情状态 ----------
const detailVisible = ref(false)
const detail = ref<PlazaWork | null>(null)

// ---------- 加载列表 ----------
/** 拉取一页数据；append=true 时追加到已有列表（加载更多） */
async function fetchPage(append = false) {
  loading.value = true
  try {
    const data = await getPlazaWorks({
      type: filterType.value,
      sort: sortType.value,
      page: page.value,
      page_size: pageSize,
    })
    if (append) {
      list.value.push(...(data.items || []))
    } else {
      list.value = data.items || []
    }
    total.value = data.total || 0
  } catch (e) {
    // 错误已由 axios 拦截器统一提示
  } finally {
    loading.value = false
  }
}

/** 筛选条件变化时重置分页并重新加载 */
function reload() {
  page.value = 1
  fetchPage(false)
}

/** 加载更多：页码 +1 后追加 */
function loadMore() {
  page.value += 1
  fetchPage(true)
}

// ---------- 详情弹窗 ----------
/** 打开详情：先用列表项数据展示，再拉取详情刷新计数（同时后端浏览数 +1） */
function openDetail(work: PlazaWork) {
  detail.value = work
  detailVisible.value = true
  // 后台拉取最新详情，刷新点赞/浏览数
  getPlazaWorkDetail(work.id)
    .then(fresh => {
      if (detail.value?.id === fresh.id) detail.value = fresh
      // 同步回列表项
      const idx = list.value.findIndex(w => w.id === fresh.id)
      if (idx >= 0) list.value[idx] = fresh
    })
    .catch(() => { /* 静默：仍使用列表项数据展示 */ })
}

// ---------- 视频悬停 GIF 预览 ----------
async function fetchBlobAsUrl(url: string): Promise<string> {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

async function loadVideoPreview(work: PlazaWork) {
  if (videoPreviews[work.id] || previewLoading[work.id]) return
  previewLoading[work.id] = true
  try {
    const url = `/api/history/video/${work.id}/preview`
    const blobUrl = await fetchBlobAsUrl(url)
    videoPreviews[work.id] = blobUrl
  } catch (e) {
    console.warn('[Plaza] 视频 GIF 预览加载失败 id=' + work.id, e)
  } finally {
    previewLoading[work.id] = false
  }
}

function onVideoCardHover(work: PlazaWork) {
  hoveredVideoId.value = work.id
  loadVideoPreview(work)
}

function onVideoCardLeave(_work: PlazaWork) {
  hoveredVideoId.value = null
}

// ---------- 点赞 / 取消点赞 ----------
/** 切换点赞状态；未登录时提示并拦截 */
async function toggleLike(work: PlazaWork) {
  if (!userStore.isAuthenticated) {
    ElMessage.warning(t('plaza.requireLogin'))
    return
  }
  // 乐观更新：先改 UI，失败再回滚
  const prevLiked = work.is_liked
  const prevCount = work.likes_count
  work.is_liked = !work.is_liked
  work.likes_count += work.is_liked ? 1 : -1
  try {
    const res = work.is_liked
      ? await likePlazaWork(work.id)
      : await unlikePlazaWork(work.id)
    work.is_liked = res.liked
    work.likes_count = res.likes_count
  } catch (e) {
    // 回滚
    work.is_liked = prevLiked
    work.likes_count = prevCount
  }
}

// ---------- 复制到剪贴板 ----------
/** 通用复制：优先 navigator.clipboard，降级 execCommand */
function copyText(text: string, successMsg: string) {
  if (!text) return
  const done = () => ElMessage.success(successMsg)
  const fail = () => ElMessage.error(t('preview.copyFailed'))
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done).catch(fail)
    return
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch (_) { ok = false }
  document.body.removeChild(ta)
  ok ? done() : fail()
}

/** 格式化参数对象为可读 JSON 字符串 */
function formatParams(params: Record<string, any> | undefined): string {
  if (!params) return ''
  try {
    return JSON.stringify(params, null, 2)
  } catch (_) {
    return String(params)
  }
}

/** 格式化时间字符串为本地可读形式 */
function formatTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString()
}

/**
 * 归一化广场作者头像 URL
 * - 空值：返回空字符串（由 el-avatar 回退到 :icon）
 * - 以 http(s):// 开头：直接使用
 * - 以 / 开头的相对路径（后端上传目录如 /uploads/avatars/xxx.jpg）：拼接 API_HOST
 */
function avatarFullUrl(rawUrl: string | null | undefined): string {
  if (!rawUrl) return ''
  if (/^https?:\/\//i.test(rawUrl)) return rawUrl
  if (rawUrl.startsWith('/')) {
    const apiHost = (import.meta.env.VITE_API_BASE_URL as string) || ''
    return `${apiHost}${rawUrl}`
  }
  return rawUrl
}

// ---------- 初始化 ----------
onMounted(() => {
  fetchPage(false)
})
</script>

<style scoped>
.plaza-view { color: var(--agnes-text-primary); }

/* 筛选区 */
.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--agnes-bg-inset);
  border-radius: 10px;
  border: 1px solid var(--agnes-border-faint);
}
.sort-select { width: 140px; }

/* 状态占位（加载中 / 空状态） */
.state-box {
  padding: 80px 20px;
  text-align: center;
  color: var(--agnes-text-faint);
}
.state-text { margin-top: 16px; font-size: 14px; }
.spinner { animation: plaza-spin 1.2s linear infinite; color: var(--agnes-primary); }
@keyframes plaza-spin { to { transform: rotate(360deg); } }

/* 响应式作品网格 */
.plaza-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}

/* 单个作品卡片：玻璃拟态 + 悬停浮起 */
.plaza-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  backdrop-filter: blur(8px);
}
.plaza-card:hover {
  transform: translateY(-4px) scale(1.01);
  box-shadow: 0 12px 36px var(--agnes-brand-glow);
  border-color: var(--agnes-primary-border);
}

/* 缩略图容器：固定宽高比，承载图片/视频首帧 + 蒙层 */
.card-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  background: var(--agnes-bg-base);
  overflow: hidden;
}

/* 模糊背景层：放大铺满，填充不同比例图片的留白区域 */
.img-bg-blur {
  position: absolute;
  inset: -10%;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  filter: blur(20px) saturate(1.2);
  opacity: 0.6;
  z-index: 0;
  transform: scale(1.1);
}

/* 图片/视频容器：撑满，层级在背景之上 */
.thumb-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  z-index: 1;
}

/* 前景图：完整展示，居中，不裁剪 */
.card-img-contain {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  transition: transform 0.3s ease;
}
.plaza-card:hover .card-img-contain {
  transform: scale(1.03);
}
.plaza-card:hover .img-bg-blur {
  transform: scale(1.15);
  transition: transform 0.5s ease;
}

/* 视频缩略图加载失败时的占位 */
.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-muted);
  background: var(--agnes-bg-dark-surface);
}

/* 视频播放蒙层：沉浸式媒体预览，固定深色半透明 */
.video-play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 15, 30, 0.35);
  color: rgba(255, 255, 255, 0.9);
  z-index: 2;
  transition: opacity 0.2s ease;
}
.plaza-card:hover .video-play-overlay { opacity: 0; }

/* 视频缩略图容器 */
.video-thumb {
  position: relative;
  width: 100%;
  height: 100%;
  z-index: 1;
}

/* 悬停时的 GIF 预览：覆盖在首帧上面 */
.video-preview-gif {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}
.video-thumb:hover .video-preview-gif {
  opacity: 1;
}

/* 视频类型角标 */
.type-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgba(10, 15, 30, 0.55);
  backdrop-filter: blur(4px);
  color: #c4a7ff;
  border: 1px solid rgba(196, 167, 255, 0.5);
  z-index: 2;
}

/* 我的作品角标 */
.mine-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: var(--agnes-brand-gradient);
  z-index: 2;
}

/* 底部信息条：作者 + 点赞（层级高于水印，确保可点击且不被遮挡） */
.card-overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 10px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  background: linear-gradient(to top, rgba(10, 15, 30, 0.78), rgba(10, 15, 30, 0));
  color: #fff;
  z-index: 10;
}

/* 带水印图片组件外层容器：撑满缩略图区域，层级低于底部信息条 */
.card-thumb > :deep(.img-with-watermark) {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  z-index: 1;
}
/* 水印文字/图片上移，避免被底部信息条和圆角截断 */
.card-thumb > :deep(.wm-position-bottom-right .wm-text),
.card-thumb > :deep(.wm-position-bottom-right .wm-image),
.card-thumb > :deep(.wm-position-bottom-left .wm-text),
.card-thumb > :deep(.wm-position-bottom-left .wm-image) {
  bottom: calc(var(--wm-margin, 20px) + 52px) !important;
}
.author {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
}
.author-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
}

/* 点赞按钮：触摸目标 ≥44px 通过 padding 保证 */
.like-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  min-height: 32px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(4px);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}
.like-btn:hover { background: rgba(255, 255, 255, 0.28); }
.like-btn.liked {
  color: #ffd98b;
  background: rgba(255, 184, 107, 0.32);
}

/* 加载更多 */
.load-more-wrap {
  margin-top: 28px;
  text-align: center;
}
.no-more {
  color: var(--agnes-text-faint);
  font-size: 13px;
}

/* 详情弹窗内容：左右两栏 */
.detail-content {
  display: flex;
  gap: 24px;
  align-items: stretch;
}
.detail-media {
  flex: 1 1 55%;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-bg-dark-surface);
  border-radius: 12px;
  overflow: hidden;
}
.detail-media img,
.detail-media video {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  display: block;
}
.detail-info {
  flex: 1 1 45%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  max-height: 70vh;
  padding-right: 4px;
}

/* 信息区块 */
.info-block {
  background: var(--agnes-bg-inset);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 10px;
  padding: 12px 14px;
}
.info-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.info-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--agnes-text-muted);
}
.info-value {
  font-size: 13px;
  color: var(--agnes-text-primary);
  word-break: break-all;
}
.info-row {
  display: flex;
  gap: 10px;
  font-size: 13px;
  line-height: 1.6;
  align-items: center;
}
.info-row .info-label { flex-shrink: 0; }
.row-icon { color: var(--agnes-text-muted); flex-shrink: 0; }

/* Prompt 文本 */
.prompt-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--agnes-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow-y: auto;
}

/* 参数 JSON 展示 */
.params-text {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--agnes-text-secondary);
  background: var(--agnes-bg-base);
  padding: 10px;
  border-radius: 8px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 统计行：点赞按钮 + 浏览数 */
.stats-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
}
.stat-views {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

/* 移动端适配：详情弹窗改为上下布局 */
@media (max-width: 768px) {
  .filter-wrap {
    flex-direction: column;
    align-items: stretch;
  }
  .sort-select { width: 100%; }
  .plaza-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }
  .detail-content {
    flex-direction: column;
    gap: 16px;
  }
  .detail-media,
  .detail-info {
    flex: 1 1 auto;
    max-height: none;
  }
  .detail-media img,
  .detail-media video {
    max-height: 50vh;
  }
}
</style>

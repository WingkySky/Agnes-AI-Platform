<!-- =====================================================
     首页 / 落地页
     - 未登录用户访问 / 看到此页
     - 已登录用户点击「进入工作台」跳转到 /images
     - 全屏沉浸式布局，不显示标题栏（App.vue 中通过路由名判断）
     - 支持深色/浅色主题（通过 CSS 变量自动响应）
     - 右上角提供主题切换 + 语言切换 + 登录/进入工作台按钮
     ===================================================== -->

<template>
  <div class="home-page">
    <!-- 背景装饰层 -->
    <div class="bg-decoration">
      <div class="blob blob-1"></div>
      <div class="blob blob-2"></div>
      <div class="blob blob-3"></div>
      <div class="grid-overlay"></div>
    </div>

    <!-- 顶部精简工具栏（仅首页用，独立于全局标题栏） -->
    <header class="home-topbar">
      <div class="home-brand">
        <el-icon class="brand-icon"><MagicStick /></el-icon>
        <span class="brand-text">{{ t('home.brand') }}</span>
      </div>
      <div class="home-topbar-right">
        <!-- 主题切换 -->
        <el-tooltip :content="themeStore.isDark ? t('theme.switchToLight') : t('theme.switchToDark')" placement="bottom">
          <button class="icon-btn" @click="themeStore.toggle()">
            <el-icon v-if="themeStore.isDark"><Sunny /></el-icon>
            <el-icon v-else><Moon /></el-icon>
          </button>
        </el-tooltip>
        <!-- 语言切换 -->
        <LanguageSwitcher />
        <!-- 登录 / 进入工作台 -->
        <el-button v-if="!userStore.isAuthenticated" type="primary" @click="router.push('/login')">
          {{ t('home.ctaLogin') }}
        </el-button>
        <el-button v-else type="primary" @click="router.push('/images')">
          {{ t('home.ctaEnter') }}
        </el-button>
      </div>
    </header>

    <!-- 主体内容 -->
    <main class="home-main">
      <!-- Hero 区 -->
      <section class="hero">
        <div class="hero-badge">
          <span class="badge-dot"></span>
          <span>{{ t('home.subtitle') }}</span>
        </div>
        <h1 class="hero-title">
          <span class="title-line">{{ t('home.tagline') }}</span>
        </h1>
        <p class="hero-desc">{{ t('home.subtitle') }}</p>
        <div class="hero-actions">
          <el-button v-if="!userStore.isAuthenticated" type="primary" size="large" @click="router.push('/login')">
            <el-icon><User /></el-icon>
            <span>{{ t('home.ctaLogin') }}</span>
          </el-button>
          <el-button v-else type="primary" size="large" @click="router.push('/images')">
            <el-icon><Grid /></el-icon>
            <span>{{ t('home.ctaEnter') }}</span>
          </el-button>
        </div>
      </section>

      <!-- 功能卡片 -->
      <section class="features">
        <div class="feature-card" @click="goFeature('images')">
          <div class="feature-icon feature-icon-1">
            <el-icon><Picture /></el-icon>
          </div>
          <h3 class="feature-title">{{ t('home.feature1Title') }}</h3>
          <p class="feature-desc">{{ t('home.feature1Desc') }}</p>
        </div>
        <div class="feature-card" @click="goFeature('videos')">
          <div class="feature-icon feature-icon-2">
            <el-icon><VideoPlay /></el-icon>
          </div>
          <h3 class="feature-title">{{ t('home.feature2Title') }}</h3>
          <p class="feature-desc">{{ t('home.feature2Desc') }}</p>
        </div>
        <div class="feature-card" @click="goFeature('chat')">
          <div class="feature-icon feature-icon-3">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <h3 class="feature-title">{{ t('home.feature3Title') }}</h3>
          <p class="feature-desc">{{ t('home.feature3Desc') }}</p>
        </div>
        <div class="feature-card" @click="goFeature('canvas')">
          <div class="feature-icon feature-icon-4">
            <el-icon><Grid /></el-icon>
          </div>
          <h3 class="feature-title">{{ t('home.feature4Title') }}</h3>
          <p class="feature-desc">{{ t('home.feature4Desc') }}</p>
        </div>
      </section>

      <!-- 底部说明 -->
      <footer class="home-footer">
        <span>{{ t('home.footerNote') }}</span>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import {
  Picture, VideoPlay, ChatDotRound, Grid, User, Sunny, Moon, MagicStick
} from '@element-plus/icons-vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

/** 点击功能卡片：未登录跳登录页，已登录跳对应功能页 */
function goFeature(target: 'images' | 'videos' | 'chat' | 'canvas') {
  if (userStore.isAuthenticated) {
    router.push(`/${target}`)
  } else {
    router.push({ path: '/login', query: { redirect: `/${target}` } })
  }
}
</script>

<style scoped>
/* =====================================================
 * 首页样式（沉浸式全屏布局，响应深色/浅色主题）
 * ===================================================== */
.home-page {
  position: relative;
  min-height: 100vh;
  width: 100%;
  background: var(--agnes-bg-base);
  color: var(--agnes-text-primary);
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif;
  transition: background 0.3s ease, color 0.3s ease;
}

/* ---- 背景装饰层 ---- */
.bg-decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.45;
  animation: float 18s ease-in-out infinite;
}
.blob-1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, var(--agnes-primary) 0%, transparent 70%);
  top: -120px;
  left: -100px;
}
.blob-2 {
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, var(--agnes-accent) 0%, transparent 70%);
  bottom: -100px;
  right: -80px;
  animation-delay: -6s;
}
.blob-3 {
  width: 360px;
  height: 360px;
  background: radial-gradient(circle, #ff8aa8 0%, transparent 70%);
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  opacity: 0.25;
  animation-delay: -12s;
}
@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -40px) scale(1.05); }
  66% { transform: translate(-20px, 30px) scale(0.95); }
}
.grid-overlay {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--agnes-border-faint) 1px, transparent 1px),
    linear-gradient(90deg, var(--agnes-border-faint) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
  opacity: 0.6;
}

/* ---- 顶部工具栏 ---- */
.home-topbar {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 40px;
}
.home-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-icon {
  font-size: 22px;
  color: var(--agnes-accent);
  filter: drop-shadow(0 0 10px rgba(120, 180, 255, 0.5));
}
.brand-text {
  font-size: 18px;
  font-weight: 700;
  background: var(--agnes-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.5px;
}
.home-topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--agnes-bg-chip);
  border: 1px solid var(--agnes-border);
  color: var(--agnes-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 16px;
}
.icon-btn:hover {
  background: var(--agnes-bg-hover);
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
  transform: translateY(-1px);
}

/* ---- 主体 ---- */
.home-main {
  position: relative;
  z-index: 5;
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 40px 60px;
  display: flex;
  flex-direction: column;
  gap: 80px;
}

/* ---- Hero 区 ---- */
.hero {
  text-align: center;
  padding: 60px 0 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: var(--agnes-bg-chip);
  border: 1px solid var(--agnes-border);
  border-radius: 999px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
  backdrop-filter: blur(8px);
}
.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--agnes-primary);
  box-shadow: 0 0 8px var(--agnes-primary);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.2); }
}
.hero-title {
  margin: 0;
  font-size: clamp(40px, 6vw, 72px);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.02em;
}
.title-line {
  background: var(--agnes-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero-desc {
  margin: 0;
  font-size: 18px;
  color: var(--agnes-text-muted);
  max-width: 600px;
  line-height: 1.6;
}
.hero-actions {
  margin-top: 16px;
}

/* ---- 功能卡片 ---- */
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
}
.feature-card {
  position: relative;
  padding: 28px 24px;
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  cursor: pointer;
  transition: all 0.3s ease;
  overflow: hidden;
}
.feature-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent 0%, var(--agnes-nav-hover-bg) 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
}
.feature-card:hover {
  transform: translateY(-4px);
  border-color: var(--agnes-primary);
  box-shadow: 0 12px 32px var(--agnes-primary-border-faint);
}
.feature-card:hover::before {
  opacity: 1;
}
.feature-card > * {
  position: relative;
  z-index: 1;
}
.feature-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  font-size: 24px;
  color: #fff;
  margin-bottom: 16px;
}
.feature-icon-1 {
  background: linear-gradient(135deg, var(--agnes-primary) 0%, var(--agnes-primary-hover) 100%);
  box-shadow: 0 6px 16px var(--agnes-primary-border);
}
.feature-icon-2 {
  background: linear-gradient(135deg, var(--agnes-accent-soft) 0%, var(--agnes-accent) 100%);
  box-shadow: 0 6px 16px var(--agnes-primary-border);
}
.feature-icon-3 {
  background: linear-gradient(135deg, #ff8aa8 0%, #ff6b9d 100%);
  box-shadow: 0 6px 16px rgba(255, 138, 168, 0.35);
}
.feature-icon-4 {
  background: linear-gradient(135deg, #ffd28a 0%, #ffb86c 100%);
  box-shadow: 0 6px 16px rgba(255, 210, 138, 0.35);
}
.feature-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 700;
  color: var(--agnes-text-primary);
}
.feature-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--agnes-text-muted);
}

/* ---- 底部 ---- */
.home-footer {
  text-align: center;
  font-size: 12px;
  color: var(--agnes-text-faint);
  padding: 20px 0;
  border-top: 1px solid var(--agnes-border-faint);
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .home-topbar {
    padding: 16px 20px;
  }
  .home-main {
    padding: 20px 20px 40px;
    gap: 48px;
  }
  .hero {
    padding: 30px 0 20px;
  }
  .features {
    grid-template-columns: 1fr;
  }
}
</style>

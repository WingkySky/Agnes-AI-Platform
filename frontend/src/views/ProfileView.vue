<!-- =====================================================
     个人中心页
     - 头像上传（支持 JPG/PNG/WebP/GIF，最大 2MB）
     - 个人资料编辑（邮箱）
     - 只读信息：用户名、角色、注册时间、最近登录
     - 不含积分模块（顶部栏已有积分 chip）
     ===================================================== -->

<template>
  <div class="profile-page">
    <!-- 页面标题 -->
    <header class="page-header">
      <h2 class="page-title">
        <el-icon><UserFilled /></el-icon>
        {{ t('profile.title') }}
      </h2>
      <p class="page-subtitle">{{ t('profile.subtitle') }}</p>
    </header>

    <div class="profile-grid">
      <!-- ============ 头像区 ============ -->
      <section class="profile-card avatar-card">
        <h3 class="card-title">{{ t('profile.avatarTitle') }}</h3>

        <div class="avatar-wrapper">
          <el-avatar :size="120" :src="avatarFullUrl" :icon="UserFilled" />
          <!-- 悬浮遮罩：点击触发文件选择 -->
          <button class="avatar-overlay" @click="triggerFilePicker" :disabled="avatarUploading">
            <el-icon v-if="!avatarUploading"><Camera /></el-icon>
            <el-icon v-else class="loading-icon"><Loading /></el-icon>
            <span>{{ avatarUploading ? t('profile.avatarUploading') : (hasAvatar ? t('profile.avatarChange') : t('profile.avatarUpload')) }}</span>
          </button>
        </div>

        <p class="avatar-hint">{{ t('profile.avatarHint') }}</p>

        <!-- 隐藏的文件输入 -->
        <input
          ref="fileInputRef"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          style="display: none"
          @change="handleAvatarChange"
        />
      </section>

      <!-- ============ 个人资料区 ============ -->
      <section class="profile-card info-card">
        <h3 class="card-title">{{ t('profile.profileTitle') }}</h3>

        <el-form label-position="top" class="profile-form">
          <!-- 用户名（只读） -->
          <el-form-item :label="t('profile.username')">
            <el-input :model-value="userStore.username" disabled>
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>

          <!-- 邮箱（可编辑） -->
          <el-form-item :label="t('profile.email')">
            <el-input
              v-model="emailValue"
              :placeholder="t('profile.emailPlaceholder')"
              clearable
            >
              <template #prefix><el-icon><Message /></el-icon></template>
            </el-input>
          </el-form-item>

          <!-- 角色（只读） -->
          <el-form-item :label="t('profile.role')">
            <el-tag :type="userStore.isAdmin ? 'danger' : 'info'" effect="plain">
              {{ userStore.isAdmin ? t('profile.roleAdmin') : t('profile.roleUser') }}
            </el-tag>
          </el-form-item>

          <!-- 注册时间（只读） -->
          <el-form-item :label="t('profile.createdAt')">
            <span class="readonly-text">{{ formatTime(userStore.user?.created_at) }}</span>
          </el-form-item>

          <!-- 最近登录（只读） -->
          <el-form-item :label="t('profile.lastLoginAt')">
            <span class="readonly-text">{{ formatTime(userStore.user?.last_login_at) }}</span>
          </el-form-item>

          <!-- 保存按钮 -->
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!emailDirty"
              @click="handleSaveProfile"
            >
              <el-icon><Check /></el-icon>
              {{ saving ? t('profile.saving') : t('profile.save') }}
            </el-button>
          </el-form-item>
        </el-form>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  UserFilled, User, Message, Camera, Loading, Check,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()

// ============ 头像上传 ============
const fileInputRef = ref<HTMLInputElement | null>(null)
const avatarUploading = ref(false)

// 头像完整 URL（后端返回的是 /uploads/avatars/xxx.jpg 相对路径）
const avatarFullUrl = computed(() => userStore.avatarUrl || '')
const hasAvatar = computed(() => !!userStore.avatarUrl)

function triggerFilePicker() {
  fileInputRef.value?.click()
}

async function handleAvatarChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  // 清空 input 的 value，方便下次选择同一文件
  input.value = ''
  if (!file) return

  // 前端预校验：类型
  const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
  if (!allowedTypes.includes(file.type)) {
    ElMessage.error(t('profile.avatarUploadFailed') + '：' + file.type)
    return
  }
  // 前端预校验：大小 2MB
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error(t('profile.avatarUploadFailed'))
    return
  }

  avatarUploading.value = true
  try {
    await userStore.uploadUserAvatar(file)
    ElMessage.success(t('profile.avatarUploadSuccess'))
  } catch (e) {
    ElMessage.error(t('profile.avatarUploadFailed'))
  } finally {
    avatarUploading.value = false
  }
}

// ============ 个人资料编辑 ============
const emailValue = ref<string>(userStore.user?.email || '')
const saving = ref(false)

// 切换用户时（登出/登录其他账号）同步邮箱字段，避免残留上一个用户的邮箱
// ProfileView 被 keep-alive 缓存，组件不会重建，需手动监听
watch(() => userStore.user?.email, (newEmail) => {
  emailValue.value = newEmail || ''
})

// 邮箱是否被修改（与原值不同时才允许保存）
const emailDirty = computed(() => (emailValue.value || '') !== (userStore.user?.email || ''))

async function handleSaveProfile() {
  if (!emailDirty.value) return
  saving.value = true
  try {
    await userStore.updateProfile({ email: emailValue.value || null })
    ElMessage.success(t('profile.saveSuccess'))
  } catch (e) {
    ElMessage.error(t('profile.saveFailed'))
  } finally {
    saving.value = false
  }
}

// ============ 工具函数 ============
function formatTime(iso?: string | null): string {
  if (!iso) return t('profile.notSet')
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return t('profile.notSet')
    return d.toLocaleString()
  } catch {
    return t('profile.notSet')
  }
}
</script>

<style scoped>
/* =====================================================
 * 个人中心页样式（依赖 CSS 变量，自动响应深色/浅色主题）
 * ===================================================== */
.profile-page {
  max-width: 960px;
  margin: 0 auto;
}

/* ---- 页面标题 ---- */
.page-header {
  margin-bottom: 24px;
}
.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--agnes-text-primary);
}
.page-title .el-icon {
  color: var(--agnes-primary);
}
.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

/* ---- 卡片网格：左侧头像，右侧资料 ---- */
.profile-grid {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  align-items: start;
}
@media (max-width: 768px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}

/* ---- 通用卡片 ---- */
.profile-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 14px;
  padding: 24px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.card-title {
  margin: 0 0 18px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

/* ---- 头像区 ---- */
.avatar-wrapper {
  position: relative;
  width: 120px;
  height: 120px;
  margin: 0 auto 14px;
  border-radius: 50%;
  overflow: hidden;
}
.avatar-wrapper :deep(.el-avatar) {
  width: 100%;
  height: 100%;
  border: 2px solid var(--agnes-border);
}
.avatar-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: rgba(10, 15, 30, 0.55);
  color: #fff;
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s ease;
  cursor: pointer;
  border: none;
  padding: 0;
}
.avatar-overlay:hover {
  opacity: 1;
}
.avatar-overlay:disabled {
  cursor: wait;
  opacity: 1;
}
.avatar-overlay .el-icon {
  font-size: 20px;
}
.avatar-overlay .loading-icon {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.avatar-hint {
  margin: 0;
  text-align: center;
  font-size: 12px;
  color: var(--agnes-text-faint);
  line-height: 1.5;
}

/* ---- 资料表单 ---- */
.profile-form {
  max-width: 480px;
}
.profile-form :deep(.el-form-item) {
  margin-bottom: 18px;
}
.profile-form :deep(.el-form-item__label) {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  padding-bottom: 4px;
}
.readonly-text {
  font-size: 14px;
  color: var(--agnes-text-primary);
  line-height: 32px;
}
</style>

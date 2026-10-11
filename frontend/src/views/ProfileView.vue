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

          <!-- 昵称（可编辑，用于广场等公开场景展示） -->
          <el-form-item :label="t('profile.nickname')">
            <el-input
              v-model="nicknameValue"
              :placeholder="t('profile.nicknamePlaceholder')"
              maxlength="32"
              show-word-limit
            >
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
            <p class="form-hint">{{ t('profile.nicknameHint') }}</p>
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
            <span class="readonly-text">{{ formatTime(userStore.user?.created_at, { emptyText: t('profile.notSet'), invalidText: t('profile.notSet') }) }}</span>
          </el-form-item>

          <!-- 最近登录（只读） -->
          <el-form-item :label="t('profile.lastLoginAt')">
            <span class="readonly-text">{{ formatTime(userStore.user?.last_login_at, { emptyText: t('profile.notSet'), invalidText: t('profile.notSet') }) }}</span>
          </el-form-item>

          <!-- 保存按钮 -->
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!profileDirty"
              @click="handleSaveProfile"
            >
              <el-icon><Check /></el-icon>
              {{ saving ? t('profile.saving') : t('profile.save') }}
            </el-button>
          </el-form-item>
        </el-form>
      </section>
    </div>

    <!-- ============ API 访问令牌（外部 Agent/CLI 经 MCP 接入） ============ -->
    <section class="profile-card pat-card">
      <div class="pat-header">
        <h3 class="card-title">{{ t('profile.patSection') }}</h3>
        <div class="pat-header-actions">
          <el-button size="small" @click="guideVisible = true">
            <el-icon><Guide /></el-icon>
            {{ t('profile.patGuide') }}
          </el-button>
          <el-button type="primary" size="small" @click="patDialogVisible = true">
            <el-icon><Plus /></el-icon>
            {{ t('profile.patNew') }}
          </el-button>
        </div>
      </div>
      <p class="pat-subtitle">{{ t('profile.patSubtitle') }}</p>

      <el-table :data="pats" size="small" class="pat-table">
        <el-table-column prop="name" :label="t('profile.patColName')" min-width="140" show-overflow-tooltip />
        <el-table-column :label="t('profile.patColPermission')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.permission === 'full' ? 'warning' : 'info'" effect="plain" size="small">
              {{ row.permission === 'full' ? t('profile.patPermissionFull') : t('profile.patPermissionReadonly') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('profile.patColCreatedAt')" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at, { emptyText: '-' }) }}</template>
        </el-table-column>
        <el-table-column :label="t('profile.patColLastUsed')" width="170">
          <template #default="{ row }">{{ row.last_used_at ? formatTime(row.last_used_at, { emptyText: t('profile.patNever') }) : t('profile.patNever') }}</template>
        </el-table-column>
        <el-table-column :label="t('profile.patColStatus')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.revoked_at ? 'danger' : 'success'" effect="plain" size="small">
              {{ row.revoked_at ? t('profile.patStatusRevoked') : t('profile.patStatusActive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="80" align="right">
          <template #default="{ row }">
            <el-button v-if="!row.revoked_at" link type="danger" size="small" @click="handleRevokePat(row)">
              {{ t('profile.patRevoke') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新建弹窗：创建后展示一次性明文 -->
      <el-dialog v-model="patDialogVisible" :title="t('profile.patCreateTitle')" width="460px" @closed="resetPatDialog">
        <template v-if="!createdToken">
          <el-form label-position="top">
            <el-form-item :label="t('profile.patNameLabel')">
              <el-input v-model="patName" :placeholder="t('profile.patNamePlaceholder')" maxlength="100" />
            </el-form-item>
            <el-form-item :label="t('profile.patPermissionLabel')">
              <el-radio-group v-model="patPermission">
                <el-radio value="readonly">{{ t('profile.patPermissionReadonly') }}</el-radio>
                <el-radio value="full">{{ t('profile.patPermissionFull') }}</el-radio>
              </el-radio-group>
              <p class="form-hint">{{ patPermission === 'full' ? t('profile.patPermissionFullHint') : t('profile.patPermissionReadonlyHint') }}</p>
            </el-form-item>
          </el-form>
        </template>
        <template v-else>
          <el-alert
            type="warning"
            :title="t('profile.patCreateSuccess')"
            :description="t('profile.patTokenOnce')"
            show-icon
            :closable="false"
            class="pat-token-alert"
          />
          <div class="pat-token-row">
            <code class="pat-token">{{ createdToken }}</code>
            <el-button size="small" @click="copyCreatedToken">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopy') }}
            </el-button>
          </div>
          <el-divider class="pat-divider" />
          <p class="pat-config-hint">{{ t('profile.patConfigHint') }}</p>
          <div class="pat-token-row">
            <code class="pat-token pat-token-tall">{{ createdConfig }}</code>
            <el-button size="small" type="primary" @click="copyCreatedConfig">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopyConfig') }}
            </el-button>
          </div>
        </template>
        <template #footer>
          <el-button @click="patDialogVisible = false">{{ t('common.close') }}</el-button>
          <el-button v-if="!createdToken" type="primary" :loading="patCreating" @click="handleCreatePat">
            {{ t('profile.patCreate') }}
          </el-button>
        </template>
      </el-dialog>

      <!-- 接入指引弹窗 -->
      <el-dialog v-model="guideVisible" :title="t('profile.patGuideTitle')" width="560px">
        <div class="pat-guide">
          <p class="pat-guide-step">{{ t('profile.patGuideStep1') }}</p>
          <div class="pat-token-row">
            <code class="pat-token">{{ mcpUrl }}</code>
            <el-button size="small" @click="copyMcpUrl">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopy') }}
            </el-button>
          </div>
          <p class="pat-guide-step">{{ t('profile.patGuideStep2') }}</p>
          <div class="pat-token-row">
            <code class="pat-token pat-token-tall pat-token-block">{{ guideConfig }}</code>
            <el-button size="small" @click="copyGuideConfig">
              <el-icon><CopyDocument /></el-icon>
              {{ t('profile.patCopy') }}
            </el-button>
          </div>
          <p class="pat-guide-step">{{ t('profile.patGuideStep3') }}</p>
          <el-alert type="info" :title="t('profile.patGuideTierNote')" :closable="false" class="pat-token-alert" />
          <p class="pat-guide-more">{{ t('profile.patGuideHint') }}</p>
        </div>
        <template #footer>
          <el-button type="primary" @click="guideVisible = false">{{ t('common.close') }}</el-button>
        </template>
      </el-dialog>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  UserFilled, User, Message, Camera, Loading, Check, Plus, CopyDocument, Guide,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { formatTime } from '@/lib/format'
import { useUserStore } from '@/stores/user'
import { useCopyText } from '@/composables/useCopyText'
import { useConfirm } from '@/composables/useConfirm'
import { createPat, listPats, revokePat, type PatInfo } from '@/api/pat'

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
const nicknameValue = ref<string>(userStore.user?.nickname || '')
const emailValue = ref<string>(userStore.user?.email || '')
const saving = ref(false)

// 切换用户时（登出/登录其他账号）同步字段，避免残留上一个用户的资料
// ProfileView 被 keep-alive 缓存，组件不会重建，需手动监听
watch(() => userStore.user?.nickname, (newNickname) => {
  nicknameValue.value = newNickname || ''
})
watch(() => userStore.user?.email, (newEmail) => {
  emailValue.value = newEmail || ''
})

// 资料是否被修改（任一字段与原值不同时才允许保存）
const profileDirty = computed(() => {
  const nicknameChanged = (nicknameValue.value || '') !== (userStore.user?.nickname || '')
  const emailChanged = (emailValue.value || '') !== (userStore.user?.email || '')
  return nicknameChanged || emailChanged
})

async function handleSaveProfile() {
  if (!profileDirty.value) return
  saving.value = true
  try {
    await userStore.updateProfile({
      nickname: nicknameValue.value || null,
      email: emailValue.value || null,
    })
    ElMessage.success(t('profile.saveSuccess'))
  } catch (e) {
    ElMessage.error(t('profile.saveFailed'))
  } finally {
    saving.value = false
  }
}

// ============ API 访问令牌（PAT，MCP 接入凭据） ============
const pats = ref<PatInfo[]>([])
const patDialogVisible = ref(false)
const patName = ref('')
const patPermission = ref<'readonly' | 'full'>('readonly')
const patCreating = ref(false)
const createdToken = ref('')

const { copyText } = useCopyText()
const { confirm } = useConfirm()

onMounted(loadPats)

async function loadPats() {
  try {
    pats.value = await listPats()
  } catch {
    ElMessage.error(t('profile.patLoadFailed'))
  }
}

function resetPatDialog() {
  patName.value = ''
  patPermission.value = 'readonly'
  createdToken.value = ''
}

async function handleCreatePat() {
  patCreating.value = true
  try {
    const created = await createPat(patName.value.trim() || 'CLI', patPermission.value)
    createdToken.value = created.token
    await loadPats()
  } catch {
    ElMessage.error(t('profile.patCreateFailed'))
  } finally {
    patCreating.value = false
  }
}

function copyCreatedToken() {
  copyText(createdToken.value, t('common.copied'))
}

// ============ 接入指引（端点按环境推导 + 配置 JSON 一键复制） ============
const guideVisible = ref(false)

// 端点 URL：dev 由后端直连（vite 只代理 /api，不代理 /mcp）；配了 API base 用之；生产同源
const mcpUrl = computed(() => {
  const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined
  if (envBase) return `${envBase.replace(/\/+$/, '')}/mcp`
  if (import.meta.env.DEV) return 'http://localhost:8000/mcp'
  return `${window.location.origin}/mcp`
})

function mcpConfigSnippet(token: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        'agnes-platform': {
          type: 'http',
          url: mcpUrl.value,
          headers: { Authorization: `Bearer ${token}` },
        },
      },
    },
    null,
    2,
  )
}

const guideConfig = computed(() => mcpConfigSnippet('agn_pat_<你的令牌>'))
const createdConfig = computed(() => mcpConfigSnippet(createdToken.value))

function copyMcpUrl() {
  copyText(mcpUrl.value, t('common.copied'))
}
function copyGuideConfig() {
  copyText(guideConfig.value, t('common.copied'))
}
function copyCreatedConfig() {
  copyText(createdConfig.value, t('profile.patConfigCopied'))
}

async function handleRevokePat(row: PatInfo) {
  await confirm(t('profile.patRevokeConfirm'))
  try {
    await revokePat(row.id)
    ElMessage.success(t('profile.patRevokeSuccess'))
    await loadPats()
  } catch {
    ElMessage.error(t('profile.patLoadFailed'))
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
.form-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}
.readonly-text {
  font-size: 14px;
  color: var(--agnes-text-primary);
  line-height: 32px;
}

/* ---- API 访问令牌 ---- */
.pat-card {
  margin-top: 20px;
}
.pat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pat-header .card-title {
  margin-bottom: 0;
  border-bottom: none;
  padding-bottom: 0;
}
.pat-subtitle {
  margin: 8px 0 14px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}
.pat-token-alert {
  margin-bottom: 12px;
}
.pat-token-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pat-token {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
  color: var(--agnes-text-primary);
}
.pat-token-tall {
  padding: 10px 12px;
  line-height: 1.5;
  white-space: pre;
  overflow-x: auto;
}
.pat-token-block {
  max-height: 180px;
  overflow-y: auto;
}
.pat-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pat-divider {
  margin: 14px 0 10px;
}
.pat-config-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.pat-guide-step {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.pat-guide .pat-guide-step:first-child {
  margin-top: 0;
}
.pat-guide .pat-token-row {
  margin-bottom: 16px;
}
.pat-guide-more {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--agnes-text-faint);
}
</style>

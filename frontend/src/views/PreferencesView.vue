<!-- =====================================================
     用户偏好设置页面
     - 展示并编辑用户的个人偏好设置
     - 所有登录用户均可访问（非管理员专属）
     - 集成 PreferencesPanel 组件
     ===================================================== -->

<template>
  <div class="preferences-view">
    <h2 class="page-title">
      <el-icon><StarFilled /></el-icon>
      {{ t('prefs.pageTitle') }}
    </h2>
    <p class="page-desc">{{ t('prefs.pageDesc') }}</p>

    <!-- 偏好设置面板 -->
    <PreferencesPanel />
  </div>
</template>

<script setup lang="ts">
import { StarFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import PreferencesPanel from '@/components/settings/PreferencesPanel.vue'

const { t } = useI18n()
</script>

<style scoped>
.preferences-view {
  max-width: 900px;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--agnes-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--agnes-text-muted);
  line-height: 1.6;
}
</style>

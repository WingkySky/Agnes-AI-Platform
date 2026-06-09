<!-- =====================================================
     LanguageSwitcher 语言切换器
     - 下拉展示当前语言，点击切换 zh-CN / en-US
     - 选择后持久化到 localStorage
     ===================================================== -->

<template>
  <div class="language-switcher">
    <el-dropdown trigger="click" @command="onSelect" :teleported="false">
    <el-button type="primary" link text-color="text--primary" size="small" class="switcher-btn">
      <el-icon><LocationFilled /></el-icon>
      <span class="current-label">{{ currentLabel }}</span>
      <el-icon class="caret-icon"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="loc in supportedLocales"
          :key="loc"
          :command="loc"
          :class="{ active: loc === currentLocale }"
        >
          <span class="option-label">{{ localeLabels[loc] }}</span>
          <el-icon v-if="loc === currentLocale" class="check-icon"><Check /></el-icon>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { LocationFilled, ArrowDown, Check } from '@element-plus/icons-vue'

const { t, locale, setLocale, supportedLocales, localeLabels } = useI18n()

const currentLocale = computed(() => locale.value)
// localeLabels 是常量对象（非 ref），直接按属性访问即可；访问 locale.value 触发响应式
const currentLabel = computed(() => {
  const l = locale.value
  return (localeLabels && localeLabels[l]) || l
})

function onSelect(command) {
  setLocale(command)
}
</script>

<style scoped>
.language-switcher {
  display: inline-flex;
  align-items: center;
}

.switcher-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  color: #c9d8f0;
  font-weight: 500;
  transition: all 0.2s ease;
  cursor: pointer;
}

.switcher-btn:hover {
  background: rgba(120, 170, 255, 0.15);
  color: #fff;
}

.switcher-btn .el-icon {
  font-size: 16px;
}

.caret-icon {
  font-size: 14px;
  opacity: 0.7;
}

.current-label {
  font-size: 13px;
}

.el-dropdown-menu__item.active .option-label {
  color: #409eff;
  font-weight: 500;
}

.check-icon {
  margin-left: 8px;
  color: #409eff;
  font-size: 14px;
}
</style>

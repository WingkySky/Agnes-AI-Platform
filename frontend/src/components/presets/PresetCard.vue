<!-- =====================================================
     PresetCard — 预设卡片组件
     - el-card 展示：名称、类型标签(el-tag)、分类、使用次数
     - 操作按钮：编辑/删除/设为公开
     - 点击卡片名称触发 detail 事件（查看详情抽屉）
     - 点击卡片其他区域触发 use 事件（应用预设）
     ===================================================== -->

<template>
  <el-card
    shadow="hover"
    class="preset-card"
    :body-style="{ padding: '16px' }"
    @click="emit('use', preset)"
  >
    <!-- 顶部：名称 + 公开标签 + 菜单 -->
    <div class="card-head">
      <span
        class="card-name"
        :title="preset.name"
        @click.stop="emit('detail', preset)"
      >{{ preset.name }}</span>
      <div class="card-badges">
        <el-tag v-if="preset.is_public" size="small" type="success" effect="plain">
          {{ t('presets.card.public') }}
        </el-tag>
        <el-dropdown trigger="click" @click.stop>
          <button type="button" class="card-menu-btn" @click.stop>
            <MoreFilled :size="14" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="emit('detail', preset)">
                {{ t('presets.detail.title') }}
              </el-dropdown-item>
              <el-dropdown-item @click="emit('edit', preset)">
                {{ t('presets.card.edit') }}
              </el-dropdown-item>
              <el-dropdown-item v-if="!preset.is_public" @click="emit('toggle-public', preset)">
                {{ t('presets.card.setPublic') }}
              </el-dropdown-item>
              <el-dropdown-item
                divided
                class="danger-item"
                @click="emit('delete', preset)"
              >
                {{ t('presets.card.delete') }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 描述 -->
    <p class="card-desc" v-if="preset.description">{{ preset.description }}</p>

    <!-- 标签行：类型 + 分类 + 使用次数 -->
    <div class="card-meta">
      <el-tag size="small" :type="typeTagType(preset.type)" effect="plain">
        {{ typeLabel(preset.type) }}
      </el-tag>
      <span class="meta-item">{{ preset.category || t('presets.card.defaultCategory') }}</span>
      <span class="meta-item">{{ t('presets.card.usageCount', { n: preset.usage_count || 0 }) }}</span>
    </div>

    <!-- 标签 -->
    <div class="card-tags" v-if="(preset.tags || []).length > 0">
      <el-tag
        v-for="tag in (preset.tags || []).slice(0, 4)"
        :key="tag"
        size="small"
        type="info"
        effect="plain"
      >
        {{ tag }}
      </el-tag>
      <span v-if="(preset.tags || []).length > 4" class="more-tag">
        +{{ preset.tags.length - 4 }}
      </span>
    </div>
    <!-- 底部操作行 -->
    <div class="card-actions" v-if="showFork">
      <slot name="actions">
        <el-button size="small" type="primary" plain @click.stop="emit('fork', preset)">
          {{ t('presets.card.fork') }}
        </el-button>
      </slot>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { MoreFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { PromptPreset } from '@/types/preset'

const { t } = useI18n()

defineProps<{
  preset: PromptPreset
  showFork?: boolean
}>()

const emit = defineEmits<{
  use: [preset: PromptPreset]
  detail: [preset: PromptPreset]
  edit: [preset: PromptPreset]
  delete: [preset: PromptPreset]
  'toggle-public': [preset: PromptPreset]
  fork: [preset: PromptPreset]
}>()

// 类型显示名（走 i18n）
function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.card.typeCamera',
    prompt: 'presets.card.typePrompt',
    style: 'presets.card.typeStyle',
    script: 'presets.card.typeScript',
    pipeline: 'presets.card.typePipeline',
  }
  return keyMap[type] ? t(keyMap[type]) : type
}

// 类型对应 el-tag 类型（视觉区分）
function typeTagType(type: string): string {
  const map: Record<string, string> = {
    camera: '',
    prompt: 'primary',
    style: 'warning',
    script: 'success',
    pipeline: 'danger',
  }
  return map[type] || 'info'
}
</script>

<style scoped>
.preset-card {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.preset-card:hover {
  transform: translateY(-2px);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

/* 卡片名称可点击查看详情 */
.card-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--agnes-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
  cursor: pointer;
}

.card-name:hover {
  color: var(--agnes-primary);
  text-decoration: underline;
}

.card-badges {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.card-menu-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  color: var(--agnes-text-tertiary);
  display: flex;
  align-items: center;
}

/* 修复：原 --agnes-fill-secondary 不存在，改用 --agnes-bg-hover */
.card-menu-btn:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.card-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--agnes-text-tertiary);
}

.meta-item {
  color: var(--agnes-text-tertiary);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.more-tag {
  font-size: 11px;
  color: var(--agnes-text-tertiary);
  line-height: 22px;
}

.card-actions {
  margin-top: 10px;
  padding-top: 10px;
  /* 修复：原 --agnes-border-light 不存在，改用 --agnes-border-faint */
  border-top: 1px solid var(--agnes-border-faint);
  display: flex;
  justify-content: flex-end;
}

:deep(.danger-item) {
  color: var(--el-color-danger);
}
</style>

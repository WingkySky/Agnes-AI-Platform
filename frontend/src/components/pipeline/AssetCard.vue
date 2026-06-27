<template>
  <el-card class="asset-card" shadow="hover" @click="$emit('click', asset)">
    <div class="card-cover">
      <ImageWithWatermark
        v-if="asset.reference_images?.length"
        :src="asset.reference_images[0]"
        :alt="asset.name"
      />
      <div v-else class="cover-placeholder">
        <el-icon><Picture /></el-icon>
      </div>
    </div>
    <div class="card-body">
      <div class="card-header">
        <span class="card-title">{{ asset.name }}</span>
        <el-tag size="small" type="info">{{ t(`assets.type.${asset.type}`) }}</el-tag>
      </div>
      <p class="card-desc">{{ asset.description || asset.visual_description }}</p>
      <div class="card-footer">
        <span class="use-count">{{ t('assets.fields.useCount') }}: {{ asset.use_count || 0 }}</span>
        <el-button
          v-permission="'pipeline:save_asset'"
          size="small"
          type="primary"
          text
          @click.stop="$emit('use', asset)"
        >
          {{ t('assets.useTip') }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n'
import { ElCard, ElTag, ElButton, ElIcon } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import type { Asset } from '@/types'

// 资产卡片：展示封面、名称、类型、描述、使用次数；点击卡片触发 click，点击使用按钮触发 use
defineProps<{
  asset: Asset
  selectable?: boolean
}>()

defineEmits<{
  click: [asset: Asset]
  use: [asset: Asset]
}>()

const { t } = useI18n()
</script>

<style scoped>
.asset-card {
  cursor: pointer;
  transition: transform 0.2s;
}
.asset-card:hover {
  transform: translateY(-2px);
}
.card-cover {
  aspect-ratio: 16 / 9;
  background: var(--agnes-bg-page);
  border-radius: 6px;
  overflow: hidden;
}
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-placeholder);
  font-size: 32px;
}
.card-body {
  padding: 12px 0 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.card-title {
  font-size: 14px;
  font-weight: 500;
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
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.use-count {
  font-size: 12px;
  color: var(--agnes-text-placeholder);
}
</style>

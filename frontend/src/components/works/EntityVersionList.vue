<!-- =====================================================
     实体版本列表（共用）：作品详情页实体弹层 + 画布实体卡弹层
     展示版本的表现图（缩略图 + 角色徽标）、采用位与「设为采用」
     ===================================================== -->

<template>
  <div class="entity-versions">
    <div v-for="v in versions" :key="v.id" class="version-row" :class="{ active: v.is_active }">
      <div class="thumbs">
        <div v-for="(img, i) in v.images" :key="img.asset_id" class="thumb">
          <img v-if="img.url" :src="img.url" :alt="roleLabel(img.role)" loading="lazy" />
          <span class="role-badge">{{ roleLabel(img.role) }}<template v-if="v.images.length > 1">·{{ i + 1 }}</template></span>
        </div>
      </div>
      <div class="version-meta">
        <span v-if="v.is_active" class="active-flag">{{ t('entityLib.active') }}</span>
        <span class="version-time">{{ formatDate(v.created_at) }}</span>
        <el-button v-if="!v.is_active" size="small" text type="primary" @click="emit('adopt', v.id)">
          {{ t('entityLib.adopt') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n'
import type { EntityVersion } from '@/api/workEntities'

defineProps<{ versions: EntityVersion[] }>()
const emit = defineEmits<{ adopt: [versionId: number] }>()
const { t } = useI18n()

function roleLabel(role: string): string {
  const key = role === 'design' ? 'entityLib.design' : role === 'turnaround' ? 'entityLib.turnaround' : 'entityLib.angle'
  return t(key)
}

function formatDate(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '-'
}
</script>

<style scoped>
.entity-versions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.version-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

.version-row.active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.thumbs {
  display: flex;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.thumb {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--el-fill-color-light);
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.role-badge {
  position: absolute;
  left: 0;
  bottom: 0;
  right: 0;
  font-size: 10px;
  line-height: 14px;
  text-align: center;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.version-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.active-flag {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 600;
}

.version-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>

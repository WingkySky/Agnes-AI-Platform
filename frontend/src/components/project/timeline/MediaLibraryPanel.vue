<!-- =====================================================
     素材库面板 MediaLibraryPanel
     - 左侧抽屉，4 类 Tab（视频/音频/帧图/BGM）
     - 每项 draggable=true，拖拽到时间线创建片段
     - 顶部 Tab 切换，底部缩略图列表
     ===================================================== -->

<template>
  <div class="media-library-panel">
    <div class="panel-header">
      <span class="header-title">📁 素材库</span>
      <el-button
        size="small"
        text
        :icon="ArrowLeftBold"
        @click="$emit('hide')"
        title="收起"
      />
    </div>

    <el-tabs v-model="activeTab" class="library-tabs">
      <el-tab-pane label="视频" name="videos">
        <div class="media-list">
          <div
            v-for="item in videos"
            :key="`v-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <img v-if="item.thumbnail_url" :src="item.thumbnail_url" :alt="item.name" />
              <el-icon v-else><VideoCamera /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!videos.length" description="暂无视频" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="音频" name="audios">
        <div class="media-list">
          <div
            v-for="item in audios"
            :key="`a-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <el-icon><Microphone /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!audios.length" description="暂无音频" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="帧图" name="frame_images">
        <div class="media-list">
          <div
            v-for="item in frameImages"
            :key="`f-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <img v-if="item.thumbnail_url" :src="item.thumbnail_url" :alt="item.name" />
              <el-icon v-else><Picture /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">静态图 · 3s</div>
            </div>
          </div>
          <el-empty v-if="!frameImages.length" description="暂无帧图" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="BGM" name="bgms">
        <div class="media-list">
          <div
            v-for="item in bgms"
            :key="`b-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <el-icon><Headset /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ item.meta?.mood }} · {{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!bgms.length" description="暂无 BGM" :image-size="60" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowLeftBold, VideoCamera, Microphone, Picture, Headset } from '@element-plus/icons-vue'
import type { MediaLibraryItem, MediaLibraryResponse } from '@/types/project'

const props = defineProps<{
  mediaLibrary: MediaLibraryResponse | null
}>()

const emit = defineEmits<{
  (e: 'hide'): void
  /** 拖拽开始时携带素材项 JSON */
  (e: 'drag-item', item: MediaLibraryItem): void
}>()

const activeTab = ref<'videos' | 'audios' | 'frame_images' | 'bgms'>('videos')

const videos = computed(() => props.mediaLibrary?.videos ?? [])
const audios = computed(() => props.mediaLibrary?.audios ?? [])
const frameImages = computed(() => props.mediaLibrary?.frame_images ?? [])
const bgms = computed(() => props.mediaLibrary?.bgms ?? [])

function formatDuration(ms: number): string {
  const seconds = ms / 1000
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function onDragStart(e: DragEvent, item: MediaLibraryItem) {
  if (!e.dataTransfer) return
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('application/json', JSON.stringify(item))
  emit('drag-item', item)
}
</script>

<style scoped>
.media-library-panel {
  width: 100%;
  height: 100%;
  background: var(--el-bg-color, #1e2128);
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color-light, #3a3d44);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #2a2d34);
}

.header-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.library-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.library-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
}

.media-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
}

.media-item {
  display: flex;
  gap: 8px;
  padding: 6px;
  border-radius: 4px;
  background: var(--el-fill-color-light, #2a2d34);
  cursor: grab;
  transition: background-color 0.15s;
}

.media-item:hover {
  background: var(--el-color-primary-light-9, #3a4eff20);
}

.media-item:active {
  cursor: grabbing;
}

.media-thumb {
  width: 48px;
  height: 36px;
  flex-shrink: 0;
  background: var(--el-fill-color-darker, #404448);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.media-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.media-thumb .el-icon {
  color: var(--el-text-color-placeholder);
  font-size: 16px;
}

.media-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.media-name {
  font-size: 12px;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.media-meta {
  font-size: 10px;
  color: var(--el-text-color-secondary);
}
</style>

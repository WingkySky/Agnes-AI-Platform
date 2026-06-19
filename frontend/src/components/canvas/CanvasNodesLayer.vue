<!-- =====================================================
     CanvasNodesLayer 节点渲染层
     - 遍历 canvas store 的 panels 数组
     - 每个节点在 CanvasNodeShell 通用外壳内渲染对应内容
     - 按 panel.type 动态分发到 nodes/ 下对应内容组件
     ===================================================== -->

<template>
  <div class="canvas-nodes-layer">
    <CanvasNodeShell
      v-for="panel in visiblePanels"
      :key="panel.id"
      :panel="panel"
      @action="handleNodeAction"
      @connect-start="(evt) => $emit('connect-start', evt)"
      @connect-end="(evt) => $emit('connect-end', evt)"
    >
      <!-- 文本节点 -->
      <TextNode
        v-if="panel.type === 'text'"
        :panel="panel"
        @update-content="(patch) => updatePanelContent(panel.id, patch)"
        @update-status="(s) => updatePanelStatus(panel.id, s)"
      />
      <!-- 图片节点 -->
      <ImageNode
        v-else-if="panel.type === 'image'"
        :panel="panel"
        @update-content="(patch) => updatePanelContent(panel.id, patch)"
        @update-status="(s) => updatePanelStatus(panel.id, s)"
      />
      <!-- 视频节点 -->
      <VideoNode
        v-else-if="panel.type === 'video'"
        :panel="panel"
        @update-content="(patch) => updatePanelContent(panel.id, patch)"
        @update-status="(s) => updatePanelStatus(panel.id, s)"
      />
      <!-- 对话节点 -->
      <ChatNode
        v-else-if="panel.type === 'chat'"
        :panel="panel"
        @update-content="(patch) => updatePanelContent(panel.id, patch)"
        @update-status="(s) => updatePanelStatus(panel.id, s)"
      />
      <!-- 配置节点 -->
      <ConfigNode
        v-else-if="panel.type === 'config'"
        :panel="panel"
        @update-content="(patch) => updatePanelContent(panel.id, patch)"
        @update-status="(s) => updatePanelStatus(panel.id, s)"
      />
      <!-- 分组框节点（简单展示分组信息） -->
      <div v-else-if="panel.type === 'frame'" class="frame-node">
        <div class="frame-node-title">{{ panel.content?.name || '分组框' }}</div>
        <div class="frame-node-subtitle">子节点：{{ (panel.content?.children || []).length }} 个</div>
      </div>
      <!-- 未知类型 -->
      <div v-else class="node-unknown">
        <el-icon :size="24"><Box /></el-icon>
        <span>节点类型：{{ panel.type }}</span>
      </div>
    </CanvasNodeShell>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Box } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'
import CanvasNodeShell from './CanvasNodeShell.vue'
import TextNode from './nodes/TextNode.vue'
import ImageNode from './nodes/ImageNode.vue'
import VideoNode from './nodes/VideoNode.vue'
import ChatNode from './nodes/ChatNode.vue'
import ConfigNode from './nodes/ConfigNode.vue'
/* 分组框节点内容（内联实现，简单展示分组信息） */

const store = useCanvasStore()
defineEmits(['node-action', 'connect-start', 'connect-end'])

/* 当前视口内可见的面板 */
const visiblePanels = computed(() => store.panels)

/* 更新 panel.content 的部分字段（深度合并，由 store 完成） */
function updatePanelContent(panelId, contentPatch) {
  if (!contentPatch || typeof contentPatch !== 'object') return
  store.updatePanel(panelId, { content: contentPatch })
}

/* 更新 panel.status —— 由子组件触发 status 更新时响应 */
function updatePanelStatus(panelId, status) {
  if (!status) return
  store.updatePanel(panelId, { status: status })
}

/* 节点级动作事件转发到上级组件 */
function handleNodeAction(evt) {
  // 由 CanvasNodeShell 发出，这里预留将来扩展
  console.debug('[CanvasNodesLayer] node action:', evt)
}

/* 分组框节点内容已改为内联模板（见上方 template 中 v-else-if="panel.type==='frame'" 部分） */
</script>

<style scoped>
.canvas-nodes-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.canvas-nodes-layer > * {
  pointer-events: auto;
}

.node-unknown {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 18px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 6px;
  color: #8ba3c9;
  font-size: 11px;
}

.frame-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  gap: 6px;
  color: #8ba3c9;
}
.frame-node-title {
  font-size: 13px;
  font-weight: 600;
  color: #e8eef7;
}
.frame-node-subtitle {
  font-size: 11px;
}
</style>

/* =====================================================
 * 右键上下文菜单组件
 * - 通过 ref 暴露 show(e, payload) / hide() 方法
 * - payload: { target: 'background'|'panel'|'connection', data: { panelId?, panel?, connectionId? } }
 * - 根据 target 渲染不同菜单项：
 *   · background: 全选 / 粘贴 / 居中视图 / 清空画布（popconfirm 确认）/ 添加分组框
 *   · panel: 通用（编辑/复制/删除/锁定/隐藏）+ 按 panel.type 显示节点级操作
 *   · connection: 删除连线
 * - 点击菜单项后 emit('panel-action', { type, panel? }) 并自动 hide
 * ===================================================== */

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="context-menu"
      :style="{ left: `${x}px`, top: `${y}px` }"
      @pointerdown.stop
      @click.stop
    >
      <!-- ============ 背景右键菜单 ============ -->
      <template v-if="target === 'background'">
        <div class="context-menu-item" @click="handleAction('selectAll')">
          <el-icon><Select /></el-icon>
          <span>全选</span>
        </div>
        <!-- 粘贴：无剪贴板内容时禁用 -->
        <div
          class="context-menu-item"
          :class="{ 'context-menu-item--disabled': !hasClipboard }"
          @click="hasClipboard && handleAction('paste')"
        >
          <el-icon><DocumentCopy /></el-icon>
          <span>粘贴</span>
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item" @click="handleAction('centerView')">
          <el-icon><FullScreen /></el-icon>
          <span>居中视图</span>
        </div>
        <div class="context-menu-item" @click="handleAction('addFrame')">
          <el-icon><Grid /></el-icon>
          <span>添加分组框</span>
        </div>
        <div class="context-menu-divider" />
        <!-- 清空画布：el-popconfirm 二次确认 -->
        <el-popconfirm
          title="确定清空画布？"
          confirm-button-text="确定"
          cancel-button-text="取消"
          @confirm="handleAction('clearCanvas')"
          @cancel="hide"
        >
          <template #reference>
            <div class="context-menu-item context-menu-item--danger">
              <el-icon><Delete /></el-icon>
              <span>清空画布</span>
            </div>
          </template>
        </el-popconfirm>
      </template>

      <!-- ============ 面板右键菜单 ============ -->
      <template v-else-if="target === 'panel'">
        <!-- 通用：编辑 / 复制 / 删除 -->
        <div class="context-menu-item" @click="handleAction('edit')">
          <el-icon><Edit /></el-icon>
          <span>编辑</span>
        </div>
        <div class="context-menu-item" @click="handleAction('duplicate')">
          <el-icon><CopyDocument /></el-icon>
          <span>复制</span>
        </div>
        <div class="context-menu-item context-menu-item--danger" @click="handleAction('delete')">
          <el-icon><Delete /></el-icon>
          <span>删除</span>
        </div>
        <div class="context-menu-divider" />
        <!-- 锁定/解锁：根据当前锁定状态切换文案 -->
        <div class="context-menu-item" @click="handleAction('lock')">
          <el-icon><component :is="isPanelLocked ? 'Unlock' : 'Lock'" /></el-icon>
          <span>{{ isPanelLocked ? '解锁' : '锁定' }}</span>
        </div>
        <!-- 隐藏：直接调 store.setPanelHidden -->
        <div class="context-menu-item" @click="handleHide">
          <el-icon><Hide /></el-icon>
          <span>隐藏</span>
        </div>

        <!-- 图片节点：裁剪 / 拆分 / 旋转 / 反推提示词 / 加入素材库 -->
        <template v-if="panelType === 'image'">
          <div class="context-menu-divider" />
          <div class="context-menu-item" @click="handleAction('crop')">
            <el-icon><Crop /></el-icon>
            <span>裁剪</span>
          </div>
          <div class="context-menu-item" @click="handleAction('split')">
            <el-icon><Scissor /></el-icon>
            <span>拆分</span>
          </div>
          <div class="context-menu-item" @click="handleAction('rotate')">
            <el-icon><RefreshRight /></el-icon>
            <span>旋转</span>
          </div>
          <div class="context-menu-item" @click="handleAction('inferPrompt')">
            <el-icon><MagicStick /></el-icon>
            <span>反推提示词</span>
          </div>
          <div class="context-menu-item" @click="handleAction('addToAssets')">
            <el-icon><FolderAdd /></el-icon>
            <span>加入素材库</span>
          </div>
        </template>

        <!-- 视频节点：反推提示词 / 提取首帧 -->
        <template v-else-if="panelType === 'video'">
          <div class="context-menu-divider" />
          <div class="context-menu-item" @click="handleAction('inferPrompt')">
            <el-icon><MagicStick /></el-icon>
            <span>反推提示词</span>
          </div>
          <div class="context-menu-item" @click="handleAction('extractFirstFrame')">
            <el-icon><PictureFilled /></el-icon>
            <span>提取首帧</span>
          </div>
        </template>

        <!-- 文本节点：改写 / 放大字号 / 缩小字号 -->
        <template v-else-if="panelType === 'text'">
          <div class="context-menu-divider" />
          <div class="context-menu-item" @click="handleAction('rewrite')">
            <el-icon><Refresh /></el-icon>
            <span>改写</span>
          </div>
          <div class="context-menu-item" @click="handleAction('fontUp')">
            <el-icon><ZoomIn /></el-icon>
            <span>放大字号</span>
          </div>
          <div class="context-menu-item" @click="handleAction('fontDown')">
            <el-icon><ZoomOut /></el-icon>
            <span>缩小字号</span>
          </div>
        </template>

        <!-- 配置节点：合并生成 -->
        <template v-else-if="panelType === 'config'">
          <div class="context-menu-divider" />
          <div class="context-menu-item" @click="handleAction('generate')">
            <el-icon><MagicStick /></el-icon>
            <span>合并生成</span>
          </div>
        </template>
      </template>

      <!-- ============ 连线右键菜单 ============ -->
      <template v-else-if="target === 'connection'">
        <div class="context-menu-item context-menu-item--danger" @click="handleAction('deleteConnection')">
          <el-icon><Delete /></el-icon>
          <span>删除连线</span>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import {
  Edit, CopyDocument, Delete, Select, Lock, Unlock, Hide, DocumentCopy, FullScreen, Grid,
  Crop, Scissor, RefreshRight, MagicStick, FolderAdd, Refresh, ZoomIn, ZoomOut, PictureFilled,
} from '@element-plus/icons-vue'

const store = useCanvasStore()

const emit = defineEmits(['panel-action'])

/* ===== 菜单显示状态与定位 ===== */
const visible = ref(false)
const x = ref(0)
const y = ref(0)
const target = ref('background') // 'background' | 'panel' | 'connection'
const contextData = ref({}) // { panelId?, panel?, connectionId? }

/* ===== 计算属性 ===== */
/** 当前面板对象（来自 contextData.panel） */
const currentPanel = computed(() => contextData.value.panel || null)
/** 当前面板类型 */
const panelType = computed(() => currentPanel.value?.type || '')
/** 当前面板是否已锁定 */
const isPanelLocked = computed(() => !!currentPanel.value?.content?.locked)
/** store 剪贴板是否有内容（用于背景菜单的粘贴项禁用判断） */
const hasClipboard = computed(() => Array.isArray(store.clipboard) && store.clipboard.length > 0)

/* ===== 暴露方法 ===== */
/** 显示菜单：根据 e.clientX/e.clientY 定位，记录 target 与 data */
function show(e, payload) {
  visible.value = true
  x.value = e.clientX
  y.value = e.clientY
  target.value = payload.target
  contextData.value = payload.data || {}

  // 确保菜单位置不超出视口
  requestAnimationFrame(() => {
    const menu = document.querySelector('.context-menu')
    if (!menu) return
    const rect = menu.getBoundingClientRect()
    if (rect.right > window.innerWidth) {
      x.value = window.innerWidth - rect.width - 4
    }
    if (rect.bottom > window.innerHeight) {
      y.value = window.innerHeight - rect.height - 4
    }
  })
}

/** 隐藏菜单 */
function hide() {
  visible.value = false
}

/* ===== 菜单项处理 ===== */
/** 处理菜单动作：emit panel-action 并自动 hide */
function handleAction(type) {
  hide()
  emit('panel-action', { type, panel: currentPanel.value })
}

/** 隐藏面板：直接调 store.setPanelHidden（不在 emit 类型列表中，直接处理） */
function handleHide() {
  hide()
  const panelId = contextData.value.panelId
  if (panelId) store.setPanelHidden(panelId, true)
}

defineExpose({ show, hide })
</script>

<style scoped>
/* 菜单容器：使用画布主题 CSS 变量 */
.context-menu {
  position: fixed;
  z-index: 10000;
  min-width: 180px;
  background: var(--canvas-panel-bg);
  border: 1px solid var(--canvas-node-border);
  border-radius: 6px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  padding: 4px 0;
  user-select: none;
}

/* 菜单项 */
.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--canvas-node-title-text);
  cursor: pointer;
  transition: background 0.1s;
}

/* hover 高亮 */
.context-menu-item:hover:not(.context-menu-item--disabled) {
  background: var(--canvas-selection-fill);
}

/* 危险项 hover（删除/清空画布） */
.context-menu-item.context-menu-item--danger:hover {
  background: rgba(255, 77, 79, 0.15);
  color: #ff6b6b;
}

/* 禁用项 */
.context-menu-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 分隔线 */
.context-menu-divider {
  height: 1px;
  margin: 4px 0;
  background: var(--canvas-node-border);
}
</style>

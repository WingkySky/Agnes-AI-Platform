<!-- =====================================================
     无限画布页面
     - 左侧栏：多画布管理
     - 中间：无限画布主体
     - 顶部：工具栏（含导入/导出按钮、搜索/筛选）
     - 右侧：选中面板/连线的属性编辑面板
     - 全局快捷键处理器（含 / 聚焦搜索框）
     - 右键上下文菜单（含节点级操作：编辑/裁剪/分割/旋转/反推/改写/字号/生成/提取首帧/锁定/粘贴等）
     - 节点编辑弹窗 PanelEditDialog（由右键菜单"编辑"触发）
     - 图片裁剪弹窗 ImageCropDialog（由右键菜单"裁剪"触发）
     - Minimap 小地图
     ===================================================== -->

<template>
  <div class="canvas-view" :data-theme="store.themeMode" @contextmenu.prevent="handleContextMenu">
    <!-- 左侧栏 -->
    <CanvasSidebar />

    <!-- 主内容区 -->
    <div class="canvas-main">
      <!-- 顶部工具栏（暴露 ref 以便全局 / 快捷键聚焦搜索框） -->
      <CanvasToolbar
        ref="canvasToolbarRef"
        @export-json="handleExportJson"
        @import-json="triggerImport"
      />

      <!-- 无限画布 -->
      <InfiniteCanvas ref="infiniteCanvasRef" @panel-edit="handlePanelEdit" @panel-action="handlePanelAction" />

      <!-- Minimap 小地图 -->
      <CanvasMinimap v-if="isMinimapOpen" />

      <!-- 底部浮动快捷工具栏 -->
      <CanvasQuickToolbar />

      <!-- 左下角缩放控制面板 -->
      <CanvasZoomControls
        :is-minimap-open="isMinimapOpen"
        @toggle-minimap="toggleMinimap"
      />

      <!-- 节点悬停工具栏 -->
      <CanvasNodeHoverToolbar
        v-if="hoveredPanel"
        :panel="hoveredPanel"
        :visible="showHoverToolbar"
        @action="handleHoverToolbarAction"
        @enter="handleHoverToolbarEnter"
        @leave="handleHoverToolbarLeave"
      />
    </div>

    <!-- 右侧属性面板 -->
    <CanvasRightPanel />

    <!-- 右键菜单（监听 panel-action 事件以处理节点级操作） -->
    <CanvasContextMenu ref="contextMenuRef" @panel-action="handlePanelAction" />

    <!-- 拖线到空白弹出的"创建新节点"菜单 -->
    <ConnectionCreateMenu />

    <!-- 节点编辑弹窗：由右键菜单"编辑"动作触发，按节点类型渲染不同表单 -->
    <PanelEditDialog
      v-model="editDialogVisible"
      :panel="editDialogPanel"
      @confirm="handleEditConfirm"
    />

    <!-- 图片裁剪弹窗：由右键菜单"裁剪"动作触发 -->
    <ImageCropDialog
      v-model="cropDialogVisible"
      :image-src="cropImageSrc"
      @confirm="onCropConfirm"
    />

    <!-- 隐藏的文件 input 用于导入 JSON -->
    <input
      ref="importInputRef"
      type="file"
      accept=".json,application/json"
      style="display: none"
      @change="handleImportFile"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'
import CanvasSidebar from '@/components/infinite-canvas/CanvasSidebar.vue'
import CanvasToolbar from '@/components/infinite-canvas/CanvasToolbar.vue'
import InfiniteCanvas from '@/components/infinite-canvas/InfiniteCanvas.vue'
import CanvasContextMenu from '@/components/infinite-canvas/CanvasContextMenu.vue'
import CanvasMinimap from '@/components/infinite-canvas/CanvasMinimap.vue'
import CanvasQuickToolbar from '@/components/infinite-canvas/CanvasQuickToolbar.vue'
import CanvasNodeHoverToolbar from '@/components/infinite-canvas/CanvasNodeHoverToolbar.vue'
import CanvasZoomControls from '@/components/infinite-canvas/CanvasZoomControls.vue'
import CanvasRightPanel from '@/components/infinite-canvas/CanvasRightPanel.vue'
import ConnectionCreateMenu from '@/components/infinite-canvas/ConnectionCreateMenu.vue'
import PanelEditDialog from '@/components/infinite-canvas/PanelEditDialog.vue'
import ImageCropDialog from '@/components/infinite-canvas/ImageCropDialog.vue'
import { executeMergeGeneration } from '@/lib/canvas-generation'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const store = useCanvasStore()
const contextMenuRef = ref(null)
const infiniteCanvasRef = ref(null)
const importInputRef = ref(null)
const canvasToolbarRef = ref(null)

// 节点编辑弹窗状态：editDialogPanel 为当前编辑的面板对象
const editDialogVisible = ref(false)
const editDialogPanel = ref(null)
// 图片裁剪弹窗状态：cropTargetPanel 为当前裁剪的面板对象
const cropDialogVisible = ref(false)
const cropTargetPanel = ref(null)
// 裁剪弹窗要显示的图片源（优先 imageUrl，其次 image，兼容旧数据）
const cropImageSrc = computed(() => {
  const c = cropTargetPanel.value?.content || {}
  return c.imageUrl || c.image || c.url || ''
})
// 节点级异步动作的 loading 状态集合（防止重复触发）
const loadingActions = reactive({})

// 小地图显示状态
const isMinimapOpen = ref(true)

// 节点悬停工具栏状态
const hoveredPanel = ref(null)
const showHoverToolbar = ref(false)
const hoverToolbarTimer = ref(null)

/** 切换小地图显示 */
function toggleMinimap() {
  isMinimapOpen.value = !isMinimapOpen.value
}

/** 处理节点悬停工具栏动作 */
function handleHoverToolbarAction({ type, panel }) {
  // 复用现有的 handlePanelAction 逻辑
  handlePanelAction({ type, panel })
  showHoverToolbar.value = false
  hoveredPanel.value = null
}

/** 鼠标进入悬停工具栏 */
function handleHoverToolbarEnter() {
  if (hoverToolbarTimer.value) {
    clearTimeout(hoverToolbarTimer.value)
    hoverToolbarTimer.value = null
  }
  showHoverToolbar.value = true
}

/** 鼠标离开悬停工具栏 */
function handleHoverToolbarLeave() {
  hoverToolbarTimer.value = setTimeout(() => {
    showHoverToolbar.value = false
    hoveredPanel.value = null
  }, 300)
}

/** 右键菜单处理：把 panel 对象一并传给 CanvasContextMenu，支持按类型渲染节点级操作 */
function handleContextMenu(e) {
  const target = e.target

  // 检查是否点击了面板
  const panelEl = target.closest('[data-canvas-target="panel"]')
  if (panelEl) {
    const panelId = panelEl.getAttribute('data-panel-id')
    const panel = store.panels.find((p) => p.id === panelId) || null
    contextMenuRef.value?.show(e, {
      target: 'panel',
      data: { panelId, panel },
    })
    return
  }

  // 检查是否点击了连线（SVG path）
  if (target.classList.contains('connection-path')) {
    const connGroup = target.closest('.connection-group')
    const connId = connGroup?.dataset?.connId
    contextMenuRef.value?.show(e, {
      target: 'connection',
      data: { connectionId: connId },
    })
    return
  }

  // 背景右键
  contextMenuRef.value?.show(e, { target: 'background' })
}

/** 全局点击关闭菜单 */
function handleClick() {
  contextMenuRef.value?.hide()
}

/** 全局快捷键处理 */
function handleKeydown(e) {
  // 忽略在表单元素中的按键
  const tag = (e.target?.tagName || '').toLowerCase()
  if (['input', 'textarea', 'select'].includes(tag) || e.target?.isContentEditable) {
    return
  }

  const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0
  const mod = isMac ? e.metaKey : e.ctrlKey

  // Space 键：临时进入平移模式（按下时显示抓手指针，可拖动画布）
  if (e.code === 'Space' && !e.repeat) {
    e.preventDefault()
    store._isSpacePressed = true
    return
  }

  // / 键：聚焦工具栏搜索框（任务 3 节点搜索）
  // - 不与现有 Ctrl/Cmd + 字母组合冲突
  // - 表单元素中的 / 已被前置 guard 拦截
  if (e.key === '/') {
    e.preventDefault()
    canvasToolbarRef.value?.focusSearch?.()
    return
  }

  // Escape：关闭右键菜单 + 取消选中；优先退出 Frame 内部模式
  if (e.key === 'Escape') {
    contextMenuRef.value?.hide()
    // 优先退出 Frame 内部模式（双击进入后用 Esc 返回上级）
    if (store.enteredFrameId) {
      store.exitFrame()
      return
    }
    // 关闭拖线空白处弹出的"创建新节点"菜单
    if (store.pendingConnectionCreate) {
      store.clearPendingConnectionCreate()
      return
    }
    store.clearSelection()
    return
  }

  // Delete / Backspace：删除选中的面板（多选支持）或连线；锁定节点会被过滤
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (store.selectedPanelIds.length > 0) {
      e.preventDefault()
      // 过滤掉 locked 节点，避免误删
      const deletableIds = store.selectedPanelIds.filter(
        (id) => !store.panels.find((p) => p.id === id)?.content?.locked
      )
      if (deletableIds.length === 0) {
        ElMessage.warning(t('canvas.lockedHint'))
        return
      }
      // 重新设置选中集合为可删除的，再触发删除
      store.selectedPanelIds = deletableIds
      store.selectedPanelId = deletableIds[0] ?? null
      store.deleteSelectedPanels()
    } else if (store.selectedConnectionId) {
      e.preventDefault()
      store.deleteConnection(store.selectedConnectionId)
    }
    return
  }

  // Ctrl+Z / Cmd+Z：撤销
  if (e.key === 'z' && mod && !e.shiftKey) {
    e.preventDefault()
    store.undo()
    return
  }

  // Ctrl+Shift+Z / Cmd+Shift+Z：重做
  if (e.key === 'z' && mod && e.shiftKey) {
    e.preventDefault()
    store.redo()
    return
  }

  // Ctrl+D / Cmd+D：复制选中面板（多选支持）
  if (e.key === 'd' && mod) {
    if (store.selectedPanelIds.length > 0) {
      e.preventDefault()
      store.duplicateSelectedPanels()
    } else if (store.selectedPanelId) {
      // 兼容旧单选
      e.preventDefault()
      store.duplicatePanel(store.selectedPanelId)
    }
    return
  }

  // Ctrl+A / Cmd+A：全选所有面板（多选）
  if (e.key === 'a' && mod && !store._connecting) {
    e.preventDefault()
    if (store.panels.length > 0) {
      // 用无限矩形一次性框选全部面板
      store.selectPanelsInRect({
        startWorld: { x: -Infinity, y: -Infinity },
        endWorld: { x: Infinity, y: Infinity },
      })
    }
    return
  }

  // Ctrl+L / Cmd+L：切换当前选中节点的锁定状态（仅支持单选）
  if (e.key === 'l' && mod && !e.shiftKey && !e.altKey) {
    e.preventDefault()
    if (store.selectedPanelIds.length === 1) {
      store.toggleLock(store.selectedPanelIds[0])
    } else if (store.selectedPanelIds.length > 1) {
      ElMessage.info(t('canvas.lockMultiSelectHint'))
    }
    return
  }

  // Ctrl+S / Cmd+S：导出当前画布为 JSON（防止浏览器默认保存网页）
  if (e.key === 's' && mod) {
    e.preventDefault()
    handleExportJson()
    return
  }

  // 方向键：微调选中面板位置（多选支持，只压一次快照）
  const nudgeAmount = e.shiftKey ? 10 : 1
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && store.selectedPanelIds.length > 0) {
    e.preventDefault()

    let dx = 0, dy = 0
    if (e.key === 'ArrowUp') dy = -nudgeAmount
    else if (e.key === 'ArrowDown') dy = nudgeAmount
    else if (e.key === 'ArrowLeft') dx = -nudgeAmount
    else if (e.key === 'ArrowRight') dx = nudgeAmount

    // 一次 pushSnapshot：多选微调视为一次操作
    store.pushSnapshot()
    const ids = [...store.selectedPanelIds]
    for (const id of ids) {
      const panel = store.panels.find((p) => p.id === id)
      if (!panel) continue
      store._updatePanelDirect(id, {
        x: panel.x + dx,
        y: panel.y + dy,
      })
    }
  }
}

/** 全局按键释放处理（用于 Space 键松开） */
function handleKeyup(e) {
  if (e.code === 'Space') {
    store._isSpacePressed = false
  }
}

/** 导出当前画布为 JSON 文件下载 */
function handleExportJson() {
  if (store.panels.length === 0 && store.connections.length === 0) {
    ElMessage.warning('画布为空，无需导出')
    return
  }
  const json = store.exportJSON()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const wsName = store.activeWorkspace?.name || 'canvas'
  a.href = url
  a.download = `${wsName}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success(t('canvas.exportSuccess'))
}

/** 触发文件选择对话框 */
function triggerImport() {
  importInputRef.value?.click()
}

/** 处理面板编辑事件（来自 InfiniteCanvas 的 panel-edit 或右键菜单的 edit 动作）
 *  - 打开 PanelEditDialog，按节点类型渲染对应编辑表单 */
function handlePanelEdit(panel) {
  if (!panel) return
  editDialogPanel.value = panel
  editDialogVisible.value = true
}

/** PanelEditDialog 确认回调：把 changes 写回 store.updatePanel */
function handleEditConfirm({ panel, changes }) {
  if (!panel || !changes) return
  store.updatePanel(panel.id, changes)
  ElMessage.success(t('canvas.editDialog.saved'))
}

/** 图片裁剪确认回调
 *  - 把 base64 写回 panel.content.image / imageUrl
 *  - 按裁剪比例调整 width / height，保持原节点中心位置不变
 */
function onCropConfirm({ width: cw, height: ch, base64 }) {
  const panel = cropTargetPanel.value
  if (!panel || !cw || !ch) return
  const ratio = cw / ch
  const oldW = panel.width || 1
  const oldH = panel.height || 1
  // 维持节点中心位置不变，按原宽度回算新高度（宽度优先保持）
  const newH = Math.max(60, oldW / ratio)
  const cx = panel.x + oldW / 2
  const cy = panel.y + oldH / 2
  const newX = cx - oldW / 2
  const newY = cy - newH / 2
  const c = panel.content || {}
  store.updatePanel(panel.id, {
    x: newX, y: newY, width: oldW, height: newH,
    content: { ...c, image: base64, imageUrl: base64 },
  })
  ElMessage.success(t('canvas.cropDialog.confirm'))
}

/**
 * 处理右键菜单抛出的节点级动作
 * - edit: 打开 PanelEditDialog
 * - crop: 打开 ImageCropDialog
 * - split / rotate: 直接调 store
 * - inferPrompt / addToAssets / rewrite / extractFirstFrame: 调 canvas API
 * - fontUp / fontDown: 直接更新 content.fontSize
 * - generate / generateVideo: 调任务队列（占位提示，待接入具体生成流程）
 * - info: 显示节点信息
 * - upload: 提示用户在编辑弹窗中上传
 */
function handlePanelAction({ type, panel }) {
  if (!panel) return
  switch (type) {
    case 'edit':
      handlePanelEdit(panel)
      break
    case 'crop':
      // 仅图片节点可裁剪，且需要有图片源
      if (panel.type !== 'image') {
        ElMessage.warning(t('canvas.cropDialog.empty'))
        return
      }
      // 直接检查 panel 自身的图片源（优先 imageUrl，其次 image，兼容旧数据）
      if (!panel.content?.imageUrl && !panel.content?.image) {
        ElMessage.warning(t('canvas.cropDialog.empty'))
        return
      }
      cropTargetPanel.value = panel
      cropDialogVisible.value = true
      break
    case 'split':
      store.splitImagePanel(panel.id, 4)
      break
    case 'rotate': {
      const cur = panel.content?.rotation || 0
      const next = (cur + 90) % 360
      store.setPanelRotation(panel.id, next)
      break
    }
    case 'inferPrompt':
      inferPrompt(panel)
      break
    case 'addToAssets':
      addToAssets(panel)
      break
    case 'rewrite':
      rewriteText(panel)
      break
    case 'extractFirstFrame':
      extractFirstFrame(panel)
      break
    case 'fontUp':
      adjustFont(panel, +1)
      break
    case 'fontDown':
      adjustFont(panel, -1)
      break
    case 'generate':
      handleMergeGenerate(panel)
      break
    case 'generateVideo':
      ElMessage.info(t('canvas.editDialog.generateVideoHint'))
      break
    case 'info':
      showPanelInfo(panel)
      break
    case 'upload':
      // 文件上传节点：打开编辑弹窗让用户重新上传
      handlePanelEdit(panel)
      break
    default:
      ElMessage.info(t('canvas.toolbar.edit'))
  }
}

/** 合并生成：调用 executeMergeGeneration 收集上游资源 + 解析 @[node:xxx] + 调用 AI 接口 + 回填结果
 *  - 仅支持 Config 节点（quick-generate 节点走简单生成流程）
 *  - 生成过程中显示进度提示
 *  - 成功后自动创建结果节点并连线
 */
async function handleMergeGenerate(panel) {
  // 仅 Config 节点支持合并生成
  if (panel.type !== 'config') {
    ElMessage.info('该节点类型暂不支持合并生成，请使用 Config 节点')
    return
  }
  if (loadingActions[`generate-${panel.id}`]) {
    ElMessage.warning('正在生成中，请稍候...')
    return
  }
  loadingActions[`generate-${panel.id}`] = true
  const loadingMsg = ElMessage.info({ message: '开始合并生成...', duration: 0 })
  try {
    const count = Math.max(1, Number(panel.content?.count) || 1)
    await executeMergeGeneration(panel.id, store, {
      count,
      onProgress: (stage, data) => {
        const messages = {
          building: `正在收集上游资源（${data?.inputSummary?.total || 0} 个）...`,
          creating: `正在创建生成任务（${(data?.index || 0) + 1}/${data?.total || count}）...`,
          polling: `等待生成结果（${(data?.index || 0) + 1}/${data?.total || count}）...`,
          generating: `生成中... ${data?.progress ? Math.round(data.progress * 100) + '%' : ''}`,
          done: `生成完成，已创建 ${data?.resultNodeIds?.length || 0} 个结果节点`,
        }
        if (messages[stage]) {
          loadingMsg.message = messages[stage]
        }
      },
    })
    loadingMsg.close()
    ElMessage.success('合并生成完成')
  } catch (err) {
    loadingMsg.close()
    ElMessage.error(`合并生成失败：${err.message || String(err)}`)
  } finally {
    loadingActions[`generate-${panel.id}`] = false
  }
}

/** 节点级异步动作：调用 /api/canvas/{actionType} 接口
 *  - loadingActions 记录每个动作的 loading 状态，防止重复触发
 *  - 失败时统一提示 */
async function callCanvasApi(actionType, body) {
  if (loadingActions[actionType]) return null
  loadingActions[actionType] = true
  try {
    const resp = await fetch(`/api/canvas/${actionType}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.json()
  } catch (err) {
    ElMessage.error(t('canvas.apiFailed', { msg: err.message || String(err) }))
    return null
  } finally {
    loadingActions[actionType] = false
  }
}

/** 反推提示词：把图片/视频 URL 传给后端，返回的 prompt 写入 panel.content.prompt */
async function inferPrompt(panel) {
  const c = panel.content || {}
  const data = await callCanvasApi('infer-prompt', { url: c.imageUrl || c.image || c.videoUrl || c.url || '', type: panel.type })
  if (data?.prompt) store.updatePanel(panel.id, { content: { ...c, prompt: data.prompt } })
}

/** 加入素材库：把图片 URL 传给后端 */
async function addToAssets(panel) {
  const c = panel.content || {}
  await callCanvasApi('assets', { url: c.imageUrl || c.image || '', name: c.name || panel.id })
  ElMessage.success(t('canvas.addedToAssets'))
}

/** 改写文本：把文本传给后端，返回的改写后文本写回 panel.content.text */
async function rewriteText(panel) {
  const c = panel.content || {}
  const data = await callCanvasApi('rewrite', { text: c.text || '' })
  if (data?.text) store.updatePanel(panel.id, { content: { ...c, text: data.text } })
}

/** 提取视频首帧：返回的图片在原节点下方新增一个 image 子节点 */
async function extractFirstFrame(panel) {
  const c = panel.content || {}
  const data = await callCanvasApi('extract-first-frame', { url: c.videoUrl || c.url || '' })
  if (data?.image) {
    store.addPanel({
      type: 'image',
      x: (panel.x ?? 0),
      y: (panel.y ?? 0) + (panel.height ?? 0) + 20,
      width: 320, height: 200,
      content: { image: data.image, imageUrl: data.image, sourceFrom: panel.id },
    })
  }
}

/** 调整文本字号：delta 为 +1 / -1，实际步进 2px，下限 8px */
function adjustFont(panel, delta) {
  const c = panel.content || {}
  const cur = Number(c.fontSize) || 14
  store.updatePanel(panel.id, { content: { ...c, fontSize: Math.max(8, cur + delta * 2) } })
}

/** 显示节点信息：用 ElMessage 简要展示节点类型、尺寸、内容关键字段 */
function showPanelInfo(panel) {
  const c = panel.content || {}
  const fields = []
  if (c.imageUrl) fields.push(`imageUrl: ${c.imageUrl.slice(0, 40)}...`)
  if (c.videoUrl) fields.push(`videoUrl: ${c.videoUrl.slice(0, 40)}...`)
  if (c.text) fields.push(`text: ${c.text.slice(0, 30)}...`)
  if (c.url) fields.push(`url: ${c.url}`)
  if (c.prompt) fields.push(`prompt: ${c.prompt.slice(0, 30)}...`)
  const info = [
    `type: ${panel.type}`,
    `size: ${panel.width}×${panel.height}`,
    ...(fields.length ? fields : ['content: (空)']),
  ].join(' | ')
  ElMessage.info({ message: info, duration: 4000 })
}

/** 处理选择的 JSON 文件 */
function handleImportFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const result = store.importJSON(ev.target.result)
      ElMessage.success(
        t('canvas.importSuccess', { n: result.panels, m: result.connections }),
      )
    } catch (err) {
      ElMessage.error(t('canvas.importFailed', { msg: err.message }))
    }
  }
  reader.onerror = () => {
    ElMessage.error(t('canvas.importFailed', { msg: '文件读取失败' }))
  }
  reader.readAsText(file)
  // 清空 input.value 允许同名文件重复选择
  e.target.value = ''
}

onMounted(() => {
  document.title = `${t('router.canvas')} · Agnes AI Platform`
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('keyup', handleKeyup)
  // 点击其他地方关闭右键菜单
  window.addEventListener('click', handleClick)
  // Task 5: 异步从 localforage 恢复完整画布状态（panels / connections / viewport）
  // - 仅触发一次，store 内部有 _storageReady 幂等保护
  // - fire-and-forget：hydrate 是异步后台任务，不阻塞 onMounted
  store._hydrateFromStorage()
})

onUnmounted(() => {
  document.title = 'Agnes AI Platform'
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('keyup', handleKeyup)
  window.removeEventListener('click', handleClick)
  // 离开时清掉 Space 状态
  store._isSpacePressed = false
})
</script>

<style scoped>
.canvas-view {
  display: flex;
  height: calc(100vh - 76px); /* 减去顶部栏高度 */
  background: var(--canvas-bg);
  overflow: hidden;

  /* 深色主题 token 映射（默认值） */
  &[data-theme="dark"] {
    --canvas-bg: linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%);
    --canvas-panel-bg: rgba(22, 32, 54, 0.7);
    --canvas-grid-dot: rgba(245, 245, 244, 0.24);
    --canvas-grid-line: rgba(245, 245, 244, 0.10);
    --canvas-node-border: rgba(120, 170, 230, 0.2);
    --canvas-node-active-border: #85b2ff;
    --canvas-node-glow: rgba(100, 150, 255, 0.35);
    --canvas-node-title-text: #ffffff;
    --canvas-node-muted-text: #8ba3c9;
    --canvas-connection-active: rgba(80, 140, 255, 0.6);
    --canvas-connection-muted: rgba(150, 150, 180, 0.3);
    --canvas-anchor-fill: #6b9cff;
    --canvas-anchor-input: #6b9cff;
    --canvas-anchor-output: #a78bff;
    --canvas-selection-fill: rgba(100, 150, 255, 0.15);
    --canvas-selection-stroke: #6b9cff;
  }

  /* 浅色主题 token 映射 */
  &[data-theme="light"] {
    --canvas-bg: #f5f7fa;
    --canvas-panel-bg: rgba(255, 255, 255, 0.95);
    --canvas-grid-dot: rgba(68, 64, 60, 0.28);
    --canvas-grid-line: rgba(68, 64, 60, 0.12);
    --canvas-node-border: rgba(0, 0, 0, 0.1);
    --canvas-node-active-border: #1d4ed8;
    --canvas-node-glow: rgba(37, 99, 235, 0.25);
    --canvas-node-title-text: #1f2937;
    --canvas-node-muted-text: #6b7280;
    --canvas-connection-active: #2563eb;
    --canvas-connection-muted: rgba(120, 113, 108, 0.5);
    --canvas-anchor-fill: #1d4ed8;
    --canvas-anchor-input: #1d4ed8;
    --canvas-anchor-output: #7c3aed;
    --canvas-selection-fill: rgba(37, 99, 235, 0.1);
    --canvas-selection-stroke: #2563eb;
  }
}

.canvas-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>

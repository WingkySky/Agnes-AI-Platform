<!-- =====================================================
     CanvasQuickMenu 画布快速创建菜单
     - create 模式（双击空白 / 空白右键「新建节点」）：分组面板 + 搜索过滤
     - connect 模式（拖线松手在空白）：推荐动作 + 可连候选，选择后由父组件
     -   在落点建节点并自动连线（临时虚线由父组件保留/取消）
     - 定位与关闭链路同 CanvasContextMenu：fixed 定位、外点 / Esc / 视口变化关闭
     - 根元素标记 data-canvas-no-zoom：菜单内按下不平移、滚轮不缩放
     ===================================================== -->

<template>
  <div
    class="canvas-quick-menu"
    :style="menuStyle"
    data-canvas-no-zoom
    @pointerdown.stop
    @click.stop
  >
    <!-- 搜索框（过滤候选列表） -->
    <div class="qm-search" :style="searchStyle">
      <Search :size="13" class="qm-search-icon" />
      <input
        ref="searchRef"
        v-model="query"
        type="text"
        :placeholder="t('canvas.quickMenu.searchPlaceholder')"
      />
    </div>

    <!-- connect 模式：推荐动作（不受搜索过滤） -->
    <template v-if="isConnect && model.recommendations.length > 0">
      <div class="qm-group-title">{{ t('canvas.quickMenu.groupRecommend') }}</div>
      <button
        v-for="item in model.recommendations"
        :key="item.id"
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="emit('select', item)"
      >
        <component :is="item.icon" :size="15" />
        <span>{{ t(item.labelKey) }}</span>
      </button>
    </template>

    <!-- 分组候选 -->
    <template v-for="group in filteredGroups" :key="group.key">
      <div class="qm-group-title">{{ t(group.labelKey) }}</div>
      <button
        v-for="item in group.items"
        :key="item.id"
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="emit('select', item)"
      >
        <component :is="item.icon" :size="15" />
        <span>{{ t(item.labelKey) }}</span>
      </button>
    </template>

    <!-- 空态：推荐与候选均无 -->
    <div v-if="!model.recommendations.length && !filteredGroups.length" class="qm-empty">
      {{ t('canvas.quickMenu.empty') }}
    </div>
  </div>
</template>

<script setup lang="ts">
/* =====================================================
 * CanvasQuickMenu 画布快速创建菜单
 *
 * 数据约定：
 *   - x, y：菜单显示位置（同 CanvasContextMenu，canvas-main 相对坐标）
 *   - mode：'create'（分组面板）| 'connect'（拖线落点，含推荐动作区）
 *   - sourceType / anchorType：connect 模式的连线源节点类型与锚点方向
 *   - 菜单项数据源统一来自 lib/canvas-quick-menu.ts 注册表
 * ===================================================== */

import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { Search } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import {
  resolveCreateGroups, resolveConnectMenu, filterQuickMenuGroups,
  type QuickMenuItem, type ConnectMenuModel,
} from '@/lib/canvas-quick-menu'

const { t } = useI18n()
const store = useCanvasStore()

/* ---------- Props / Emits ---------- */
const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  // 'create'：双击/右键新建；'connect'：拖线松手落点
  mode: { type: String, required: true },
  // connect 模式：拖线源节点类型 / 锚点方向（'source' 右锚出 | 'target' 左锚出）
  sourceType: { type: String, default: '' },
  anchorType: { type: String, default: '' },
  theme: { type: Object, required: true },
})

const emit = defineEmits([
  'select', // payload: QuickMenuItem
  'close',
])

/* ---------- 菜单数据 ---------- */
const query = ref('')
const isConnect = computed(() => props.mode === 'connect')
const model = computed<ConnectMenuModel>(() => {
  if (!isConnect.value) return { recommendations: [], groups: resolveCreateGroups() }
  return resolveConnectMenu(props.sourceType, props.anchorType === 'target' ? 'target' : 'source')
})
const filteredGroups = computed(() => filterQuickMenuGroups(model.value.groups, query.value))

/* ---------- 样式（对齐 CanvasContextMenu 的主题 token） ---------- */
const menuStyle = computed(() => ({
  left: props.x + 'px',
  top: props.y + 'px',
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.node.text,
  '--hover-bg': props.theme.toolbar.itemHover,
}))
const searchStyle = computed(() => ({ borderColor: props.theme.toolbar.border }))
const itemStyle = computed(() => ({}))

/* ---------- 关闭链路：外点 / Esc / 视口变化（缩放平移后锚点漂移，惯例直接关闭） ---------- */
function handleOutsideClick(event: PointerEvent) {
  const menu = document.querySelector('.canvas-quick-menu')
  if (menu && !menu.contains(event.target as Node)) emit('close')
}
function handleEsc(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}
watch(() => store.viewport, () => emit('close'), { deep: true })

onMounted(() => {
  window.addEventListener('pointerdown', handleOutsideClick)
  window.addEventListener('keydown', handleEsc)
  searchRef.value?.focus()
})
onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleOutsideClick)
  window.removeEventListener('keydown', handleEsc)
})

const searchRef = ref<HTMLInputElement | null>(null)
</script>

<style scoped>
/* ===== 菜单容器：同 CanvasContextMenu 基调，增加搜索区与滚动 ===== */
.canvas-quick-menu {
  position: fixed;
  z-index: 80;
  width: 232px;
  max-height: 340px;
  overflow-y: auto;
  padding: 4px 0 6px;
  border-radius: 12px;
  border: 1px solid;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(12px);
}

/* ===== 搜索框 ===== */
.qm-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 8px 2px;
  padding: 5px 8px;
  border: 1px solid;
  border-radius: 8px;
}
.qm-search-icon {
  flex-shrink: 0;
  opacity: 0.55;
}
.qm-search input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: inherit;
  font-size: 12px;
}
.qm-search input::placeholder {
  color: inherit;
  opacity: 0.45;
}

/* ===== 分组标题 ===== */
.qm-group-title {
  padding: 7px 12px 3px;
  font-size: 11px;
  opacity: 0.55;
  user-select: none;
}

/* ===== 菜单项（同 CanvasContextMenu） ===== */
.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 12px;
  border: none;
  background: transparent;
  color: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms ease, opacity 150ms ease;
}
.menu-item:hover {
  background-color: var(--hover-bg, var(--agnes-bg-hover));
}

/* ===== 空态 ===== */
.qm-empty {
  padding: 10px 12px;
  font-size: 12px;
  opacity: 0.5;
  text-align: center;
}
</style>

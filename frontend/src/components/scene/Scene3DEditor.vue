<!-- =====================================================
     Scene3DEditor —— Three.js 3D 视口内核（导演台工作台版）
     功能：
       - 3D 视图：网格地面 + 多机位模型 + 多主体人形 + 多射灯 + 道具占位
       - 多机位一等公民：cameras[] 全部渲染，active 机位为编辑对象
       - 机位拍摄方向引导线 / 灯光照射方向引导线
       - OrbitControls 旋转/平移/缩放查看（Q 切换画布模式）
       - 漫游模式（PointerLockControls WASD 飞行）
       - TransformControls 拖动/旋转当前选中元素（W=移动 E=旋转）
       - 点击 3D 元素直接选中（同步 emit select 供面板联动）
       - 预演播放：镜头序列关键帧插值驱动 lens 相机逐帧渲染，可逐镜头截封面
       - 视口拍照（emit captured，画幅激活时按比例裁剪）
       - 实时输出 scene_data v2（v-model）
     对外 API（defineExpose）：select / playShots / stopPlayback /
       captureViewport / enterRoam / focusCamera / activeCameraPose
     使用方式：
       <Scene3DEditor ref="viewportRef" v-model="sceneData" @select="..." />
     ===================================================== -->

<template>
  <div class="scene3d-editor">
    <!-- 3D 渲染容器 -->
    <div
      ref="containerEl"
      :class="['scene3d-canvas', { drawing }]"
      @click="onCanvasClick"
      @dblclick="onCanvasDblClick"
    >
      <!-- 画幅取景框（纯参考叠加，不拦截交互） -->
      <div v-if="aspectRatio" class="aspect-frame-overlay">
        <div class="aspect-frame-box" :style="frameBoxStyle">
          <div class="aspect-frame-safe"></div>
        </div>
      </div>

      <!-- 预演播放 HUD -->
      <div v-if="playbackState" class="scene3d-playback-hud">
        <span>{{ playbackLabel }}</span>
        <el-button size="small" type="danger" plain @click="stopPlayback">
          {{ t('scene3d.playbackStop') }}
        </el-button>
      </div>

      <!-- 路径绘制提示 -->
      <div v-if="drawing" class="scene3d-draw-hint">{{ t('scene3d.pathDrawHint') }}</div>
    </div>

    <!-- 工具栏：元素选择/添加/删除 + 模式 + FOV + 画幅 + 跟随 + 漫游 + 拍照 -->
    <div :class="['scene3d-toolbar', { collapsed: toolbarCollapsed }]">
      <el-button
        size="small"
        link
        :icon="toolbarCollapsed ? Expand : Fold"
        :title="t('scene3d.toolbarToggle')"
        @click="toolbarCollapsed = !toolbarCollapsed"
      />
      <template v-if="!toolbarCollapsed">
        <el-radio-group v-model="activeTarget" size="small" @change="onTargetChange">
          <el-radio-button value="camera">{{ t('scene3d.targetCamera') }}</el-radio-button>
          <el-radio-button value="subject">{{ t('scene3d.targetSubject') }}</el-radio-button>
          <el-radio-button value="light">{{ t('scene3d.targetLight') }}</el-radio-button>
          <el-radio-button value="prop">{{ t('scene3d.targetProp') }}</el-radio-button>
        </el-radio-group>

        <!-- 元素选择 + 添加/删除（全部类型，相机也是元素） -->
        <div class="element-control">
          <el-select
            v-model="activeIndex"
            size="small"
            style="width: 132px"
            @change="attachActive"
          >
            <el-option
              v-for="opt in elementOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button size="small" :icon="Plus" circle :title="t('scene3d.kbdAdd')" @click="addElement" />
          <el-button
            size="small"
            :icon="Minus"
            circle
            :disabled="!canRemove"
            :title="t('scene3d.kbdDelete')"
            @click="removeElement"
          />
        </div>

        <!-- 灯光预设方案（仅灯光类型显示） -->
        <el-select
          v-if="activeTarget === 'light'"
          v-model="selectedPreset"
          size="small"
          :placeholder="t('scene3d.lightPresetPlaceholder')"
          style="width: 150px"
          @change="applyLightPreset"
        >
          <el-option
            v-for="opt in lightPresetOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>

        <!-- 变换模式：移动/旋转 -->
        <el-radio-group v-model="transformMode" size="small" @change="onModeChange">
          <el-radio-button value="translate">{{ t('scene3d.modeTranslate') }}</el-radio-button>
          <el-radio-button value="rotate">{{ t('scene3d.modeRotate') }}</el-radio-button>
        </el-radio-group>

        <!-- FOV（作用于选中机位） -->
        <div v-if="activeTarget === 'camera'" class="fov-control">
          <span class="fov-label">FOV</span>
          <el-slider
            v-model="fovValue"
            :min="15"
            :max="100"
            :step="1"
            style="width: 100px"
            @change="onFovChange"
          />
          <span class="fov-value">{{ fovValue }}°</span>
        </div>

        <!-- 画幅取景框（持久在 stage.aspect_ratio） -->
        <el-select
          v-model="aspectRatio"
          size="small"
          clearable
          :placeholder="t('scene3d.aspectFrame')"
          style="width: 92px"
          @change="onAspectChange"
        >
          <el-option label="16:9" value="16:9" />
          <el-option label="9:16" value="9:16" />
          <el-option label="1:1" value="1:1" />
          <el-option label="2.35:1" value="2.35:1" />
        </el-select>

        <!-- 镜头跟随主体（作用于选中机位） -->
        <el-checkbox
          v-if="activeTarget === 'camera'"
          :model-value="followEnabled"
          size="small"
          :title="t('scene3d.followSubjectHint')"
          @change="onFollowToggle"
        >
          {{ t('scene3d.followSubject') }}
        </el-checkbox>

        <el-button
          size="small"
          plain
          :icon="Position"
          :type="roaming ? 'warning' : 'default'"
          :title="t('scene3d.roamHint')"
          @click="toggleRoam"
        >
          {{ t('scene3d.roam') }}
        </el-button>
        <el-button size="small" plain :icon="Camera" @click="captureViewport">
          {{ t('scene3d.capture') }}
        </el-button>
        <el-button size="small" plain :icon="QuestionFilled" @click="showHelp = true" />
      </template>
    </div>

    <!-- 当前选中元素的自定义标记编辑面板 -->
    <div v-if="currentLabel !== null && !toolbarCollapsed" class="scene3d-label-panel">
      <span class="label-title">{{ t('scene3d.customLabel') }}</span>
      <el-input
        :model-value="currentLabel"
        size="small"
        style="width: 180px"
        :placeholder="t('scene3d.labelPlaceholder')"
        @update:model-value="onLabelChange"
      />
    </div>

    <!-- 快捷键指引弹窗 -->
    <el-dialog
      v-model="showHelp"
      :title="t('scene3d.helpTitle')"
      width="420px"
      append-to-body
    >
      <div class="help-content">
        <div v-for="item in helpItems" :key="item.key" class="help-item">
          <kbd class="kbd">{{ item.key }}</kbd>
          <span>{{ item.desc }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * Scene3DEditor —— Three.js 3D 视口内核
 * v-model 双向绑定 scene_data v2（多机位/关键帧序列数据由外层面板管理），
 * 拖动 3D 元素实时同步位置；播放/选中等经 defineExpose 与 emit 对外协作。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { PointerLockControls } from 'three/examples/jsm/controls/PointerLockControls.js'
import {
  Plus,
  Minus,
  QuestionFilled,
  Camera,
  Position,
  Fold,
  Expand,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useThemeStore } from '@/stores/theme'
import { defaultCamera } from '@/lib/scene/normalize'
import { sampleCameraTrack } from '@/lib/scene/camera-track'
import { createSubjectMannequin, MANNEQUIN_JOINTS, type JointMap } from '@/lib/scene/mannequin'
import { poseForPreset } from '@/lib/scene/poses'
import type { CameraDevice, LightData, PropData, SceneData, ShotData, Vec3 } from '@/types/scene'

const { t } = useI18n()
const themeStore = useThemeStore()

const props = defineProps<{
  modelValue: SceneData
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
  /** 视口拍照完成（已按画幅裁剪） */
  captured: [dataUrl: string]
  /** 选中元素变化（面板联动） */
  select: [payload: { type: 'camera' | 'subject' | 'light' | 'prop'; index: number }]
  /** 铅笔绘制完成（kind=目标：主体走位/镜头运镜） */
  'path-drawn': [payload: { kind: 'subject' | 'shot'; points: Vec3[] }]
}>()

const containerEl = ref<HTMLDivElement>()
// 当前可拖动元素类型与索引（camera 也按索引多选）
type TargetType = 'camera' | 'subject' | 'light' | 'prop'
const activeTarget = ref<TargetType>('camera')
const activeIndex = ref(0)
const transformMode = ref<'translate' | 'rotate'>('translate')
const canvasMode = ref<'orbit' | 'pan'>('orbit')
const showHelp = ref(false)
const selectedPreset = ref<string>('')
const toolbarCollapsed = ref(false)

// ---------- 画幅框 / 跟随（读写 stage.aspect_ratio、camera.followSubjectId） ----------
const containerSize = ref({ w: 0, h: 0 })
const aspectRatio = computed({
  get: () => props.modelValue?.stage?.aspect_ratio || '',
  set: (val) => {
    emit('update:modelValue', { ...props.modelValue, stage: { ...props.modelValue.stage, aspect_ratio: val || '' } })
  },
})
const aspectRatioValue = computed(() => {
  if (!aspectRatio.value) return 0
  const [w, h] = aspectRatio.value.split(':').map(Number)
  return w > 0 && h > 0 ? w / h : 0
})
/** 取景框盒尺寸：容器内等比内接最大矩形 */
const frameBoxStyle = computed(() => {
  const ratio = aspectRatioValue.value
  if (!ratio || !containerSize.value.w || !containerSize.value.h) return {}
  let w = containerSize.value.w
  let h = w / ratio
  if (h > containerSize.value.h) {
    h = containerSize.value.h
    w = h * ratio
  }
  return { width: `${Math.round(w)}px`, height: `${Math.round(h)}px` }
})

/** 选中机位（v-model 数据侧，非 mesh） */
const selectedCamera = computed<CameraDevice | null>(
  () => props.modelValue?.cameras?.[activeTarget.value === 'camera' ? activeIndex.value : -1] ?? null,
)
const fovValue = ref(selectedCamera.value?.fov ?? 50)
const followEnabled = computed(() => !!selectedCamera.value?.followSubjectId)

function onAspectChange() {
  onResize()
}

function onFollowToggle(val: string | number | boolean) {
  const idx = activeTarget.value === 'camera' ? activeIndex.value : -1
  const cameras = props.modelValue.cameras.map((c, i) => {
    if (i !== idx) return c
    if (val) {
      // 开启跟随时绑定当前选中主体（未选主体则第一个）
      const subIdx = activeTarget.value === 'subject' ? activeIndex.value : 0
      const sub = props.modelValue.subjects[subIdx] || props.modelValue.subjects[0]
      return { ...c, followSubjectId: sub?.id ?? null }
    }
    return { ...c, followSubjectId: null }
  })
  emit('update:modelValue', { ...props.modelValue, cameras })
}

// ---------- Three.js 内部对象（非响应式）----------
let renderer: THREE.WebGLRenderer | null = null
let resizeObserver: ResizeObserver | null = null
let scene: THREE.Scene | null = null
let viewCamera: THREE.PerspectiveCamera | null = null
let lensCamera: THREE.PerspectiveCamera | null = null
let orbitControls: OrbitControls | null = null
let transformControls: TransformControls | null = null
let roamControls: PointerLockControls | null = null
let gridHelper: THREE.GridHelper | null = null
let axesHelper: THREE.AxesHelper | null = null
let animationId = 0
// 多机位 mesh 与引导线（与 modelValue.cameras 同序）
let cameraMeshes: THREE.Group[] = []
let cameraArrows: THREE.ArrowHelper[] = []
let subjectMeshes: THREE.Group[] = []
let lightMeshes: THREE.Group[] = []
let propMeshes: THREE.Mesh[] = []
// 漫游键位
const roamKeys = new Set<string>()
const clock = new THREE.Clock()
const roaming = ref(false)

// Raycaster 用于点击选中
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()

// ---------- 主体颜色梯度（区分多个主体）----------
const SUBJECT_COLORS = [0x67c23a, 0x409eff, 0x9c27b0, 0xe6a23c, 0xf56c6c]
const PROP_COLOR = 0xe6a23c

// ---------- 预演播放状态 ----------
interface PlaybackOpts {
  captureCovers?: boolean
  onShotStart?: (shot: ShotData, index: number) => void
  onShotCover?: (shotId: string, dataUrl: string) => void
  onDone?: () => void
}
let playback: { shots: ShotData[]; startMs: number; idx: number; opts: PlaybackOpts } | null = null
const playbackState = ref(false)
const playbackLabel = ref('')

// ---------- 元素下拉选项 ----------
const elementOptions = computed(() => {
  if (activeTarget.value === 'camera') {
    return (props.modelValue?.cameras || []).map((c, i) => ({
      label: c.name || `${t('scene3d.targetCamera')} ${i + 1}`,
      value: i,
    }))
  }
  if (activeTarget.value === 'subject') {
    return (props.modelValue?.subjects || []).map((s, i) => ({
      label: `${s.label || t('scene3d.targetSubject')} ${i + 1}`,
      value: i,
    }))
  }
  if (activeTarget.value === 'light') {
    return (props.modelValue?.lights || []).map((_, i) => ({
      label: `${t('scene3d.targetLight')} ${i + 1}`,
      value: i,
    }))
  }
  return (props.modelValue?.props || []).map((p, i) => ({
    label: `${p.label || t('scene3d.targetProp')} ${i + 1}`,
    value: i,
  }))
})

// 是否可删除（相机/主体/灯光至少保留 1 个，道具可全删）
const canRemove = computed(() => {
  if (activeTarget.value === 'camera') return (props.modelValue?.cameras?.length || 0) > 1
  if (activeTarget.value === 'subject') return (props.modelValue?.subjects?.length || 0) > 1
  if (activeTarget.value === 'light') return (props.modelValue?.lights?.length || 0) > 1
  if (activeTarget.value === 'prop') return (props.modelValue?.props?.length || 0) > 0
  return false
})

// ---------- 灯光预设方案 ----------
const lightPresetOptions = computed(() => [
  { value: 'three_point', label: t('scene3d.presetThreePoint') },
  { value: 'rembrandt', label: t('scene3d.presetRembrandt') },
  { value: 'butterfly', label: t('scene3d.presetButterfly') },
  { value: 'split', label: t('scene3d.presetSplit') },
  { value: 'loop', label: t('scene3d.presetLoop') },
  { value: 'rim', label: t('scene3d.presetRim') },
])

/** 灯光预设方案数据：返回一组灯光配置 */
function getLightPreset(preset: string): LightData[] {
  const dir = (x: number, y: number, z: number): Vec3 => {
    const len = Math.sqrt(x * x + y * y + z * z)
    return { x: x / len, y: y / len, z: z / len }
  }
  const mk = (x: number, y: number, z: number, intensity: number, d: Vec3): LightData =>
    ({ id: crypto.randomUUID(), type: 'directional', x, y, z, intensity, direction: d })
  switch (preset) {
    case 'three_point':
      // 三点布光：主光（前上侧）+ 辅光（对侧填充）+ 轮廓光（背后顶）
      return [
        mk(4, 5, 4, 1.5, dir(-4, -5, -4)),
        mk(-4, 3, 3, 0.6, dir(4, -3, -3)),
        mk(0, 6, -4, 1.0, dir(0, -6, 4)),
      ]
    case 'rembrandt':
      // 伦勃朗光：单侧 45° 高位主光，制造三角光斑
      return [mk(5, 5, 3, 1.4, dir(-5, -5, -3)), mk(-4, 2, 4, 0.4, dir(4, -2, -4))]
    case 'butterfly':
      // 蝴蝶光：正前方高位主光，鼻下制造蝴蝶形阴影
      return [mk(0, 6, 5, 1.5, dir(0, -6, -5)), mk(0, 2, 5, 0.5, dir(0, -2, -5))]
    case 'split':
      // 分割光：正侧光，明暗各半
      return [mk(6, 3, 0, 1.3, dir(-6, -3, 0))]
    case 'loop':
      // 环形光：前侧 30° 主光，鼻影短小
      return [mk(3, 4, 5, 1.3, dir(-3, -4, -5)), mk(-3, 2, 4, 0.5, dir(3, -2, -4))]
    case 'rim':
      // 轮廓光：背后侧逆光，勾勒边缘
      return [mk(-3, 4, -5, 1.5, dir(3, -4, 5)), mk(2, 3, 5, 0.6, dir(-2, -3, -5))]
    default:
      return []
  }
}

/** 应用灯光预设：替换当前所有灯光 */
function applyLightPreset(preset: string) {
  if (!preset) return
  const lights = getLightPreset(preset)
  emit('update:modelValue', { ...props.modelValue, lights })
  rebuildElements()
  activeIndex.value = 0
  attachActive()
}

// ---------- 当前选中元素的 label（用于自定义标记编辑面板）----------
const currentLabel = computed<string | null>(() => {
  if (activeTarget.value === 'camera') return null // 相机名称在右栏编辑
  if (activeTarget.value === 'subject') {
    return props.modelValue?.subjects?.[activeIndex.value]?.label ?? null
  }
  if (activeTarget.value === 'prop') {
    return props.modelValue?.props?.[activeIndex.value]?.label ?? null
  }
  return null
})

/** 自定义标记修改：实时同步到 modelValue */
function onLabelChange(val: string) {
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  if (activeTarget.value === 'subject' && newData.subjects[activeIndex.value]) {
    newData.subjects[activeIndex.value].label = val
  } else if (activeTarget.value === 'prop' && newData.props[activeIndex.value]) {
    newData.props[activeIndex.value].label = val
  }
  emit('update:modelValue', newData)
}

// ---------- 快捷键指引项 ----------
const helpItems = computed(() => [
  { key: '1 / 2 / 3 / 4', desc: t('scene3d.helpSwitchTarget') },
  { key: 'W', desc: t('scene3d.helpTranslate') },
  { key: 'E', desc: t('scene3d.helpRotate') },
  { key: 'Q', desc: t('scene3d.helpCanvasMode') },
  { key: 'G', desc: t('scene3d.helpRoam') },
  { key: 'N', desc: t('scene3d.helpAdd') },
  { key: 'Delete', desc: t('scene3d.helpDelete') },
  { key: 'R', desc: t('scene3d.helpResetView') },
  { key: t('scene3d.helpClick'), desc: t('scene3d.helpClickDesc') },
  { key: t('scene3d.helpCanvasLeft'), desc: t('scene3d.helpCanvasLeftDesc') },
  { key: t('scene3d.helpCanvasRight'), desc: t('scene3d.helpCanvasRightDesc') },
  { key: t('scene3d.helpCanvasWheel'), desc: t('scene3d.helpCanvasWheelDesc') },
])

// ---------- 创建相机形状（拟物化：机身+镜头+取景器）----------
// 注意：cameraMesh 是普通 THREE.Group（非 Camera 类型），Object3D.lookAt() 对普通对象
// 的约定是让 +z 轴指向目标。因此镜头放置在 +z 方向（前方/拍摄方向）。
function createCameraMesh(color: number): THREE.Group {
  const group = new THREE.Group()
  const bodyMat = new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.85 })
  const lensMat = new THREE.MeshStandardMaterial({ color: 0x303133, transparent: true, opacity: 0.9 })
  const detailMat = new THREE.MeshStandardMaterial({ color: 0x909399 })

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.5, 0.4), bodyMat)
  body.position.y = 0.25
  group.add(body)

  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.5, 24), lensMat)
  lens.rotation.x = Math.PI / 2
  lens.position.set(0, 0.25, 0.45)
  group.add(lens)

  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.04, 12, 24), detailMat)
  ring.position.set(0, 0.25, 0.7)
  group.add(ring)

  const viewfinder = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 0.2), detailMat)
  viewfinder.position.set(0, 0.6, -0.1)
  group.add(viewfinder)

  group.userData.type = 'camera'
  body.userData.type = 'camera'
  return group
}

// ---------- 主体 = 16 关节程序人偶 + 姿势预设（b2） ----------
/** 把姿势预设写到人偶关节（未列出的关节归零），角度制→弧度 */
function applyPose(joints: JointMap, preset?: string | null) {
  const pose = poseForPreset(preset)
  for (const name of MANNEQUIN_JOINTS) {
    const g = joints[name]
    if (!g) continue
    const r = pose[name]
    const rad = (deg: number) => (deg * Math.PI) / 180
    g.rotation.set(r ? rad(r[0]) : 0, r ? rad(r[1]) : 0, r ? rad(r[2]) : 0)
  }
}

// ---------- 创建射灯形状（拟物化：灯体+锥形灯罩+灯头+方向引导线）----------
function createLightMesh(): THREE.Group {
  const group = new THREE.Group()
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x606266, transparent: true, opacity: 0.85 })
  const shadeMat = new THREE.MeshStandardMaterial({ color: 0x909399, transparent: true, opacity: 0.75 })
  const bulbMat = new THREE.MeshStandardMaterial({
    color: 0xffd04b,
    emissive: 0xffd04b,
    emissiveIntensity: 0.7,
    transparent: true,
    opacity: 0.95,
  })

  const housing = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.4, 16), bodyMat)
  housing.position.y = 0.25
  group.add(housing)

  const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.32, 0.3, 16, 1, true), shadeMat)
  shade.position.y = -0.05
  group.add(shade)

  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.06, 16), bulbMat)
  lampHead.position.y = -0.2
  group.add(lampHead)

  const arrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, -1, 0),
    new THREE.Vector3(0, -0.23, 0),
    2.0,
    0xffd04b,
    0.35,
    0.22,
  )
  group.add(arrow)

  group.userData.type = 'light'
  housing.userData.type = 'light'
  shade.userData.type = 'light'
  lampHead.userData.type = 'light'
  return group
}

// ---------- 创建道具占位（按类型选几何体）----------
function createPropMesh(propType: PropData['type']): THREE.Mesh {
  let geo: THREE.BufferGeometry
  switch (propType) {
    case 'sphere':
      geo = new THREE.SphereGeometry(0.5, 16, 16)
      break
    case 'cylinder':
      geo = new THREE.CylinderGeometry(0.4, 0.4, 1.0, 16)
      break
    case 'plane':
      geo = new THREE.PlaneGeometry(1.5, 1.5)
      break
    case 'box':
    default:
      geo = new THREE.BoxGeometry(0.8, 0.8, 0.8)
      break
  }
  const mat = new THREE.MeshStandardMaterial({ color: PROP_COLOR, transparent: true, opacity: 0.5 })
  const mesh = new THREE.Mesh(geo, mat)
  mesh.position.y = 0.4
  mesh.userData.type = 'prop'
  return mesh
}

// ---------- 初始化 Three.js 场景 ----------
function initThree() {
  if (!containerEl.value) return
  const width = containerEl.value.clientWidth
  const height = containerEl.value.clientHeight

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(width, height)
  renderer.setPixelRatio(window.devicePixelRatio)
  containerEl.value.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  updateThemeColors()

  viewCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
  viewCamera.position.set(6, 5, 8)
  viewCamera.lookAt(0, 1, 0)

  gridHelper = new THREE.GridHelper(20, 20, 0x444466, 0x2a2a44)
  scene.add(gridHelper)
  axesHelper = new THREE.AxesHelper(2)
  scene.add(axesHelper)

  const ambient = new THREE.AmbientLight(0xffffff, 0.4)
  scene.add(ambient)
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
  dirLight.position.set(5, 8, 5)
  scene.add(dirLight)

  // 应用初始数据（重建机位/主体/灯光/道具）
  applySceneData(props.modelValue)

  orbitControls = new OrbitControls(viewCamera, renderer.domElement)
  orbitControls.enableDamping = true
  orbitControls.dampingFactor = 0.1
  orbitControls.target.set(0, 1, 0)
  setCanvasMode('orbit')

  transformControls = new TransformControls(viewCamera, renderer.domElement)
  transformControls.addEventListener('dragging-changed', (e: any) => {
    if (orbitControls) orbitControls.enabled = !e.value
    // 松手后路径折线跟随顶点新位置（拖动中不重建避免抖动）
    if (!e.value) rebuildPathGroups()
  })
  transformControls.addEventListener('objectChange', syncToModel)
  // Three.js 0.185+ TransformControls 不再直接继承 Object3D，需用 getHelper()
  scene.add(transformControls.getHelper())

  // 漫游控制（PointerLock：WASD + Space/Shift 升降）
  roamControls = new PointerLockControls(viewCamera, renderer.domElement)
  roamControls.addEventListener('lock', () => { roaming.value = true; orbitControls && (orbitControls.enabled = false) })
  roamControls.addEventListener('unlock', () => { roaming.value = false; roamKeys.clear(); orbitControls && (orbitControls.enabled = true) })

  setActiveTarget('camera')
  setTransformMode('translate')

  animate()
  // ResizeObserver 盯容器：面板折叠/拖拽改变容器尺寸不触发 window resize，
  // canvas 必须跟随容器才能真正吃满空间
  resizeObserver = new ResizeObserver(() => onResize())
  resizeObserver.observe(containerEl.value)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
}

function animate() {
  animationId = requestAnimationFrame(animate)
  const dt = clock.getDelta()
  if (roamControls?.isLocked) moveRoam(dt)
  if (orbitControls) orbitControls.update()
  if (renderer && scene) {
    const cam = playback ? updatePlayback() : null
    renderer.render(scene, (cam as THREE.Camera) || viewCamera!)
  }
}

function onResize() {
  if (!containerEl.value || !renderer || !viewCamera) return
  const w = containerEl.value.clientWidth
  const h = containerEl.value.clientHeight
  if (w <= 0 || h <= 0) return // 布局过渡瞬间跳过，等下一次回调
  renderer.setSize(w, h)
  viewCamera.aspect = w / h
  viewCamera.updateProjectionMatrix()
  if (lensCamera) {
    lensCamera.aspect = aspectRatioValue.value || w / h
    lensCamera.updateProjectionMatrix()
  }
  containerSize.value = { w, h }
}

// ---------- 漫游 ----------
function toggleRoam() {
  if (!roamControls) return
  if (roamControls.isLocked) roamControls.unlock()
  else enterRoam()
}

function enterRoam() {
  roamControls?.lock()
}

function moveRoam(dt: number) {
  if (!viewCamera) return
  const speed = 8 * dt
  const fwd = viewCamera.getWorldDirection(new THREE.Vector3())
  const right = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0)).normalize()
  if (roamKeys.has('w')) viewCamera.position.addScaledVector(fwd, speed)
  if (roamKeys.has('s')) viewCamera.position.addScaledVector(fwd, -speed)
  if (roamKeys.has('a')) viewCamera.position.addScaledVector(right, -speed)
  if (roamKeys.has('d')) viewCamera.position.addScaledVector(right, speed)
  if (roamKeys.has(' ')) viewCamera.position.y += speed
  if (roamKeys.has('shift')) viewCamera.position.y -= speed
}

// ---------- 预演播放 ----------
/** 播放镜头序列：关键帧插值驱动 lens 相机；期间隐藏 gizmo 只留场景内容 */
function playShots(shots: ShotData[], opts: PlaybackOpts = {}) {
  if (!scene || !renderer || !containerEl.value) return
  stopPlayback()
  const w = containerEl.value.clientWidth
  const h = containerEl.value.clientHeight
  lensCamera = new THREE.PerspectiveCamera(50, aspectRatioValue.value || w / h, 0.1, 1000)
  setGizmosVisible(false)
  if (transformControls) transformControls.detach()
  if (orbitControls) orbitControls.enabled = false
  playback = { shots, startMs: performance.now(), idx: -1, opts }
  playbackState.value = true
}

function stopPlayback() {
  if (!playback) return
  playback = null
  playbackState.value = false
  lensCamera = null
  setGizmosVisible(true)
  if (orbitControls) orbitControls.enabled = !roamControls?.isLocked
  attachActive()
}

/** 每帧推进播放，返回本帧渲染相机；结束自动 stopPlayback */
function updatePlayback(): THREE.PerspectiveCamera | null {
  if (!playback || !lensCamera || !renderer || !scene) return null
  const { shots, startMs, opts } = playback
  const elapsed = (performance.now() - startMs) / 1000
  const total = shots.reduce((s, x) => s + (x.duration || 0), 0)
  // 定位当前镜头
  let acc = 0
  let idx = shots.length - 1
  let tInShot = 0
  for (let i = 0; i < shots.length; i++) {
    const dur = shots[i].duration || 0
    if (elapsed < acc + dur) {
      idx = i
      tInShot = elapsed - acc
      break
    }
    acc += dur
  }
  if (elapsed >= total + 0.05) {
    // 序列播完：末镜头末帧截封面后收尾
    if (opts.captureCovers) captureShotCover(shots[shots.length - 1])
    opts.onDone?.()
    stopPlayback()
    return null
  }
  const shot = shots[idx]
  if (playback.idx !== idx) {
    if (playback.idx >= 0 && opts.captureCovers) captureShotCover(shots[playback.idx])
    playback.idx = idx
    playbackLabel.value = `${idx + 1} / ${shots.length}`
    opts.onShotStart?.(shot, idx)
  }
  const frames = shot.keyframes?.length
    ? shot.keyframes
    : [{ time: 0, position: { x: 0, y: 1.6, z: 5 }, target: { x: 0, y: 1, z: 0 }, fov: 50, easing: 'linear' as const }]
  applyCameraPose(lensCamera, sampleCameraTrack(frames, tInShot))
  return lensCamera
}

/** 把插值姿态应用到镜头相机 */
function applyCameraPose(cam: THREE.PerspectiveCamera, pose: ReturnType<typeof sampleCameraTrack>) {
  if (!pose) return
  cam.position.set(pose.position.x, pose.position.y, pose.position.z)
  cam.lookAt(pose.target.x, pose.target.y, pose.target.z)
  cam.fov = pose.fov
  cam.updateProjectionMatrix()
}

/** 截某镜头末帧为封面（补渲染该末帧后同步抓取，画幅激活时按画幅裁剪） */
async function captureShotCover(shot: ShotData) {
  if (!renderer || !scene || !lensCamera || !playback) return
  const frames = shot.keyframes?.length
    ? shot.keyframes
    : [{ time: 0, position: { x: 0, y: 1.6, z: 5 }, target: { x: 0, y: 1, z: 0 }, fov: 50, easing: 'linear' as const }]
  applyCameraPose(lensCamera, sampleCameraTrack(frames, shot.duration))
  renderer.render(scene, lensCamera)
  let dataUrl = renderer.domElement.toDataURL('image/png')
  if (aspectRatioValue.value) {
    const { cropDataUrlToAspect } = await import('@/lib/canvas-image-ops')
    dataUrl = await cropDataUrlToAspect(dataUrl, aspectRatioValue.value)
  }
  playback.opts.onShotCover?.(shot.id, dataUrl)
}

// ---------- gizmo 可见性（播放期间隐藏）----------
function setGizmosVisible(visible: boolean) {
  if (gridHelper) gridHelper.visible = visible
  if (axesHelper) axesHelper.visible = visible
  cameraMeshes.forEach(m => (m.visible = visible))
  cameraArrows.forEach(a => (a.visible = visible))
  lightMeshes.forEach(m => (m.visible = visible))
  Object.values(pathGroups).forEach(g => g && (g.visible = visible))
  if (drawGroup) drawGroup.visible = visible
  if (transformControls) transformControls.getHelper().visible = visible
}

// ---------- 视口拍照：同步渲染后抓帧，画幅激活时按比例居中裁剪 ----------
async function captureViewport() {
  if (!renderer || !scene || !viewCamera) return
  renderer.render(scene, viewCamera)
  let dataUrl = renderer.domElement.toDataURL('image/png')
  if (aspectRatioValue.value) {
    const { cropDataUrlToAspect } = await import('@/lib/canvas-image-ops')
    dataUrl = await cropDataUrlToAspect(dataUrl, aspectRatioValue.value)
  }
  emit('captured', dataUrl)
}

// ---------- 运镜/走位路径（b3）：渲染 + 铅笔绘制 + 点拖拽 ----------
type PathKind = 'subject' | 'shot'
const PATH_COLORS: Record<PathKind, number> = { subject: 0x67c23a, shot: 0x409eff }
const drawing = ref(false)
let drawKind: PathKind | null = null
let drawPoints: Vec3[] = []
let drawGroup: THREE.Group | null = null
let pathGroups: Record<PathKind, THREE.Group | null> = { subject: null, shot: null }
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)

/** 路径组：虚线感折线 + 可拖顶点小球 */
function buildPathGroup(kind: PathKind, points: Vec3[], interactive: boolean): THREE.Group {
  const group = new THREE.Group()
  const color = PATH_COLORS[kind]
  const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 })
  const geo = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(p.x, p.y, p.z)))
  group.add(new THREE.Line(geo, mat))
  points.forEach((p, i) => {
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 12, 12),
      new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.9 }),
    )
    sphere.position.set(p.x, p.y, p.z)
    if (interactive) sphere.userData = { type: 'pathpoint', kind, index: i }
    group.add(sphere)
  })
  return group
}

/** 重建路径渲染：选中主体的走位路径 + activeShot 的运镜路径 */
function rebuildPathGroups() {
  if (!scene) return
  for (const g of Object.values(pathGroups)) if (g) scene.remove(g)
  pathGroups = { subject: null, shot: null }
  const d = props.modelValue
  if (activeTarget.value === 'subject') {
    const s = d.subjects?.[activeIndex.value]
    if (s?.motionPath?.points?.length) {
      const g = buildPathGroup('subject', s.motionPath.points, true)
      scene.add(g)
      pathGroups.subject = g
    }
  }
  const shot = d.shots?.find(x => x.id === d.activeShotId)
  if (shot?.cameraPath?.path?.points?.length) {
    const g = buildPathGroup('shot', shot.cameraPath.path.points, true)
    scene.add(g)
    pathGroups.shot = g
  }
}

function rebuildDrawPreview() {
  if (!scene) return
  if (drawGroup) scene.remove(drawGroup)
  drawGroup = null
  if (drawKind && drawPoints.length) {
    drawGroup = buildPathGroup(drawKind, drawPoints, false)
    scene.add(drawGroup)
  }
}

/** 铅笔绘制：进入后点击地面加点，双击结束（≥2 点才上抛），Esc 取消 */
function startDrawPath(kind: PathKind) {
  drawKind = kind
  drawPoints = []
  drawing.value = true
  if (transformControls) transformControls.detach()
  rebuildDrawPreview()
}

function cancelDrawPath() {
  drawKind = null
  drawPoints = []
  drawing.value = false
  rebuildDrawPreview()
}

function finishDrawPath() {
  if (drawKind) {
    // 去掉双击产生的重复近点
    const deduped: Vec3[] = []
    for (const p of drawPoints) {
      const last = deduped[deduped.length - 1]
      if (!last || Math.hypot(p.x - last.x, p.z - last.z) > 0.3) deduped.push(p)
    }
    if (deduped.length >= 2) emit('path-drawn', { kind: drawKind, points: deduped })
  }
  cancelDrawPath()
}

function onCanvasDblClick() {
  if (drawing.value) finishDrawPath()
}

/** 拖拽路径顶点 → 回写 model 路径点（不动元素同步链路） */
function syncPathPoint(mesh: THREE.Object3D) {
  const { kind, index } = mesh.userData as { kind: PathKind; index: number }
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  const pos = { x: round(mesh.position.x), y: round(mesh.position.y), z: round(mesh.position.z) }
  if (kind === 'subject') {
    const s = newData.subjects[activeTarget.value === 'subject' ? activeIndex.value : -1]
    if (s?.motionPath) s.motionPath.points[index] = pos
  } else {
    const shot = newData.shots.find(x => x.id === newData.activeShotId)
    if (shot?.cameraPath) shot.cameraPath.path.points[index] = pos
  }
  emit('update:modelValue', newData)
}

// ---------- 点击 3D 元素直接选中 ----------
function onCanvasClick(e: MouseEvent) {
  if (transformControls?.dragging || playback) return
  if (!containerEl.value || !renderer || !viewCamera) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, viewCamera)

  // 铅笔绘制模式：点击地面加点
  if (drawing.value && drawKind) {
    const hit = new THREE.Vector3()
    if (raycaster.ray.intersectPlane(groundPlane, hit)) {
      drawPoints.push({ x: round(hit.x), y: 1.6, z: round(hit.z) })
      rebuildDrawPreview()
    }
    return
  }

  const targets: THREE.Object3D[] = []
  cameraMeshes.forEach(m => targets.push(m))
  subjectMeshes.forEach(m => targets.push(m))
  lightMeshes.forEach(g => g.traverse(child => targets.push(child)))
  propMeshes.forEach(m => targets.push(m))
  Object.values(pathGroups).forEach(g => g && g.children.forEach(c => targets.push(c)))

  const hits = raycaster.intersectObjects(targets, true)
  if (hits.length === 0) return

  let obj: THREE.Object3D | null = hits[0].object
  while (obj && !obj.userData?.type) obj = obj.parent
  if (!obj) return

  const type = obj.userData.type as TargetType | 'pathpoint'
  if (type === 'pathpoint') {
    // 路径顶点：附着变换手柄拖动（不动元素选中态）
    if (transformControls) transformControls.attach(obj)
    return
  }
  if (type === 'camera') {
    const idx = cameraMeshes.indexOf(obj as THREE.Group)
    if (idx >= 0) select('camera', idx)
  } else if (type === 'subject') {
    let g: THREE.Object3D | null = obj
    while (g && !subjectMeshes.includes(g as THREE.Group)) g = g.parent
    if (g) select('subject', subjectMeshes.indexOf(g as THREE.Group))
  } else if (type === 'light') {
    let g: THREE.Object3D | null = obj
    while (g && !lightMeshes.includes(g as THREE.Group)) g = g.parent
    if (g) select('light', lightMeshes.indexOf(g as THREE.Group))
  } else if (type === 'prop') {
    select('prop', propMeshes.indexOf(obj as THREE.Mesh))
  }
}

// ---------- 选中（统一入口：数据、mesh、emit 三方同步）----------
function isLocked(type: TargetType, index: number): boolean {
  const list = type === 'camera' ? props.modelValue.cameras : type === 'subject' ? props.modelValue.subjects : type === 'light' ? props.modelValue.lights : props.modelValue.props
  return !!(list as any[])[index]?.locked
}

function select(type: TargetType, index: number) {
  if (isLocked(type, index)) return
  activeTarget.value = type
  activeIndex.value = index
  if (type === 'camera') {
    // 激活机位唯一化
    const cameras = props.modelValue.cameras.map((c, i) => ({ ...c, active: i === index }))
    emit('update:modelValue', { ...props.modelValue, cameras })
    fovValue.value = cameras[index]?.fov ?? 50
  }
  attachActive()
  rebuildPathGroups()
  emit('select', { type, index })
}

function setActiveTarget(target: TargetType) {
  select(target, 0)
}

function onTargetChange(val: TargetType) {
  setActiveTarget(val)
}

// ---------- 变换模式切换 ----------
function setTransformMode(mode: 'translate' | 'rotate') {
  transformMode.value = mode
  if (transformControls) transformControls.setMode(mode)
}

function onModeChange(val: 'translate' | 'rotate') {
  setTransformMode(val)
}

// ---------- 画布模式切换（旋转视角 / 平移视角）----------
function setCanvasMode(mode: 'orbit' | 'pan') {
  canvasMode.value = mode
  if (!orbitControls) return
  if (mode === 'orbit') {
    orbitControls.enableRotate = true
    orbitControls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    }
  } else {
    orbitControls.enableRotate = true
    orbitControls.mouseButtons = {
      LEFT: THREE.MOUSE.PAN,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.ROTATE,
    }
  }
}

// ---------- 把 TransformControls 附着到当前选中元素 ----------
function attachActive() {
  if (!transformControls) return
  if (activeTarget.value === 'camera') {
    const mesh = cameraMeshes[activeIndex.value]
    if (mesh) transformControls.attach(mesh)
  } else if (activeTarget.value === 'subject') {
    const mesh = subjectMeshes[activeIndex.value]
    if (mesh) transformControls.attach(mesh)
  } else if (activeTarget.value === 'light') {
    const mesh = lightMeshes[activeIndex.value]
    if (mesh) transformControls.attach(mesh)
  } else if (activeTarget.value === 'prop') {
    const mesh = propMeshes[activeIndex.value]
    if (mesh) transformControls.attach(mesh)
  }
}

// ---------- 添加元素 ----------
function addElement() {
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  if (activeTarget.value === 'camera') {
    const n = newData.cameras.length
    const cam = defaultCamera(`${String.fromCharCode(65 + n)} 机位`)
    cam.position = { x: 3 + n, y: 1.6, z: 4 }
    newData.cameras = newData.cameras.map(c => ({ ...c, active: false }))
    newData.cameras.push(cam)
    activeIndex.value = n
    rebuildElements()
  } else if (activeTarget.value === 'subject') {
    newData.subjects.push({
      id: crypto.randomUUID(),
      x: 2 + newData.subjects.length,
      y: 0,
      z: 0,
      label: `${t('scene3d.subjectDefaultLabel')}${newData.subjects.length + 1}`,
      rotation: { x: 0, y: 0, z: 0 },
    })
    activeIndex.value = newData.subjects.length - 1
    rebuildElements()
  } else if (activeTarget.value === 'light') {
    newData.lights.push({
      id: crypto.randomUUID(),
      type: 'directional',
      x: -5,
      y: 5,
      z: -5,
      intensity: 0.6,
      direction: { x: 0.58, y: -0.58, z: 0.58 },
    })
    activeIndex.value = newData.lights.length - 1
    rebuildElements()
  } else if (activeTarget.value === 'prop') {
    newData.props.push({
      id: crypto.randomUUID(),
      type: 'box',
      x: 1 + newData.props.length,
      y: 0,
      z: -2,
      label: `${t('scene3d.propDefaultLabel')}${newData.props.length + 1}`,
      rotation: { x: 0, y: 0, z: 0 },
    })
    activeIndex.value = newData.props.length - 1
    rebuildElements()
  }
  emit('update:modelValue', newData)
  attachActive()
  emit('select', { type: activeTarget.value, index: activeIndex.value })
}

// ---------- 删除当前选中元素 ----------
function removeElement() {
  if (!canRemove.value || isLocked(activeTarget.value, activeIndex.value)) return
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  if (activeTarget.value === 'camera') {
    const removed = newData.cameras[activeIndex.value]
    newData.cameras.splice(activeIndex.value, 1)
    // 引用被删机位的镜头改挂到第一个机位
    newData.shots = newData.shots.map(s =>
      s.cameraId === removed.id ? { ...s, cameraId: newData.cameras[0].id } : s,
    )
    newData.cameras[0].active = true
  } else if (activeTarget.value === 'subject') {
    const removed = newData.subjects[activeIndex.value]
    newData.subjects.splice(activeIndex.value, 1)
    // 跟随该主体的机位解除跟随
    newData.cameras = newData.cameras.map(c =>
      c.followSubjectId === removed.id ? { ...c, followSubjectId: null } : c,
    )
  } else if (activeTarget.value === 'light') {
    newData.lights.splice(activeIndex.value, 1)
  } else if (activeTarget.value === 'prop') {
    newData.props.splice(activeIndex.value, 1)
  }
  activeIndex.value = Math.max(0, activeIndex.value - 1)
  emit('update:modelValue', newData)
  rebuildElements()
  attachActive()
  emit('select', { type: activeTarget.value, index: activeIndex.value })
}

// ---------- 把 3D 对象位置/方向/旋转同步回 modelValue ----------
function syncToModel() {
  // 路径顶点拖拽：只回写路径点，不走元素同步
  const attached = transformControls?.object as THREE.Object3D | undefined
  if (attached?.userData?.type === 'pathpoint') {
    syncPathPoint(attached)
    return
  }
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  // 同步机位（位置 + 被拖动相机的朝向 → target）
  cameraMeshes.forEach((m, i) => {
    const cam = newData.cameras[i]
    if (!cam) return
    cam.position = { x: round(m.position.x), y: round(m.position.y), z: round(m.position.z) }
    // 跟随机位：target 恒对准跟随主体（胸口高度）
    if (cam.followSubjectId) {
      const si = newData.subjects.findIndex(s => s.id === cam.followSubjectId)
      const mesh = subjectMeshes[si]
      if (mesh) {
        m.lookAt(mesh.position.x, 1.2, mesh.position.z)
        cam.target = { x: round(mesh.position.x), y: 1.2, z: round(mesh.position.z) }
        updateCameraArrow(i, cam.target)
        return
      }
    }
    // 仅被拖动/旋转的相机按朝向重算 target（保持原 target 距离）
    if (transformControls && transformControls.object === m) {
      const forward = new THREE.Vector3(0, 0, 1).applyQuaternion(m.quaternion)
      const orig = cam.target || { x: 0, y: 0, z: 0 }
      const dist =
        Math.sqrt(
          (orig.x - m.position.x) ** 2 + (orig.y - m.position.y) ** 2 + (orig.z - m.position.z) ** 2,
        ) || 5
      cam.target = {
        x: round(m.position.x + forward.x * dist),
        y: round(m.position.y + forward.y * dist),
        z: round(m.position.z + forward.z * dist),
      }
      updateCameraArrow(i, cam.target)
    }
  })
  // 同步主体（位置 + 旋转）
  subjectMeshes.forEach((m, i) => {
    if (newData.subjects[i]) {
      newData.subjects[i].x = round(m.position.x)
      newData.subjects[i].z = round(m.position.z)
      newData.subjects[i].rotation = {
        x: round(m.rotation.x * 180 / Math.PI),
        y: round(m.rotation.y * 180 / Math.PI),
        z: round(m.rotation.z * 180 / Math.PI),
      }
    }
  })
  // 同步灯光位置 + 方向（从 group 的旋转计算方向向量）
  lightMeshes.forEach((m, i) => {
    if (newData.lights[i]) {
      newData.lights[i].x = round(m.position.x)
      newData.lights[i].y = round(m.position.y)
      newData.lights[i].z = round(m.position.z)
      const defaultDir = new THREE.Vector3(0, -1, 0)
      defaultDir.applyQuaternion(m.quaternion)
      newData.lights[i].direction = {
        x: round(defaultDir.x),
        y: round(defaultDir.y),
        z: round(defaultDir.z),
      }
    }
  })
  // 同步道具（位置 + 旋转）
  propMeshes.forEach((m, i) => {
    if (newData.props[i]) {
      newData.props[i].x = round(m.position.x)
      newData.props[i].z = round(m.position.z)
      newData.props[i].rotation = {
        x: round(m.rotation.x * 180 / Math.PI),
        y: round(m.rotation.y * 180 / Math.PI),
        z: round(m.rotation.z * 180 / Math.PI),
      }
    }
  })
  emit('update:modelValue', newData)
}

function round(n: number): number {
  return Math.round(n * 100) / 100
}

// ---------- 把方向向量转为四元数（用于应用灯光旋转）----------
function directionToQuaternion(dir: Vec3): THREE.Quaternion {
  const from = new THREE.Vector3(0, -1, 0)
  const to = new THREE.Vector3(dir.x || 0, dir.y || -1, dir.z || 0)
  if (to.lengthSq() === 0) return new THREE.Quaternion()
  to.normalize()
  return new THREE.Quaternion().setFromUnitVectors(from, to)
}

// ---------- 更新机位拍摄方向引导线（从机位指向 target）----------
function updateCameraArrow(index: number, target: Vec3) {
  const arrow = cameraArrows[index]
  const mesh = cameraMeshes[index]
  if (!arrow || !mesh) return
  const from = mesh.position.clone()
  const to = new THREE.Vector3(target.x, target.y, target.z)
  const dir = to.clone().sub(from)
  const len = dir.length()
  if (len < 0.01) return
  dir.normalize()
  arrow.position.copy(from)
  arrow.setDirection(dir)
  arrow.setLength(Math.min(len, 6), 0.3, 0.2)
}

// ---------- 重建机位/主体/灯光/道具 mesh（基于 modelValue）----------
function rebuildElements() {
  if (!scene) return
  cameraMeshes.forEach(m => scene!.remove(m))
  cameraArrows.forEach(a => scene!.remove(a))
  subjectMeshes.forEach(m => scene!.remove(m))
  lightMeshes.forEach(m => scene!.remove(m))
  propMeshes.forEach(m => scene!.remove(m))
  cameraMeshes = []
  cameraArrows = []
  subjectMeshes = []
  lightMeshes = []
  propMeshes = []

  const d = props.modelValue
  // 重建机位（激活机位蓝色，其余灰色；引导线同色）
  ;(d.cameras || []).forEach((c, i) => {
    const color = c.active ? 0x409eff : 0x8a909b
    const mesh = createCameraMesh(color)
    mesh.position.set(c.position.x, c.position.y, c.position.z)
    mesh.lookAt(c.target.x, c.target.y, c.target.z)
    scene!.add(mesh)
    cameraMeshes.push(mesh)
    const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, 0, 0), 1, color, 0.3, 0.2)
    scene!.add(arrow)
    cameraArrows.push(arrow)
    updateCameraArrow(i, c.target)
  })
  // 重建主体（人偶 + 姿势 + 位置 + 朝向 + 可见性）
  ;(d.subjects || []).forEach((s) => {
    const { root, joints } = createSubjectMannequin(SUBJECT_COLORS[subjectMeshes.length % SUBJECT_COLORS.length])
    applyPose(joints, s.pose?.preset)
    root.position.set(s.x, 0, s.z)
    const rot = s.rotation || { x: 0, y: 0, z: 0 }
    root.rotation.set((rot.x || 0) * Math.PI / 180, (rot.y || 0) * Math.PI / 180, (rot.z || 0) * Math.PI / 180)
    root.visible = s.visible !== false
    scene!.add(root)
    subjectMeshes.push(root)
  })
  // 重建灯光（应用位置 + 方向旋转）
  ;(d.lights || []).forEach((l) => {
    const mesh = createLightMesh()
    mesh.position.set(l.x, l.y, l.z)
    const dir = l.direction || { x: 0, y: -1, z: 0 }
    mesh.quaternion.copy(directionToQuaternion(dir))
    mesh.visible = l.visible !== false
    scene!.add(mesh)
    lightMeshes.push(mesh)
  })
  // 重建道具（应用位置 + 旋转 + 可见性）
  ;(d.props || []).forEach((p) => {
    const mesh = createPropMesh(p.type)
    mesh.position.set(p.x, p.y || 0.4, p.z)
    const rot = p.rotation || { x: 0, y: 0, z: 0 }
    mesh.rotation.set((rot.x || 0) * Math.PI / 180, (rot.y || 0) * Math.PI / 180, (rot.z || 0) * Math.PI / 180)
    const sc = p.scale ?? 1
    mesh.scale.set(sc, sc, sc)
    mesh.visible = p.visible !== false
    scene!.add(mesh)
    propMeshes.push(mesh)
  })
}

// ---------- 把 modelValue 应用到 3D 对象 ----------
function applySceneData(data: SceneData) {
  if (!scene) return
  const d = data
  rebuildElements()
  rebuildPathGroups()
  if (activeTarget.value === 'camera') {
    const cam = d.cameras?.[activeIndex.value] || d.cameras?.[0]
    if (cam) fovValue.value = cam.fov
  }
}

// ---------- FOV 滑块改变（作用于选中机位，同时近似预览到观察相机）----------
function onFovChange(val: number | null) {
  if (val == null) return
  if (viewCamera) {
    viewCamera.fov = val
    viewCamera.updateProjectionMatrix()
  }
  const idx = activeTarget.value === 'camera' ? activeIndex.value : -1
  if (idx < 0) return
  const cameras = props.modelValue.cameras.map((c, i) => (i === idx ? { ...c, fov: val } : c))
  emit('update:modelValue', { ...props.modelValue, cameras })
}

// ---------- 重置查看视角 ----------
function resetView() {
  if (!viewCamera || !orbitControls) return
  viewCamera.position.set(6, 5, 8)
  viewCamera.lookAt(0, 1, 0)
  orbitControls.target.set(0, 1, 0)
  orbitControls.update()
}

// ---------- 根据当前主题更新 3D 场景背景与网格颜色 ----------
function updateThemeColors() {
  if (!scene) return
  const isDark = themeStore.isDark
  scene.background = new THREE.Color(isDark ? 0x0b0f1a : 0xeaeef6)
  if (gridHelper) {
    const color1 = isDark ? 0x444466 : 0xc5cdd9
    const color2 = isDark ? 0x2a2a44 : 0xe0e5ee
    const materials = gridHelper.material as THREE.Material | THREE.Material[]
    if (Array.isArray(materials)) {
      ;(materials[0] as THREE.LineBasicMaterial).color.setHex(color1)
      ;(materials[1] as THREE.LineBasicMaterial).color.setHex(color2)
    } else {
      ;(materials as THREE.LineBasicMaterial).color.setHex(color1)
    }
  }
}

// 监听主题变化，实时更新 3D 场景颜色
watch(
  () => themeStore.isDark,
  () => updateThemeColors(),
)

// ---------- 快捷键 ----------
function onKeyDown(e: KeyboardEvent) {
  if (roamControls?.isLocked) {
    roamKeys.add(e.key.toLowerCase())
    return
  }
  // 输入框内不触发
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  if (e.key === 'Escape' && drawing.value) {
    cancelDrawPath()
    return
  }

  const key = e.key.toLowerCase()
  if (key === '1') setActiveTarget('camera')
  else if (key === '2') setActiveTarget('subject')
  else if (key === '3') setActiveTarget('light')
  else if (key === '4') setActiveTarget('prop')
  else if (key === 'w') setTransformMode('translate')
  else if (key === 'e') setTransformMode('rotate')
  else if (key === 'q') setCanvasMode(canvasMode.value === 'orbit' ? 'pan' : 'orbit')
  else if (key === 'g') enterRoam()
  else if (key === 'n') addElement()
  else if (key === 'delete' || key === 'backspace') removeElement()
  else if (key === 'r') resetView()
  else if (key === '?' || (e.shiftKey && key === '/')) showHelp.value = !showHelp.value
}

function onKeyUp(e: KeyboardEvent) {
  roamKeys.delete(e.key.toLowerCase())
}

// ---------- 外部 modelValue 变化时同步到 3D（避免循环，仅当非拖动状态）----------
watch(
  () => props.modelValue,
  (val) => {
    if (!val) return
    const cam = val.cameras?.[activeTarget.value === 'camera' ? activeIndex.value : 0]
    if (cam?.fov != null) fovValue.value = cam.fov
    if (transformControls && !transformControls.dragging) {
      applySceneData(val)
      attachActive()
    }
  },
  { deep: true },
)

// ---------- 对外 API ----------
/** 选中机位当前姿态（记录关键帧用） */
function activeCameraPose() {
  const cam = selectedCamera.value
  if (!cam) return null
  return { position: { ...cam.position }, target: { ...cam.target }, fov: cam.fov }
}

/** 观察相机飞到某机位附近（点镜头卡聚焦） */
function focusCamera(index: number) {
  if (!viewCamera || !orbitControls) return
  const cam = props.modelValue.cameras[index]
  const mesh = cameraMeshes[index]
  if (!cam || !mesh) return
  const back = new THREE.Vector3(cam.position.x, cam.position.y, cam.position.z)
    .sub(new THREE.Vector3(cam.target.x, cam.target.y, cam.target.z))
    .normalize()
    .multiplyScalar(3)
  viewCamera.position.set(cam.position.x + back.x, cam.position.y + back.y + 1, cam.position.z + back.z)
  orbitControls.target.copy(mesh.position)
  orbitControls.update()
}

defineExpose({
  select,
  playShots,
  stopPlayback,
  captureViewport,
  enterRoam,
  focusCamera,
  activeCameraPose,
  startDrawPath,
  cancelDrawPath,
})

onMounted(() => {
  initThree()
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (transformControls) transformControls.dispose()
  if (orbitControls) orbitControls.dispose()
  if (roamControls) roamControls.dispose()
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
  }
  renderer = null
  scene = null
  viewCamera = null
})
</script>

<style scoped>
.scene3d-editor {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 320px;
  position: relative;
  overflow: hidden;
  background: var(--agnes-bg-base);
}

.scene3d-canvas {
  flex: 1;
  width: 100%;
  min-height: 280px;
  cursor: pointer;
  position: relative;
}

.scene3d-canvas.drawing {
  cursor: crosshair;
}

/* 路径绘制提示条 */
.scene3d-draw-hint {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 14px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 11;
  font-size: 12px;
  color: var(--agnes-text-primary);
}

/* 画幅取景框叠加层（纯参考，不拦截交互） */
.aspect-frame-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
}

.aspect-frame-box {
  position: relative;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
  outline: 1px solid rgba(255, 255, 255, 0.65);
}

/* 安全框（95% 内框）+ 三分线 */
.aspect-frame-safe {
  position: absolute;
  inset: 2.5%;
  border: 1px dashed rgba(255, 255, 255, 0.35);
  background:
    linear-gradient(to right, transparent 33.3%, rgba(255, 255, 255, 0.18) 33.3%, rgba(255, 255, 255, 0.18) 33.4%, transparent 33.4%),
    linear-gradient(to right, transparent 66.6%, rgba(255, 255, 255, 0.18) 66.6%, rgba(255, 255, 255, 0.18) 66.7%, transparent 66.7%),
    linear-gradient(to bottom, transparent 33.3%, rgba(255, 255, 255, 0.18) 33.3%, rgba(255, 255, 255, 0.18) 33.4%, transparent 33.4%),
    linear-gradient(to bottom, transparent 66.6%, rgba(255, 255, 255, 0.18) 66.6%, rgba(255, 255, 255, 0.18) 66.7%, transparent 66.7%);
}

/* 预演播放 HUD */
.scene3d-playback-hud {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 11;
  font-size: 13px;
  color: var(--agnes-text-primary);
}

.scene3d-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 10;
  flex-wrap: wrap;
  max-width: calc(100% - 24px);
}

.element-control {
  display: flex;
  align-items: center;
  gap: 6px;
}

.fov-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fov-label {
  font-size: 13px;
  color: var(--agnes-text-primary);
  white-space: nowrap;
}

.fov-value {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  min-width: 36px;
}

/* 自定义标记编辑面板（左下角） */
.scene3d-label-panel {
  position: absolute;
  bottom: 12px;
  left: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 10;
}

.label-title {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  white-space: nowrap;
}

/* 快捷键指引弹窗 */
.help-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--agnes-text-primary);
}

.kbd {
  display: inline-block;
  min-width: 80px;
  padding: 2px 8px;
  background: var(--agnes-bg-hover);
  border: 1px solid var(--agnes-border);
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  text-align: center;
  color: var(--agnes-text-secondary);
}
</style>

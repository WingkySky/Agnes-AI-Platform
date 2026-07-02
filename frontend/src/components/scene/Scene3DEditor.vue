<!-- =====================================================
     Scene3DEditor —— Three.js 3D 场景布局编辑器（导演台）
     功能：
       - 3D 视图：网格地面 + 相机模型 + 多主体人形 + 多射灯 + 道具占位
       - 相机拍摄方向引导线（从相机指向 lookAt 的箭头）
       - 灯光照射方向引导线（射灯箭头，跟随 direction 实时更新）
       - OrbitControls 旋转/平移/缩放查看视角（Q 切换画布模式）
       - TransformControls 拖动/旋转当前选中元素（W=移动 E=旋转）
       - 所有元素（相机/主体/灯光/道具）均可旋转，统一逻辑
       - 点击 3D 元素直接选中（无需上方列表切换）
       - 支持添加/删除多个主体、灯光、道具
       - 灯光预设方案（三点布光/伦勃朗/蝴蝶光等）
       - 实时输出 scene_data（v-model）
       - FOV 滑块调节相机视场角
       - 快捷键：1-4 切类型 / W-E 切模式 / Q 切画布模式 / Del 删除 / N 新建 / R 重置 / ? 帮助
     使用方式：
       <Scene3DEditor v-model="sceneData" />
     ===================================================== -->

<template>
  <div class="scene3d-editor">
    <!-- 3D 渲染容器 -->
    <div ref="containerEl" class="scene3d-canvas" @click="onCanvasClick" />

    <!-- 工具栏：切换元素类型 + 元素选择 + 添加/删除 + 模式 + FOV -->
    <div class="scene3d-toolbar">
      <el-radio-group v-model="activeTarget" size="small" @change="onTargetChange">
        <el-radio-button value="camera">{{ t('scene3d.targetCamera') }}</el-radio-button>
        <el-radio-button value="subject">{{ t('scene3d.targetSubject') }}</el-radio-button>
        <el-radio-button value="light">{{ t('scene3d.targetLight') }}</el-radio-button>
        <el-radio-button value="prop">{{ t('scene3d.targetProp') }}</el-radio-button>
      </el-radio-group>

      <!-- 元素选择 + 添加/删除（仅主体/灯光/道具显示） -->
      <div v-if="activeTarget !== 'camera'" class="element-control">
        <el-select
          v-model="activeIndex"
          size="small"
          style="width: 140px"
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
        style="width: 160px"
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

      <!-- 画布模式：旋转视角/平移视角 -->
      <el-radio-group v-model="canvasMode" size="small" @change="onCanvasModeChange">
        <el-radio-button value="orbit">{{ t('scene3d.canvasModeOrbit') }}</el-radio-button>
        <el-radio-button value="pan">{{ t('scene3d.canvasModePan') }}</el-radio-button>
      </el-radio-group>

      <div class="fov-control">
        <span class="fov-label">FOV</span>
        <el-slider
          v-model="fovValue"
          :min="15"
          :max="100"
          :step="1"
          style="width: 120px"
          @change="onFovChange"
        />
        <span class="fov-value">{{ fovValue }}°</span>
      </div>

      <el-button size="small" plain @click="resetView">{{ t('scene3d.resetView') }}</el-button>
      <el-button size="small" plain :icon="QuestionFilled" @click="showHelp = true" />
    </div>

    <!-- 当前选中元素的自定义标记编辑面板 -->
    <div v-if="currentLabel !== null" class="scene3d-label-panel">
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
 * Scene3DEditor —— Three.js 3D 场景编辑器
 * 通过 v-model 双向绑定 scene_data，拖动 3D 元素时实时同步位置。
 * 支持多主体、多灯光、多道具，点击选中、灯光方向旋转、灯光预设、快捷键。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { Plus, Minus, QuestionFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useThemeStore } from '@/stores/theme'
import type { LightData, PropData, SceneData, Vec3 } from '@/types/scene'

const { t } = useI18n()
const themeStore = useThemeStore()

const props = defineProps<{
  modelValue: SceneData
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
}>()

const containerEl = ref<HTMLDivElement>()
// 当前可拖动元素类型与索引
type TargetType = 'camera' | 'subject' | 'light' | 'prop'
const activeTarget = ref<TargetType>('camera')
const activeIndex = ref(0)
const fovValue = ref(props.modelValue?.camera?.fov ?? 50)
// 变换模式：translate=移动 / rotate=旋转（所有元素均可旋转）
const transformMode = ref<'translate' | 'rotate'>('translate')
// 画布模式：orbit=左键旋转视角 / pan=左键平移视角（滚轮缩放始终可用）
const canvasMode = ref<'orbit' | 'pan'>('orbit')
const showHelp = ref(false)
const selectedPreset = ref<string>('')

// ---------- Three.js 内部对象（非响应式）----------
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let viewCamera: THREE.PerspectiveCamera | null = null
let orbitControls: OrbitControls | null = null
let transformControls: TransformControls | null = null
let cameraMesh: THREE.Group | null = null
// 相机拍摄方向引导线（从相机指向 lookAt 的箭头）
let cameraArrow: THREE.ArrowHelper | null = null
// 多元素 mesh 数组（主体/灯光为 Group，道具为 Mesh）
let subjectMeshes: THREE.Group[] = []
let lightMeshes: THREE.Group[] = []
let propMeshes: THREE.Mesh[] = []
let gridHelper: THREE.GridHelper | null = null
let animationId = 0
// Raycaster 用于点击选中
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()

// ---------- 主体颜色梯度（区分多个主体）----------
const SUBJECT_COLORS = [0x67c23a, 0x409eff, 0x9c27b0, 0xe6a23c, 0xf56c6c]
const PROP_COLOR = 0xe6a23c

// ---------- 默认场景数据 ----------
function defaultSceneData(): SceneData {
  return {
    subjects: [{ x: 0, y: 0, z: 0, label: t('scene3d.subjectDefaultLabel'), rotation: { x: 0, y: 0, z: 0 } }],
    camera: {
      position: { x: 0, y: 1.6, z: 5 },
      lookAt: { x: 0, y: 0, z: 0 },
      fov: 50,
    },
    lights: [{ type: 'directional', x: 5, y: 8, z: 5, intensity: 1.0, direction: { x: -0.47, y: -0.75, z: -0.47 } }],
    props: [],
    environment: { type: 'studio', label: t('scene3d.envStudio') },
  }
}

// ---------- 元素下拉选项 ----------
const elementOptions = computed(() => {
  if (activeTarget.value === 'subject') {
    return props.modelValue.subjects.map((s, i) => ({
      label: `${s.label || t('scene3d.targetSubject')} ${i + 1}`,
      value: i,
    }))
  }
  if (activeTarget.value === 'light') {
    return props.modelValue.lights.map((_, i) => ({
      label: `${t('scene3d.targetLight')} ${i + 1}`,
      value: i,
    }))
  }
  if (activeTarget.value === 'prop') {
    return props.modelValue.props.map((p, i) => ({
      label: `${p.label || t('scene3d.targetProp')} ${i + 1}`,
      value: i,
    }))
  }
  return []
})

// 是否可删除（主体和灯光至少保留 1 个，道具可全删）
const canRemove = computed(() => {
  if (activeTarget.value === 'subject') return props.modelValue.subjects.length > 1
  if (activeTarget.value === 'light') return props.modelValue.lights.length > 1
  if (activeTarget.value === 'prop') return props.modelValue.props.length > 0
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
  switch (preset) {
    case 'three_point':
      // 三点布光：主光（前上侧）+ 辅光（对侧填充）+ 轮廓光（背后顶）
      return [
        { type: 'directional', x: 4, y: 5, z: 4, intensity: 1.5, direction: dir(-4, -5, -4) },
        { type: 'directional', x: -4, y: 3, z: 3, intensity: 0.6, direction: dir(4, -3, -3) },
        { type: 'directional', x: 0, y: 6, z: -4, intensity: 1.0, direction: dir(0, -6, 4) },
      ]
    case 'rembrandt':
      // 伦勃朗光：单侧 45° 高位主光，制造三角光斑
      return [
        { type: 'directional', x: 5, y: 5, z: 3, intensity: 1.4, direction: dir(-5, -5, -3) },
        { type: 'directional', x: -4, y: 2, z: 4, intensity: 0.4, direction: dir(4, -2, -4) },
      ]
    case 'butterfly':
      // 蝴蝶光：正前方高位主光，鼻下制造蝴蝶形阴影
      return [
        { type: 'directional', x: 0, y: 6, z: 5, intensity: 1.5, direction: dir(0, -6, -5) },
        { type: 'directional', x: 0, y: 2, z: 5, intensity: 0.5, direction: dir(0, -2, -5) },
      ]
    case 'split':
      // 分割光：正侧光，明暗各半
      return [
        { type: 'directional', x: 6, y: 3, z: 0, intensity: 1.3, direction: dir(-6, -3, 0) },
      ]
    case 'loop':
      // 环形光：前侧 30° 主光，鼻影短小
      return [
        { type: 'directional', x: 3, y: 4, z: 5, intensity: 1.3, direction: dir(-3, -4, -5) },
        { type: 'directional', x: -3, y: 2, z: 4, intensity: 0.5, direction: dir(3, -2, -4) },
      ]
    case 'rim':
      // 轮廓光：背后侧逆光，勾勒边缘
      return [
        { type: 'directional', x: -3, y: 4, z: -5, intensity: 1.5, direction: dir(3, -4, 5) },
        { type: 'directional', x: 2, y: 3, z: 5, intensity: 0.6, direction: dir(-2, -3, -5) },
      ]
    default:
      return []
  }
}

/** 应用灯光预设：替换当前所有灯光 */
function applyLightPreset(preset: string) {
  if (!preset) return
  const lights = getLightPreset(preset)
  const newData: SceneData = { ...props.modelValue, lights }
  emit('update:modelValue', newData)
  rebuildElements()
  activeIndex.value = 0
  attachActive()
}

// ---------- 当前选中元素的 label（用于自定义标记编辑面板）----------
const currentLabel = computed<string | null>(() => {
  if (activeTarget.value === 'camera') return null // 相机无 label
  if (activeTarget.value === 'subject') {
    return props.modelValue.subjects[activeIndex.value]?.label ?? null
  }
  if (activeTarget.value === 'light') {
    // 灯光暂无 label 字段，未来可扩展
    return null
  }
  if (activeTarget.value === 'prop') {
    return props.modelValue.props[activeIndex.value]?.label ?? null
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
// 的约定是让 +z 轴指向目标（因 Mesh 正面法线沿 +z，lookAt 让正面朝向观察者）。
// 因此镜头放置在 +z 方向（前方/拍摄方向），lookAt() 直接对准主体即可正确指向。
function createCameraMesh(): THREE.Group {
  const group = new THREE.Group()
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x409eff, transparent: true, opacity: 0.85 })
  const lensMat = new THREE.MeshStandardMaterial({ color: 0x303133, transparent: true, opacity: 0.9 })
  const detailMat = new THREE.MeshStandardMaterial({ color: 0x909399 })

  // 机身（方块）
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.5, 0.4), bodyMat)
  body.position.y = 0.25
  group.add(body)

  // 镜头（圆柱，突出前方 +z，即拍摄方向）
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.5, 24), lensMat)
  lens.rotation.x = Math.PI / 2 // 圆柱默认沿 y，旋转到沿 z
  lens.position.set(0, 0.25, 0.45)
  group.add(lens)

  // 镜头前圈（装饰，镜头最前端）
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.04, 12, 24), detailMat)
  ring.position.set(0, 0.25, 0.7)
  group.add(ring)

  // 取景器（顶部小突起，朝 -z 即相机后方）
  const viewfinder = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 0.2), detailMat)
  viewfinder.position.set(0, 0.6, -0.1)
  group.add(viewfinder)

  // 标记：用于 Raycaster 识别为相机
  group.userData.type = 'camera'
  body.userData.type = 'camera'
  return group
}

// ---------- 创建人形主体（拟物化：头+身体+四肢）----------
function createSubjectMesh(index: number): THREE.Group {
  const group = new THREE.Group()
  const color = SUBJECT_COLORS[index % SUBJECT_COLORS.length]
  const skinMat = new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.85 })
  const clothMat = new THREE.MeshStandardMaterial({ color: color & 0xfefef0, transparent: true, opacity: 0.85 })

  // 头（球）
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 16), skinMat)
  head.position.y = 1.55
  group.add(head)

  // 身体（圆柱/方块，躯干）
  const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.3, 0.7, 12), clothMat)
  torso.position.y = 1.0
  group.add(torso)

  // 手臂（两个细圆柱）
  const armGeo = new THREE.CylinderGeometry(0.07, 0.07, 0.6, 8)
  const leftArm = new THREE.Mesh(armGeo, clothMat)
  leftArm.position.set(-0.32, 1.0, 0)
  leftArm.rotation.z = 0.2
  group.add(leftArm)
  const rightArm = new THREE.Mesh(armGeo, clothMat)
  rightArm.position.set(0.32, 1.0, 0)
  rightArm.rotation.z = -0.2
  group.add(rightArm)

  // 腿（两个细圆柱）
  const legGeo = new THREE.CylinderGeometry(0.09, 0.09, 0.6, 8)
  const leftLeg = new THREE.Mesh(legGeo, clothMat)
  leftLeg.position.set(-0.12, 0.3, 0)
  group.add(leftLeg)
  const rightLeg = new THREE.Mesh(legGeo, clothMat)
  rightLeg.position.set(0.12, 0.3, 0)
  group.add(rightLeg)

  // 标记：用于 Raycaster 识别为主体
  group.userData.type = 'subject'
  head.userData.type = 'subject'
  torso.userData.type = 'subject'
  return group
}

// ---------- 创建射灯形状（拟物化：灯体+锥形灯罩+灯头+方向引导线）----------
// 造型参考舞台射灯：圆柱灯体在上方，锥形灯罩开口朝下，灯头在灯罩底部，
// 整体照射方向默认沿 -y（向下），由 group 的旋转控制实际照射方向。
function createLightMesh(): THREE.Group {
  const group = new THREE.Group()
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x606266, transparent: true, opacity: 0.85 })
  const shadeMat = new THREE.MeshStandardMaterial({ color: 0x909399, transparent: true, opacity: 0.75 })
  // 灯头发光材质
  const bulbMat = new THREE.MeshStandardMaterial({
    color: 0xffd04b,
    emissive: 0xffd04b,
    emissiveIntensity: 0.7,
    transparent: true,
    opacity: 0.95,
  })

  // 灯体（圆柱，沿 y 轴，位于上方）
  const housing = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.4, 16), bodyMat)
  housing.position.y = 0.25
  group.add(housing)

  // 锥形灯罩（圆台，开口朝下，连接灯体与灯头）
  const shade = new THREE.Mesh(
    new THREE.CylinderGeometry(0.18, 0.32, 0.3, 16, 1, true),
    shadeMat,
  )
  shade.position.y = -0.05
  group.add(shade)

  // 灯头（小圆柱，底部发光口）
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.06, 16), bulbMat)
  lampHead.position.y = -0.2
  group.add(lampHead)

  // 方向引导线：默认沿 -y 方向（向下照射），长度 2.0，带箭头
  const arrowDir = new THREE.Vector3(0, -1, 0)
  const arrow = new THREE.ArrowHelper(
    arrowDir,
    new THREE.Vector3(0, -0.23, 0),
    2.0,
    0xffd04b,
    0.35,
    0.22,
  )
  group.add(arrow)

  // 标记：用于 Raycaster 识别为灯光
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
  const mat = new THREE.MeshStandardMaterial({
    color: PROP_COLOR,
    transparent: true,
    opacity: 0.5,
    wireframe: false,
  })
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
  // 场景背景与网格颜色根据当前主题设置
  updateThemeColors()

  viewCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
  viewCamera.position.set(6, 5, 8)
  viewCamera.lookAt(0, 1, 0)

  // 网格地面 + 坐标轴（颜色由 updateThemeColors 根据主题设置）
  gridHelper = new THREE.GridHelper(20, 20, 0x444466, 0x2a2a44)
  scene.add(gridHelper)
  const axes = new THREE.AxesHelper(2)
  scene.add(axes)

  // 场景照明
  const ambient = new THREE.AmbientLight(0xffffff, 0.4)
  scene.add(ambient)
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
  dirLight.position.set(5, 8, 5)
  scene.add(dirLight)

  // 相机指示
  cameraMesh = createCameraMesh()
  scene.add(cameraMesh)

  // 相机拍摄方向引导线（从相机指向 lookAt 的箭头）
  cameraArrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, -1),
    new THREE.Vector3(0, 0, 0),
    1,
    0x409eff,
    0.3,
    0.2,
  )
  scene.add(cameraArrow)

  // 应用初始数据（重建主体/灯光/道具）
  applySceneData(props.modelValue)

  // OrbitControls
  orbitControls = new OrbitControls(viewCamera, renderer.domElement)
  orbitControls.enableDamping = true
  orbitControls.dampingFactor = 0.1
  orbitControls.target.set(0, 1, 0)
  // 应用默认画布模式（左键旋转 / 右键平移）
  setCanvasMode('orbit')

  // TransformControls
  transformControls = new TransformControls(viewCamera, renderer.domElement)
  transformControls.addEventListener('dragging-changed', (e: any) => {
    if (orbitControls) orbitControls.enabled = !e.value
  })
  transformControls.addEventListener('objectChange', syncToModel)
  // Three.js 0.185+ TransformControls 不再直接继承 Object3D，需用 getHelper()
  scene.add(transformControls.getHelper())

  // 默认选中相机 + translate 模式
  setActiveTarget('camera')
  setTransformMode('translate')

  animate()
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onKeyDown)
}

function animate() {
  animationId = requestAnimationFrame(animate)
  if (orbitControls) orbitControls.update()
  if (renderer && scene && viewCamera) {
    renderer.render(scene, viewCamera)
  }
}

function onResize() {
  if (!containerEl.value || !renderer || !viewCamera) return
  const w = containerEl.value.clientWidth
  const h = containerEl.value.clientHeight
  renderer.setSize(w, h)
  viewCamera.aspect = w / h
  viewCamera.updateProjectionMatrix()
}

// ---------- 点击 3D 元素直接选中 ----------
function onCanvasClick(e: MouseEvent) {
  // 拖动中不处理
  if (transformControls?.dragging) return
  if (!containerEl.value || !renderer || !viewCamera) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, viewCamera)

  // 收集所有可选 mesh（含 group 内子 mesh）
  const targets: THREE.Object3D[] = []
  if (cameraMesh) targets.push(cameraMesh)
  subjectMeshes.forEach(m => targets.push(m))
  lightMeshes.forEach(g => {
    g.traverse(child => targets.push(child))
  })
  propMeshes.forEach(m => targets.push(m))

  const hits = raycaster.intersectObjects(targets, true)
  if (hits.length === 0) return

  const hit = hits[0].object
  // 向上查找带 userData.type 的祖先（灯光 group 的球被点击时需向上找 group）
  let obj: THREE.Object3D | null = hit
  while (obj && !obj.userData?.type) {
    obj = obj.parent
  }
  if (!obj) return

  const type = obj.userData.type as TargetType
  if (type === 'camera') {
    setActiveTarget('camera')
  } else if (type === 'subject') {
    // 向上找 subjectMeshes 中的 group
    let g: THREE.Object3D | null = obj
    while (g && !subjectMeshes.includes(g as THREE.Group)) {
      g = g.parent
    }
    if (g) {
      const idx = subjectMeshes.indexOf(g as THREE.Group)
      activeTarget.value = 'subject'
      activeIndex.value = idx
      attachActive()
    }
  } else if (type === 'light') {
    // 向上找 lightMeshes 中的 group
    let g: THREE.Object3D | null = obj
    while (g && !lightMeshes.includes(g as THREE.Group)) {
      g = g.parent
    }
    if (g) {
      const idx = lightMeshes.indexOf(g as THREE.Group)
      activeTarget.value = 'light'
      activeIndex.value = idx
      attachActive()
    }
  } else if (type === 'prop') {
    const idx = propMeshes.indexOf(obj as THREE.Mesh)
    if (idx >= 0) {
      activeTarget.value = 'prop'
      activeIndex.value = idx
      attachActive()
    }
  }
}

// ---------- 切换当前可拖动对象类型 ----------
function setActiveTarget(target: TargetType) {
  activeTarget.value = target
  // 切换类型时重置索引到 0
  if (target !== 'camera') {
    activeIndex.value = 0
  }
  attachActive()
}

function onTargetChange(val: TargetType) {
  setActiveTarget(val)
}

// ---------- 变换模式切换 ----------
function setTransformMode(mode: 'translate' | 'rotate') {
  transformMode.value = mode
  if (transformControls) {
    transformControls.setMode(mode)
  }
}

function onModeChange(val: 'translate' | 'rotate') {
  setTransformMode(val)
}

// ---------- 画布模式切换（旋转视角 / 平移视角）----------
function setCanvasMode(mode: 'orbit' | 'pan') {
  canvasMode.value = mode
  if (!orbitControls) return
  if (mode === 'orbit') {
    // 旋转模式：左键旋转，右键平移
    orbitControls.enableRotate = true
    orbitControls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    }
  } else {
    // 平移模式：左键平移，右键旋转
    orbitControls.enableRotate = true
    orbitControls.mouseButtons = {
      LEFT: THREE.MOUSE.PAN,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.ROTATE,
    }
  }
}

function onCanvasModeChange(val: 'orbit' | 'pan') {
  setCanvasMode(val)
}

// ---------- 把 TransformControls 附着到当前选中元素 ----------
function attachActive() {
  if (!transformControls) return
  if (activeTarget.value === 'camera') {
    if (cameraMesh) transformControls.attach(cameraMesh)
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
  if (activeTarget.value === 'subject') {
    newData.subjects.push({
      x: 2 + newData.subjects.length,
      y: 0,
      z: 0,
      label: `${t('scene3d.subjectDefaultLabel')}${newData.subjects.length + 1}`,
      rotation: { x: 0, y: 0, z: 0 },
    })
    activeIndex.value = newData.subjects.length - 1
  } else if (activeTarget.value === 'light') {
    newData.lights.push({
      type: 'directional',
      x: -5,
      y: 5,
      z: -5,
      intensity: 0.6,
      direction: { x: 0.58, y: -0.58, z: 0.58 },
    })
    activeIndex.value = newData.lights.length - 1
  } else if (activeTarget.value === 'prop') {
    newData.props.push({
      type: 'box',
      x: 1 + newData.props.length,
      y: 0,
      z: -2,
      label: `${t('scene3d.propDefaultLabel')}${newData.props.length + 1}`,
      rotation: { x: 0, y: 0, z: 0 },
    })
    activeIndex.value = newData.props.length - 1
  }
  emit('update:modelValue', newData)
  rebuildElements()
  attachActive()
}

// ---------- 删除当前选中元素 ----------
function removeElement() {
  if (!canRemove.value) return
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  if (activeTarget.value === 'subject') {
    newData.subjects.splice(activeIndex.value, 1)
  } else if (activeTarget.value === 'light') {
    newData.lights.splice(activeIndex.value, 1)
  } else if (activeTarget.value === 'prop') {
    newData.props.splice(activeIndex.value, 1)
  }
  activeIndex.value = Math.max(0, activeIndex.value - 1)
  emit('update:modelValue', newData)
  rebuildElements()
  attachActive()
}

// ---------- 把 3D 对象位置/方向/旋转同步回 modelValue ----------
function syncToModel() {
  const newData: SceneData = JSON.parse(JSON.stringify(props.modelValue))
  // 同步相机（旋转时更新 lookAt）
  if (cameraMesh) {
    newData.camera.position = {
      x: round(cameraMesh.position.x),
      y: round(cameraMesh.position.y),
      z: round(cameraMesh.position.z),
    }
    newData.camera.fov = fovValue.value
    // 相机旋转后，根据朝向更新 lookAt
    // cameraMesh 是普通 Group，Object3D.lookAt() 让 +z 轴指向目标（前向为 +z）
    // 旋转后 forward = (0,0,1).applyQuaternion(cameraMesh.quaternion)
    const forward = new THREE.Vector3(0, 0, 1)
    forward.applyQuaternion(cameraMesh.quaternion)
    // 保持原 lookAt 距离
    const origLook = newData.camera.lookAt || { x: 0, y: 0, z: 0 }
    const dist = Math.sqrt(
      (origLook.x - cameraMesh.position.x) ** 2 +
      (origLook.y - cameraMesh.position.y) ** 2 +
      (origLook.z - cameraMesh.position.z) ** 2,
    ) || 5
    newData.camera.lookAt = {
      x: round(cameraMesh.position.x + forward.x * dist),
      y: round(cameraMesh.position.y + forward.y * dist),
      z: round(cameraMesh.position.z + forward.z * dist),
    }
    // 同步相机拍摄方向引导线（从相机指向 lookAt）
    updateCameraArrow(newData.camera.lookAt)
  }
  // 同步主体（位置 + 旋转）
  subjectMeshes.forEach((m, i) => {
    if (newData.subjects[i]) {
      newData.subjects[i].x = round(m.position.x)
      newData.subjects[i].z = round(m.position.z)
      // 旋转弧度转欧拉角度
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
      // 默认方向 (0,-1,0) 应用 group 的四元数得到实际方向
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
  const from = new THREE.Vector3(0, -1, 0) // 默认朝向
  const to = new THREE.Vector3(dir.x || 0, dir.y || -1, dir.z || 0)
  if (to.lengthSq() === 0) return new THREE.Quaternion()
  to.normalize()
  return new THREE.Quaternion().setFromUnitVectors(from, to)
}

// ---------- 更新相机拍摄方向引导线（从相机指向 lookAt）----------
function updateCameraArrow(lookAt: Vec3) {
  if (!cameraArrow || !cameraMesh) return
  const from = cameraMesh.position.clone()
  const to = new THREE.Vector3(lookAt.x, lookAt.y, lookAt.z)
  const dir = to.clone().sub(from)
  const len = dir.length()
  if (len < 0.01) return
  dir.normalize()
  cameraArrow.position.copy(from)
  cameraArrow.setDirection(dir)
  // 引导线长度略短于实际距离，避免箭头穿过目标
  cameraArrow.setLength(Math.min(len, 6), 0.3, 0.2)
}

// ---------- 重建主体/灯光/道具 mesh（基于 modelValue）----------
function rebuildElements() {
  if (!scene) return
  // 移除旧 mesh
  subjectMeshes.forEach(m => scene!.remove(m))
  lightMeshes.forEach(m => scene!.remove(m))
  propMeshes.forEach(m => scene!.remove(m))
  subjectMeshes = []
  lightMeshes = []
  propMeshes = []

  const d = props.modelValue
  // 重建主体（应用位置 + 旋转）
  d.subjects.forEach((s) => {
    const mesh = createSubjectMesh(subjectMeshes.length)
    mesh.position.set(s.x, 0, s.z)
    // 应用 rotation（欧拉角转弧度）
    const rot = s.rotation || { x: 0, y: 0, z: 0 }
    mesh.rotation.set(
      (rot.x || 0) * Math.PI / 180,
      (rot.y || 0) * Math.PI / 180,
      (rot.z || 0) * Math.PI / 180,
    )
    scene!.add(mesh)
    subjectMeshes.push(mesh)
  })
  // 重建灯光（应用位置 + 方向旋转）
  d.lights.forEach((l) => {
    const mesh = createLightMesh()
    mesh.position.set(l.x, l.y, l.z)
    // 应用方向向量到 group 旋转
    const dir = l.direction || { x: 0, y: -1, z: 0 }
    mesh.quaternion.copy(directionToQuaternion(dir))
    scene!.add(mesh)
    lightMeshes.push(mesh)
  })
  // 重建道具（应用位置 + 旋转）
  d.props.forEach((p) => {
    const mesh = createPropMesh(p.type)
    mesh.position.set(p.x, p.y || 0.4, p.z)
    const rot = p.rotation || { x: 0, y: 0, z: 0 }
    mesh.rotation.set(
      (rot.x || 0) * Math.PI / 180,
      (rot.y || 0) * Math.PI / 180,
      (rot.z || 0) * Math.PI / 180,
    )
    scene!.add(mesh)
    propMeshes.push(mesh)
  })
}

// ---------- 把 modelValue 应用到 3D 对象 ----------
function applySceneData(data: SceneData) {
  if (!scene) return
  const d = data || defaultSceneData()

  // 相机：设置位置 + 朝向 lookAt（让镜头对准目标）
  // cameraMesh 是普通 Group，lookAt() 让 +z 轴（镜头方向）指向目标
  if (cameraMesh && d.camera?.position) {
    cameraMesh.position.set(
      d.camera.position.x,
      d.camera.position.y,
      d.camera.position.z,
    )
    const look = d.camera.lookAt || { x: 0, y: 0, z: 0 }
    cameraMesh.lookAt(look.x, look.y, look.z)
    // 更新拍摄方向引导线
    updateCameraArrow(look)
  }
  fovValue.value = d.camera?.fov ?? 50

  // 重建主体/灯光/道具
  rebuildElements()
}

// ---------- FOV 滑块改变 ----------
function onFovChange(val: number) {
  if (!viewCamera) return
  viewCamera.fov = val
  viewCamera.updateProjectionMatrix()
  syncToModel()
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
  // 场景背景：深色用深蓝黑，浅色用浅灰白
  scene.background = new THREE.Color(isDark ? 0x0b0f1a : 0xeaeef6)
  // 网格颜色：深色用暗蓝灰，浅色用浅灰
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
  // 输入框内不触发
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return

  const key = e.key.toLowerCase()
  if (key === '1') setActiveTarget('camera')
  else if (key === '2') setActiveTarget('subject')
  else if (key === '3') setActiveTarget('light')
  else if (key === '4') setActiveTarget('prop')
  else if (key === 'w') setTransformMode('translate')
  else if (key === 'e') {
    // 旋转模式对所有元素生效（相机/主体/灯光/道具均可旋转）
    setTransformMode('rotate')
  }
  else if (key === 'q') {
    // 切换画布模式（旋转视角 / 平移视角）
    setCanvasMode(canvasMode.value === 'orbit' ? 'pan' : 'orbit')
  }
  else if (key === 'n') {
    if (activeTarget.value !== 'camera') addElement()
  }
  else if (key === 'delete' || key === 'backspace') {
    if (activeTarget.value !== 'camera') removeElement()
  }
  else if (key === 'r') resetView()
  else if (key === '?' || (e.shiftKey && key === '/')) showHelp.value = !showHelp.value
}

// ---------- 外部 modelValue 变化时同步到 3D（避免循环，仅当非拖动状态）----------
watch(
  () => props.modelValue,
  (val) => {
    if (!val) return
    if (val.camera?.fov != null) fovValue.value = val.camera.fov
    // 仅在非拖动时应用，避免拖动中又被回写
    if (transformControls && !transformControls.dragging) {
      applySceneData(val)
      // 重新附着当前选中元素（元素数量可能变化）
      attachActive()
    }
  },
  { deep: true },
)

onMounted(() => {
  initThree()
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onKeyDown)
  if (transformControls) transformControls.dispose()
  if (orbitControls) orbitControls.dispose()
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
  min-height: 480px;
  position: relative;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--agnes-bg-base);
}

.scene3d-canvas {
  flex: 1;
  width: 100%;
  min-height: 420px;
  cursor: pointer;
}

.scene3d-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 10;
  flex-wrap: wrap;
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

/* 左下角图例已移除 */

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

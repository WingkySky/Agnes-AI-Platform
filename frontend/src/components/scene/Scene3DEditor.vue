<!-- =====================================================
     Scene3DEditor —— Three.js 3D 场景布局编辑器（导演台 MVP）
     功能：
       - 3D 视图：网格地面 + 相机锥体 + 主体方块 + 方向光箭头
       - OrbitControls 旋转/缩放查看视角
       - TransformControls 拖动相机/主体/灯光改变位置
       - 实时输出 scene_data（v-model）
       - FOV 滑块调节相机视场角
     使用方式：
       <Scene3DEditor v-model="sceneData" />
     ===================================================== -->

<template>
  <div class="scene3d-editor">
    <!-- 3D 渲染容器 -->
    <div ref="containerEl" class="scene3d-canvas" />

    <!-- 工具栏：切换当前可拖动对象 + FOV 调节 -->
    <div class="scene3d-toolbar">
      <el-radio-group v-model="activeTarget" size="small" @change="onTargetChange">
        <el-radio-button value="camera">{{ t('scene3d.targetCamera') }}</el-radio-button>
        <el-radio-button value="subject">{{ t('scene3d.targetSubject') }}</el-radio-button>
        <el-radio-button value="light">{{ t('scene3d.targetLight') }}</el-radio-button>
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
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Scene3DEditor —— Three.js 3D 场景编辑器
 * 通过 v-model 双向绑定 scene_data，拖动 3D 元素时实时同步位置。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { useI18n } from '@/i18n'
import type { SceneData } from '@/types/scene'

const { t } = useI18n()

const props = defineProps<{
  modelValue: SceneData
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
}>()

const containerEl = ref<HTMLDivElement>()
const activeTarget = ref<'camera' | 'subject' | 'light'>('camera')
const fovValue = ref(props.modelValue?.camera?.fov ?? 50)

// ---------- Three.js 内部对象（非响应式）----------
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let viewCamera: THREE.PerspectiveCamera | null = null
let orbitControls: OrbitControls | null = null
let transformControls: TransformControls | null = null
let cameraMesh: THREE.Group | null = null
let subjectMesh: THREE.Mesh | null = null
let lightMesh: THREE.Group | null = null
let directionalLight: THREE.DirectionalLight | null = null
let animationId = 0

// ---------- 默认场景数据 ----------
function defaultSceneData(): SceneData {
  return {
    subject: { x: 0, y: 0, z: 0, label: '主体' },
    camera: {
      position: { x: 0, y: 1.6, z: 5 },
      lookAt: { x: 0, y: 0, z: 0 },
      fov: 50,
    },
    lights: [
      { type: 'directional', x: 5, y: 8, z: 5, intensity: 1.0 },
    ],
  }
}

// ---------- 创建相机锥体（表示导演台相机位置）----------
function createCameraMesh(): THREE.Group {
  const group = new THREE.Group()
  // 锥体表示相机机身，朝向 -z
  const geo = new THREE.ConeGeometry(0.3, 0.6, 4)
  geo.rotateX(Math.PI / 2)
  const mat = new THREE.MeshBasicMaterial({ color: 0x409eff, wireframe: false })
  const cone = new THREE.Mesh(geo, mat)
  group.add(cone)
  // 添加边框线让相机更醒目
  const edges = new THREE.EdgesGeometry(geo)
  const line = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({ color: 0xffffff }),
  )
  group.add(line)
  return group
}

// ---------- 创建主体方块 ----------
function createSubjectMesh(): THREE.Mesh {
  const geo = new THREE.BoxGeometry(0.8, 1.6, 0.8)
  const mat = new THREE.MeshStandardMaterial({
    color: 0x67c23a,
    transparent: true,
    opacity: 0.6,
  })
  const mesh = new THREE.Mesh(geo, mat)
  mesh.position.y = 0.8 // 方块底部贴地
  return mesh
}

// ---------- 创建灯光指示（箭头 + 小球）----------
function createLightMesh(): THREE.Group {
  const group = new THREE.Group()
  // 小球表示灯
  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(0.2, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0xffd04b }),
  )
  group.add(ball)
  // 箭头从灯指向原点
  const dir = new THREE.Vector3(-1, -1, -1).normalize()
  const arrow = new THREE.ArrowHelper(
    dir,
    new THREE.Vector3(0, 0, 0),
    2.0,
    0xffd04b,
    0.3,
    0.2,
  )
  group.add(arrow)
  return group
}

// ---------- 初始化 Three.js 场景 ----------
function initThree() {
  if (!containerEl.value) return
  const width = containerEl.value.clientWidth
  const height = containerEl.value.clientHeight

  // 渲染器
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(width, height)
  renderer.setPixelRatio(window.devicePixelRatio)
  containerEl.value.appendChild(renderer.domElement)

  // 场景
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a1a2e)

  // 视图相机（用于查看场景，非导演台相机）
  viewCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
  viewCamera.position.set(6, 5, 8)
  viewCamera.lookAt(0, 1, 0)

  // 网格地面
  const grid = new THREE.GridHelper(20, 20, 0x444466, 0x2a2a44)
  scene.add(grid)

  // 坐标轴
  const axes = new THREE.AxesHelper(2)
  scene.add(axes)

  // 环境光 + 方向光（场景照明）
  const ambient = new THREE.AmbientLight(0xffffff, 0.4)
  scene.add(ambient)
  directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
  directionalLight.position.set(5, 8, 5)
  scene.add(directionalLight)

  // 导演台元素：相机、主体、灯光指示
  cameraMesh = createCameraMesh()
  scene.add(cameraMesh)
  subjectMesh = createSubjectMesh()
  scene.add(subjectMesh)
  lightMesh = createLightMesh()
  scene.add(lightMesh)

  // 应用初始数据
  applySceneData(props.modelValue)

  // OrbitControls：旋转/缩放查看
  orbitControls = new OrbitControls(viewCamera, renderer.domElement)
  orbitControls.enableDamping = true
  orbitControls.dampingFactor = 0.1
  orbitControls.target.set(0, 1, 0)

  // TransformControls：拖动元素
  transformControls = new TransformControls(viewCamera, renderer.domElement)
  transformControls.addEventListener('dragging-changed', (e: any) => {
    if (orbitControls) orbitControls.enabled = !e.value
  })
  transformControls.addEventListener('objectChange', syncToModel)
  // Three.js 0.185+ TransformControls 不再直接继承 Object3D，需用 getHelper() 获取场景对象
  scene.add(transformControls.getHelper())

  // 默认选中相机
  setActiveTarget('camera')

  // 渲染循环
  animate()

  // 窗口大小变化
  window.addEventListener('resize', onResize)
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

// ---------- 切换当前可拖动对象 ----------
function setActiveTarget(target: 'camera' | 'subject' | 'light') {
  if (!transformControls) return
  if (target === 'camera' && cameraMesh) {
    transformControls.attach(cameraMesh)
  } else if (target === 'subject' && subjectMesh) {
    transformControls.attach(subjectMesh)
  } else if (target === 'light' && lightMesh) {
    transformControls.attach(lightMesh)
  }
}

function onTargetChange(val: 'camera' | 'subject' | 'light') {
  setActiveTarget(val)
}

// ---------- 把 3D 对象位置同步回 modelValue ----------
function syncToModel() {
  if (!cameraMesh || !subjectMesh || !lightMesh) return
  const camPos = cameraMesh.position
  const subPos = subjectMesh.position
  const lightPos = lightMesh.position

  const newData: SceneData = {
    subject: {
      x: round(subPos.x),
      y: 0, // 主体 y 固定贴地
      z: round(subPos.z),
      label: props.modelValue?.subject?.label ?? '主体',
    },
    camera: {
      position: { x: round(camPos.x), y: round(camPos.y), z: round(camPos.z) },
      lookAt: props.modelValue?.camera?.lookAt ?? { x: 0, y: 0, z: 0 },
      fov: fovValue.value,
    },
    lights: [
      {
        type: 'directional',
        x: round(lightPos.x),
        y: round(lightPos.y),
        z: round(lightPos.z),
        intensity: props.modelValue?.lights?.[0]?.intensity ?? 1.0,
      },
    ],
  }
  emit('update:modelValue', newData)
}

function round(n: number): number {
  return Math.round(n * 100) / 100
}

// ---------- 把 modelValue 应用到 3D 对象 ----------
function applySceneData(data: SceneData) {
  if (!cameraMesh || !subjectMesh || !lightMesh) return
  const d = data || defaultSceneData()

  cameraMesh.position.set(d.camera.position.x, d.camera.position.y, d.camera.position.z)
  // 主体 y 固定贴地（方块中心 y=0.8）
  subjectMesh.position.set(d.subject.x, 0.8, d.subject.z)
  if (d.lights?.[0]) {
    lightMesh.position.set(d.lights[0].x, d.lights[0].y, d.lights[0].z)
  }
  fovValue.value = d.camera.fov
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

// ---------- 外部 modelValue 变化时同步到 3D（避免循环，仅当非拖动状态）----------
watch(
  () => props.modelValue,
  (val) => {
    if (!val) return
    if (val.camera?.fov != null) fovValue.value = val.camera.fov
    // 仅在非拖动时应用，避免拖动中又被回写
    if (transformControls && !transformControls.dragging) {
      applySceneData(val)
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
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  overflow: hidden;
  background: #1a1a2e;
}

.scene3d-canvas {
  flex: 1;
  width: 100%;
  min-height: 420px;
}

.scene3d-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
  backdrop-filter: blur(4px);
  z-index: 10;
  flex-wrap: wrap;
}

.fov-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fov-label {
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
  white-space: nowrap;
}

.fov-value {
  font-size: 13px;
  color: var(--el-text-color-secondary, #909399);
  min-width: 36px;
}
</style>

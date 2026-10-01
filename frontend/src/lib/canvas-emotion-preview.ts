/* =====================================================
 * canvas-emotion-preview — 表情实时预览（three.js 灰模头模）
 * - 加载剥掉纹理依赖的 facecap.glb（meshopt 解码为 JS 模块，无 basis 转码器）
 * - 情绪 blendshapes（ARKit 命名）→ morph target 权重 220ms 缓动过渡
 * - 仅加载与动画期间渲染（按需渲染，无持续 rAF）
 * 供 CanvasEmotionDialog 使用
 * ===================================================== */

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'

import type { EmotionBlendshapes } from './canvas-emotion'

export interface EmotionFacePreview {
  setShapes: (shapes: EmotionBlendshapes) => void
  dispose: () => void
}

const EASE_DURATION = 220
const MODEL_URL = '/canvas/models/facecap.glb'

/** 创建头模预览实例：接管传入 canvas 的 WebGL 上下文，onError 供弹窗提示加载失败 */
export function createEmotionFacePreview(canvas: HTMLCanvasElement, onError?: (message: string) => void): EmotionFacePreview {
  const width = canvas.clientWidth || 220
  const height = canvas.clientHeight || 220
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  renderer.setSize(width, height, false)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(38, width / Math.max(1, height), 0.1, 20)
  camera.position.set(0, 0, 4.15)
  scene.add(new THREE.AmbientLight(0xffffff, 0.82))
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.45)
  keyLight.position.set(-2.8, 4, 3)
  scene.add(keyLight)
  const fillLight = new THREE.DirectionalLight(0xc9d0dc, 0.5)
  fillLight.position.set(3, 1, 2)
  scene.add(fillLight)

  let model: THREE.Object3D | null = null
  let meshes: THREE.Mesh[] = []
  let raf: number | null = null
  let pendingTargets: EmotionBlendshapes | null = null
  const render = () => renderer.render(scene, camera)

  const loader = new GLTFLoader()
  loader.setMeshoptDecoder(MeshoptDecoder)
  loader.load(
    MODEL_URL,
    (gltf) => {
      model = createMannequinModel(gltf.scene)
      meshes = morphMeshes(model)
      scene.add(model)
      render()
      // 模型加载晚于选预设时，补应用最近一次目标表情
      if (pendingTargets) {
        setShapes(pendingTargets)
        pendingTargets = null
      }
    },
    undefined,
    (error) => onError?.(error instanceof Error ? error.message : String(error)),
  )

  // morph 权重缓动：从当前值插值到目标 blendshapes，动画结束即停帧
  const setShapes = (targets: EmotionBlendshapes) => {
    if (!meshes.length) {
      pendingTargets = targets
      return
    }
    const starts = meshes.map(mesh => [...(mesh.morphTargetInfluences || [])])
    const startTime = performance.now()
    if (raf !== null) cancelAnimationFrame(raf)
    const step = (now: number) => {
      const progress = Math.min(1, (now - startTime) / EASE_DURATION)
      const eased = 1 - Math.pow(1 - progress, 3)
      meshes.forEach((mesh, meshIndex) => {
        const dictionary = mesh.morphTargetDictionary || {}
        const influences = mesh.morphTargetInfluences || []
        for (const [name, index] of Object.entries(dictionary)) {
          const target = targets[name] || 0
          influences[index] = (starts[meshIndex][index] || 0) + (target - (starts[meshIndex][index] || 0)) * eased
        }
      })
      render()
      raf = progress < 1 ? requestAnimationFrame(step) : null
    }
    raf = requestAnimationFrame(step)
  }

  return {
    setShapes,
    dispose: () => {
      if (raf !== null) cancelAnimationFrame(raf)
      raf = null
      if (model) {
        model.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose()
            ;(Array.isArray(object.material) ? object.material : [object.material]).forEach(material => material.dispose())
          }
        })
        scene.remove(model)
        model = null
      }
      renderer.dispose()
      // 不主动丢上下文会占住浏览器的 WebGL 上下文配额（约 16 个），反复开关弹窗后新建渲染器会抛错
      renderer.forceContextLoss()
    },
  }
}

/** 克隆模型并统一替换为哑光灰模材质；按包围盒归一化尺寸并居中，避免导出版本差异导致偏移 */
function createMannequinModel(source: THREE.Object3D): THREE.Object3D {
  const model = source.clone(true)
  model.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return
    object.material = new THREE.MeshStandardMaterial({ color: new THREE.Color('#aaacae'), roughness: 0.9, metalness: 0.01 })
    object.castShadow = false
    object.receiveShadow = false
  })
  const bounds = new THREE.Box3().setFromObject(model)
  const size = bounds.getSize(new THREE.Vector3())
  model.scale.multiplyScalar(2.35 / Math.max(size.y, 0.001))
  const normalized = new THREE.Box3().setFromObject(model)
  model.position.sub(normalized.getCenter(new THREE.Vector3()))
  return model
}

/** 收集带 morph target 的网格（facecap 的头模网格承载全部 ARKIT 表情） */
function morphMeshes(model: THREE.Object3D): THREE.Mesh[] {
  const meshes: THREE.Mesh[] = []
  model.traverse((object) => {
    if (object instanceof THREE.Mesh && object.morphTargetDictionary && object.morphTargetInfluences) meshes.push(object)
  })
  return meshes
}

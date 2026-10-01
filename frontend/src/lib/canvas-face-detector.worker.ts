/// <reference lib="webworker" />

import { FaceDetector } from '@mediapipe/tasks-vision'
// 加载器与 wasm 运行时从 npm 包按 URL 引入（与安装版本严格配对，不在 public 冗余存放）。
// 必须用 ESM 变体 vision_wasm_module_internal.*：模块 Worker 里 MediaPipe 走动态 import，
// UMD 变体（vision_wasm_internal.js）没有 export，会报 "ModuleFactory not set"。
import wasmLoaderUrl from '@mediapipe/tasks-vision/vision_wasm_module_internal.js?url'
import wasmBinaryUrl from '@mediapipe/tasks-vision/vision_wasm_module_internal.wasm?url'

import type { EmotionFaceBox } from './canvas-emotion'

type DetectFaceRequest = { id: number; image: ImageBitmap }
type DetectFaceResponse = { id: number; faces?: EmotionFaceBox[]; imageWidth?: number; imageHeight?: number; error?: string }

let detectorPromise: Promise<FaceDetector> | null = null

const workerGlobal = self as typeof self & {
  importScripts: (...urls: string[]) => void
  import?: (url: string) => Promise<unknown>
}

// MediaPipe 在模块 Worker 中 importScripts 不可用，会转向 self.import 动态引入加载器；
// 这里显式接管为 blob URL import，避免 Vite 把运行时 URL 当源码模块转换。
workerGlobal.importScripts = () => { throw new TypeError('module worker uses dynamic import') }
workerGlobal.import = async (url: string) => {
  const response = await fetch(url.replace(/\?import(?:&.*)?$/, ''))
  if (!response.ok) throw new Error(`wasm loader 加载失败：${response.status}`)
  const blobUrl = URL.createObjectURL(new Blob([await response.text()], { type: 'text/javascript' }))
  try {
    return await import(/* @vite-ignore */ blobUrl)
  } finally {
    URL.revokeObjectURL(blobUrl)
  }
}

function getDetector() {
  if (!detectorPromise) {
    detectorPromise = FaceDetector.createFromOptions(
      { wasmLoaderPath: wasmLoaderUrl, wasmBinaryPath: wasmBinaryUrl },
      {
        baseOptions: { modelAssetPath: '/canvas/models/blaze-face-full-range-sparse.tflite' },
        runningMode: 'IMAGE',
        minDetectionConfidence: 0.25,
        minSuppressionThreshold: 0.3,
      },
    )
  }
  return detectorPromise
}

self.onmessage = async (event: MessageEvent<DetectFaceRequest>) => {
  const { id, image } = event.data
  const response: DetectFaceResponse = { id, imageWidth: image.width, imageHeight: image.height }
  try {
    const detector = await getDetector()
    response.faces = detector.detect(image).detections.flatMap((detection, index) => {
      const box = detection.boundingBox
      if (!box) return []
      return [{
        id: `face-${id}-${index}`,
        x: box.originX,
        y: box.originY,
        width: box.width,
        height: box.height,
        confidence: detection.categories[0]?.score,
        source: 'detected' as const,
        // 关键点归一化坐标转像素（前两位为双眼，供表情合成做取景对齐）
        keypoints: detection.keypoints?.map(point => ({ x: point.x * image.width, y: point.y * image.height })),
      }]
    })
  } catch (error) {
    response.error = error instanceof Error ? error.message : '人脸识别失败'
  } finally {
    image.close()
  }
  self.postMessage(response)
}

export {}

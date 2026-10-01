/* =====================================================
 * canvas-face-detection — 人脸检测主线程封装
 * - 模块 Worker 内跑 MediaPipe FaceDetector，不阻塞画布交互
 * - 每次检测独立建/销毁 worker（低频操作，无需常驻）
 * ===================================================== */

import type { EmotionFaceBox } from './canvas-emotion'

export interface FaceDetectionResult {
  faces: EmotionFaceBox[]
  imageWidth: number
  imageHeight: number
}

/** 检测图片中的人脸框（imageUrl 需可 fetch：dataURL 或同源/代理地址） */
export async function detectFaces(imageUrl: string): Promise<FaceDetectionResult> {
  const response = await fetch(imageUrl)
  if (!response.ok) throw new Error(`图片读取失败：${response.status}`)
  const bitmap = await createImageBitmap(await response.blob())
  const worker = new Worker(new URL('./canvas-face-detector.worker.ts', import.meta.url), { type: 'module' })
  try {
    return await new Promise<FaceDetectionResult>((resolve, reject) => {
      const id = Date.now()
      const timeout = setTimeout(() => reject(new Error('人脸识别超时')), 30_000)
      worker.onmessage = (event: MessageEvent<{ id: number; faces?: EmotionFaceBox[]; imageWidth?: number; imageHeight?: number; error?: string }>) => {
        if (event.data.id !== id) return
        clearTimeout(timeout)
        if (event.data.error) reject(new Error(event.data.error))
        else resolve({ faces: event.data.faces || [], imageWidth: event.data.imageWidth || bitmap.width, imageHeight: event.data.imageHeight || bitmap.height })
      }
      worker.onerror = (event) => {
        clearTimeout(timeout)
        reject(new Error(event.message || '人脸识别失败'))
      }
      worker.postMessage({ id, image: bitmap }, [bitmap])
    })
  } finally {
    worker.terminate()
  }
}

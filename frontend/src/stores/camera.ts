/* =====================================================
 * 摄像机 Store — Pinia 状态管理
 * - enabled 开关、当前 camera_params、预设列表、选中预设 ID
 * - toggleCamera / setCameraParams / loadPresets / selectPreset
 * ===================================================== */

import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { getCameraPresets, type CameraPreset } from '@/api/cameraPresets'
import type { CameraParams } from '@/types/camera'

export const useCameraStore = defineStore('camera', () => {
  /* ==== 状态 ==== */

  /** 摄像机是否启用 */
  const enabled = ref(false)

  /** 当前摄像机参数 */
  const cameraParams = reactive<CameraParams>({
    enabled: false,
  })

  /** 预设列表 */
  const presets = ref<CameraPreset[]>([])

  /** 预设加载中 */
  const presetsLoading = ref(false)

  /** 预设是否已加载 */
  const presetsLoaded = ref(false)

  /** 当前选中的预设 ID */
  const selectedPresetId = ref<number | null>(null)

  /* ==== Actions ==== */

  /** 切换摄像机启用/禁用 */
  function toggleCamera() {
    enabled.value = !enabled.value
    cameraParams.enabled = enabled.value
  }

  /** 设置当前摄像机参数（合并更新） */
  function setCameraParams(params: Partial<CameraParams>) {
    Object.assign(cameraParams, params)
  }

  /** 加载预设列表 */
  async function loadPresets() {
    if (presetsLoading.value) return
    presetsLoading.value = true
    try {
      const result = await getCameraPresets({ page_size: 200 })
      presets.value = result.items
      presetsLoaded.value = true
    } catch (e) {
      console.error('加载摄像机预设失败:', e)
      throw e
    } finally {
      presetsLoading.value = false
    }
  }

  /** 选中预设并填充参数 */
  function selectPreset(presetId: number | null) {
    selectedPresetId.value = presetId
    if (presetId === null) {
      // 清空参数但保留 enabled 状态
      const wasEnabled = cameraParams.enabled
      const keys = Object.keys(cameraParams) as (keyof CameraParams)[]
      for (const k of keys) {
        if (k === 'enabled') continue
        ;(cameraParams as any)[k] = undefined
      }
      return
    }
    const preset = presets.value.find((p) => p.id === presetId)
    if (!preset) return
    cameraParams.camera_model = preset.camera_model
    cameraParams.focal_length = preset.focal_length
    cameraParams.aperture = preset.aperture
    cameraParams.depth_of_field = preset.depth_of_field
    cameraParams.shutter_speed = preset.shutter_speed
    cameraParams.shutter_angle = preset.shutter_angle
    cameraParams.camera_movement = preset.camera_movement
    cameraParams.camera_angle = preset.camera_angle
    cameraParams.aspect_ratio = preset.aspect_ratio
    cameraParams.visual_style = preset.visual_style
  }

  /** 从预设对象直接设置参数（无需先加载presets列表） */
  function applyPresetObject(preset: Record<string, string | undefined>) {
    cameraParams.camera_model = preset.camera_model || undefined
    cameraParams.focal_length = preset.focal_length || undefined
    cameraParams.aperture = preset.aperture || undefined
    cameraParams.depth_of_field = preset.depth_of_field || undefined
    cameraParams.shutter_speed = preset.shutter_speed || undefined
    cameraParams.shutter_angle = preset.shutter_angle || undefined
    cameraParams.camera_movement = preset.camera_movement || undefined
    cameraParams.camera_angle = preset.camera_angle || undefined
    cameraParams.aspect_ratio = preset.aspect_ratio || undefined
    cameraParams.visual_style = preset.visual_style || undefined
  }

  /** 清除所有摄像机状态 */
  function clearAll() {
    enabled.value = false
    const keys = Object.keys(cameraParams) as (keyof CameraParams)[]
    for (const k of keys) {
      ;(cameraParams as any)[k] = k === 'enabled' ? false : undefined
    }
    presets.value = []
    presetsLoaded.value = false
    selectedPresetId.value = null
  }

  /* ==== 导出 ==== */
  return {
    enabled,
    cameraParams,
    presets,
    presetsLoading,
    presetsLoaded,
    selectedPresetId,
    toggleCamera,
    setCameraParams,
    loadPresets,
    selectPreset,
    applyPresetObject,
    clearAll,
  }
})

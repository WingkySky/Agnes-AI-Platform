/* =====================================================
 * 场景挂载生成纯函数（导演台第一批）
 * scene_data.camera → camera_params 映射（对齐后端 scene_service 翻译器阈值）
 * 与挂载后缀拼接。
 * ===================================================== */

export interface SceneMount {
  scene_id: number
  name: string
  suffix: string
  camera: { position: { x: number; y: number; z: number }; target: { x: number; y: number; z: number }; fov: number } | null
}

/**
 * 场景相机 → camera_params 子集（视角 + 焦段），喂给后端 build_camera_prompt_suffix。
 * 阈值对齐 scene_service：cam_y>3 俯视 / <0.3 仰视 / 其余平视；
 * 距离（xz 平面，相机→target）：<1.5 85mm / <3 50mm / <6 35mm / <10 24mm / 其余 16mm。
 * 无相机数据返回 null（调用方跳过 camera_params 合并）。
 */
export function sceneCameraParams(
  camera: SceneMount['camera'] | null | undefined,
): { enabled: true; camera_angle: string; focal_length: string } | null {
  if (!camera || !camera.position || !camera.target) return null
  const camY = camera.position.y
  const cameraAngle = camY > 3.0 ? '俯视' : camY < 0.3 ? '仰视' : '平视'
  const dx = camera.position.x - camera.target.x
  const dz = camera.position.z - camera.target.z
  const distance = Math.sqrt(dx * dx + dz * dz)
  const focal =
    distance < 1.5 ? '85mm' : distance < 3.0 ? '50mm' : distance < 6.0 ? '35mm' : distance < 10.0 ? '24mm' : '16mm'
  return { enabled: true, camera_angle: cameraAngle, focal_length: focal }
}

/** 挂载场景的提交时拼接文本（空挂载返回 ''；后缀自带句首句号时剥掉避免「场景设定：。」） */
export function composeSceneSuffix(mount: SceneMount | null | undefined): string {
  const suffix = (mount?.suffix || '').trim().replace(/^。+/, '').trim()
  return suffix ? `场景设定：${suffix}` : ''
}

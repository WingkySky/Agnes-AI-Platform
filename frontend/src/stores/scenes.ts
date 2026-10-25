/* =====================================================
 * 场景 store：导演台场景的全局挂载状态（对齐预设挂载范式）
 * mountedByContext 按图片/视频上下文隔离，单选互斥、会话内保留；
 * 挂载时调 preview-prompt 缓存 scene→prompt 后缀，提交时由调用方拼接。
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { previewScenePrompt } from '@/api/scenes'
import type { SceneMount } from '@/lib/scene-mount'
import type { Scene3D, SceneData } from '@/types/scene'

export type SceneContext = 'image' | 'video'

export const useScenesStore = defineStore('scenes', () => {
  const mountedByContext = ref<Record<SceneContext, SceneMount | null>>({
    image: null,
    video: null,
  })

  function mountedFor(context: SceneContext): SceneMount | null {
    return mountedByContext.value[context]
  }

  function isMountedIn(context: SceneContext, sceneId: number): boolean {
    return mountedByContext.value[context]?.scene_id === sceneId
  }

  function unmountScene(context: SceneContext): void {
    mountedByContext.value[context] = null
  }

  /** 挂载场景（再点同场景 = 取消，对齐预设 toggle 语义）；suffix 失败时抛错由调用方提示 */
  async function mountScene(scene: Scene3D, context: SceneContext): Promise<boolean> {
    if (isMountedIn(context, scene.id)) {
      unmountScene(context)
      return false
    }
    const res = await previewScenePrompt(scene.scene_data as SceneData)
    const suffix = (res.prompt_suffix || '').trim()
    mountedByContext.value[context] = {
      scene_id: scene.id,
      name: scene.name,
      suffix,
      camera: (scene.scene_data as SceneData)?.camera ?? null,
    }
    return true
  }

  return { mountedByContext, mountedFor, isMountedIn, unmountScene, mountScene }
})

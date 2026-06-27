/* =====================================================
 * useCreditEstimate — 积分预估组合式函数
 * 根据生成任务参数（type/mode/size/seconds/num_frames）
 * 自动调用后端 /api/credits/estimate 接口预估扣费金额
 *
 * 用法：
 *   const { cost, loading, insufficient, refresh } = useCreditEstimate(() => ({
 *     type: 'image',
 *     mode: mode.value,
 *     size: size.value,
 *   }))
 * ===================================================== */

import { ref, watch, onActivated } from 'vue'
import { estimateCost, type CreditEstimateResponse } from '@/api/credits'
import { estimatePipelineCredits } from '@/api/pipeline'

/** 积分预估参数（响应式 getter，便于依赖响应式数据） */
export interface EstimateParamsGetter {
  (): {
    type: 'image' | 'video' | 'pipeline'
    // image/video 用
    mode?: string
    size?: string
    seconds?: number
    num_frames?: number
    // pipeline 用
    templateId?: number
    inputs?: Record<string, unknown>
  }
}

/**
 * 根据响应式参数预估扣费
 * @param paramsGetter 返回当前参数的函数（内部会 watch 其返回值变化）
 */
export function useCreditEstimate(paramsGetter: EstimateParamsGetter) {
  const cost = ref<number | null>(null)        // 预估扣费数量；null 表示尚未加载
  const loading = ref(false)                   // 是否正在请求
  const insufficient = ref(false)              // 当前余额是否不足
  const error = ref<string | null>(null)       // 错误信息

  let reqId = 0                                // 请求序号，避免竞态

  /** 重新拉取预估扣费 */
  async function refresh() {
    const params = paramsGetter()
    if (!params || !params.type) {
      cost.value = null
      return
    }
    const myId = ++reqId
    loading.value = true
    error.value = null
    try {
      let data: CreditEstimateResponse
      if (params.type === 'pipeline') {
        // pipeline 走专用预估接口
        if (!params.templateId) {
          cost.value = null
          return
        }
        const result = await estimatePipelineCredits(params.templateId, params.inputs || {})
        // pipeline 预估返回 { estimated_total, sufficient }，适配为 CreditEstimateResponse 结构
        data = {
          cost: result.estimated_total,
          sufficient: true, // pipeline 预估不返回 sufficient，默认 true，由后端创建时再校验
        } as CreditEstimateResponse
      } else {
        // image/video 走通用预估接口
        data = await estimateCost(params)
      }
      // 避免竞态：仅采用最新一次请求的结果
      if (myId !== reqId) return
      cost.value = data.cost
      insufficient.value = !data.sufficient
    } catch (e) {
      if (myId !== reqId) return
      console.warn('[useCreditEstimate] 请求失败:', e)
      cost.value = null
      error.value = (e as Error)?.message || 'estimate failed'
    } finally {
      if (myId === reqId) loading.value = false
    }
  }

  // 监听参数变化自动刷新（deep 监听返回对象的变化）
  watch(paramsGetter, refresh, { deep: true, immediate: true })

  // keep-alive 组件重新激活时刷新一次预估值
  // 场景：管理员在积分规则页修改了规则，切回图片/视频生成页时
  // 组件不会重新挂载、参数也没变，但规则已更新，需要重新拉取预估
  // 注意：只影响前端预估显示，不碰历史记录和积分流水（那些是生成时写入的，不会变）
  onActivated(() => {
    refresh()
  })

  return { cost, loading, insufficient, error, refresh }
}

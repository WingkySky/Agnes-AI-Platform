/* =====================================================
 * 画布积分预估与校验工具
 * - 用于无限画布中所有生图/生视频环节
 * - 调用后端 /api/credits/estimate 接口预估扣费
 * - 余额不足时弹出明确提示并阻止生成
 *
 * 使用场景：
 *   1. handleNodeGenerateImage / handleHoverGenerateImage（文本→图片）
 *   2. handleConfigGenerate（配置节点 → 图片/视频）
 *   3. handleMaskConfirm（局部编辑）
 *   4. retryGeneration（重试生成）
 *   5. handleHoverDescribe（反推提示词，消耗 AI 对话积分）
 * ===================================================== */

import { ElMessage } from 'element-plus'
import { estimateCost, type CreditEstimateResponse } from '@/api/credits'
import { useUserStore } from '@/stores/user'
import { useI18n } from '@/i18n'

/** 预估参数 */
export interface EstimateParams {
  type: 'image' | 'video'
  mode?: string
  size?: string
  seconds?: number
  num_frames?: number
}

/**
 * 预估本次生成任务的积分消耗
 * - 返回 { cost, sufficient, balance } 或 null（请求失败时）
 * - 失败时弹提示但不阻塞流程（让生成接口自己抛 402）
 */
export async function estimateCanvasCost(params: EstimateParams): Promise<CreditEstimateResponse | null> {
  try {
    return await estimateCost(params)
  } catch (e) {
    console.warn('[canvas] estimate cost failed:', e)
    return null
  }
}

/**
 * 校验积分是否足够，不足时弹提示并返回 false
 * - 用于生成前的预检，避免直接调生成接口被 402 拒绝
 * - 预估失败时不阻塞（返回 true，让生成接口自己处理）
 *
 * @param params 预估参数
 * @returns true=可以继续生成，false=积分不足应中止
 */
export async function checkCreditsBeforeGenerate(params: EstimateParams): Promise<boolean> {
  const { t } = useI18n()
  const userStore = useUserStore()

  // 未登录用户不校验（后端会拒绝）
  if (!userStore.user) return true

  const estimate = await estimateCanvasCost(params)
  if (!estimate) {
    // 预估失败，不阻塞，让生成接口自己处理
    return true
  }

  if (!estimate.sufficient) {
    ElMessage.error(
      t('canvas.messages.insufficient')
        .replace('{balance}', String(estimate.balance))
        .replace('{cost}', String(estimate.cost))
    )
    return false
  }

  return true
}

/**
 * 生成成功后提示消耗的积分
 * - 在 ElMessage.success 中附带消耗数量
 * - 预估失败时不显示数量（避免误导）
 */
export function showCostConsumedMessage(params: EstimateParams, successMessage: string): void {
  const { t } = useI18n()
  // 异步预估，不阻塞成功提示
  estimateCanvasCost(params).then((estimate) => {
    if (estimate && estimate.cost > 0) {
      ElMessage.success(`${successMessage}（${t('canvas.messages.costConsumed').replace('{n}', String(estimate.cost))}）`)
    } else {
      ElMessage.success(successMessage)
    }
  })
}

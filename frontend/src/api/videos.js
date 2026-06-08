/* =====================================================
 * 视频生成相关 API 封装
 * ===================================================== */

import client from './client'

/**
 * 创建视频生成任务
 * @param {Object} params
 * @param {string} params.prompt
 * @param {string} [params.negative_prompt]
 * @param {string} [params.model]
 * @param {number} [params.num_frames]
 * @param {number} [params.frame_rate]
 * @param {number} [params.width]
 * @param {number} [params.height]
 * @param {string} [params.mode]        - text2video / image2video / keyframes
 * @param {string} [params.image]       - image2video 模式下的参考图（URL 或 base64）
 * @param {string[]} [params.images]    - keyframes 模式下的多张图片
 * @param {number} [params.seed]
 */
export function createVideoTask(params) {
  return client.post('/api/videos', params)
}

/**
 * 查询视频任务状态（轮询用）
 * @param {string} taskId
 */
export function getVideoStatus(taskId) {
  return client.get(`/api/videos/${taskId}`, { silent: true }) // 轮询失败不弹错误提示
}

/**
 * 中止视频任务
 * @param {string} taskId
 */
export function cancelVideoTask(taskId) {
  return client.delete(`/api/videos/${taskId}`)
}

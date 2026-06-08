/* =====================================================
 * 图片生成相关 API 封装
 * ===================================================== */

import client from './client'

/**
 * 生成图片
 * @param {Object} params
 * @param {string} params.prompt        - 提示词
 * @param {string} params.model         - 模型名
 * @param {string} params.size          - 尺寸，如 1024x1024
 * @param {string} params.response_format - url / b64_json
 * @param {string} [params.base64_image]- 图生图时的参考图（base64，不带前缀）
 */
export function createImage(params) {
  return client.post('/api/images/generations', params)
}

/**
 * 获取单张图片生成记录
 * @param {number} id
 */
export function getImageRecord(id) {
  return client.get(`/api/images/${id}`)
}

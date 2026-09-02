/* =====================================================
 * 媒体任务状态判定（图片/视频任务的 raw status 成功/失败判断）
 * - taskQueue 轮询、chat 媒体轮询、画布任务轮询共用一套判定
 * ===================================================== */

/** 后端返回的成功状态值 */
const MEDIA_SUCCESS_STATUSES = ['success', 'completed', 'done', 'succeeded', 'finished']

/** 后端返回的失败状态值 */
const MEDIA_FAILED_STATUSES = ['failed', 'error', 'timeout']

/** 判断媒体任务 raw status 是否为成功（大小写不敏感） */
export function isMediaSuccess(status: string): boolean {
  return MEDIA_SUCCESS_STATUSES.includes(status.toLowerCase())
}

/** 判断媒体任务 raw status 是否为失败（大小写不敏感） */
export function isMediaFailed(status: string): boolean {
  return MEDIA_FAILED_STATUSES.includes(status.toLowerCase())
}

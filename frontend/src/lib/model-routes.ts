/* =====================================================
 * 模型备用路由编辑纯函数（多渠道路由 failover）
 * SettingsView 路由区的增删/排序/保存载荷构造；无副作用便于测试
 * ===================================================== */

export interface EditableModelRoute {
  provider_id: number
  model_id: string
  is_enabled: boolean
}

/** 移动路由条目（delta=±1）；越界返回原数组 */
export function moveModelRoute(
  routes: EditableModelRoute[],
  from: number,
  delta: number,
): EditableModelRoute[] {
  const target = from + delta
  if (from < 0 || from >= routes.length || target < 0 || target >= routes.length) return routes
  const next = [...routes]
  const [row] = next.splice(from, 1)
  next.splice(target, 0, row)
  return next
}

/** 追加备用路由；(provider, model) 去重——重复时返回原数组并标记 duplicate */
export function appendModelRoute(
  routes: EditableModelRoute[],
  providerId: number,
  modelId: string,
): { routes: EditableModelRoute[]; duplicate: boolean } {
  const id = modelId.trim()
  if (!providerId || !id) return { routes, duplicate: false }
  if (routes.some((r) => r.provider_id === providerId && r.model_id === id)) {
    return { routes, duplicate: true }
  }
  return {
    routes: [...routes, { provider_id: providerId, model_id: id, is_enabled: true }],
    duplicate: false,
  }
}

/** 保存载荷：列表顺序即 priority（越小越优先） */
export function buildRouteSavePayload(routes: EditableModelRoute[]): {
  routes: Array<{ provider_id: number; model_id: string; priority: number; is_enabled: boolean }>
} {
  return {
    routes: routes.map((r, i) => ({
      provider_id: r.provider_id,
      model_id: r.model_id,
      priority: i,
      is_enabled: r.is_enabled,
    })),
  }
}

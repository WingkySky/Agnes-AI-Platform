/**
 * 画布流程分析工具
 * - 分析节点连线，自动识别执行顺序（拓扑排序）
 * - 自动分组为步骤
 */

import { CanvasPanel, CanvasConnection, CanvasStep } from '@/stores/canvas'

/**
 * 分析画布节点和连线，自动识别流程
 * - 返回步骤列表（已按执行顺序排序）
 * - 每个拓扑层级作为一个步骤（更细粒度的分组）
 */
export function analyzeFlow(
  panels: CanvasPanel[],
  connections: CanvasConnection[]
): CanvasStep[] {
  if (panels.length === 0) return []

  // 1. 计算拓扑深度（从源节点到该节点的最长路径）
  const depth = new Map<string, number>()
  const adjacency = new Map<string, string[]>()
  const inDegree = new Map<string, number>()

  for (const panel of panels) {
    adjacency.set(panel.id, [])
    inDegree.set(panel.id, 0)
    depth.set(panel.id, 0)
  }

  for (const conn of connections) {
    if (!adjacency.has(conn.source_panel_id)) continue
    if (!adjacency.has(conn.target_panel_id)) continue

    adjacency.get(conn.source_panel_id)!.push(conn.target_panel_id)
    inDegree.set(conn.target_panel_id, (inDegree.get(conn.target_panel_id) || 0) + 1)
  }

  // 2. 拓扑排序，计算深度
  const queue: string[] = []
  const order: string[] = []

  for (const [panelId, degree] of inDegree) {
    if (degree === 0) {
      queue.push(panelId)
      depth.set(panelId, 0)
    }
  }

  while (queue.length > 0) {
    const currentId = queue.shift()!
    order.push(currentId)

    const neighbors = adjacency.get(currentId) || []
    for (const neighborId of neighbors) {
      const newDegree = (inDegree.get(neighborId) || 0) - 1
      inDegree.set(neighborId, newDegree)

      // 更新深度
      const newDepth = (depth.get(currentId) || 0) + 1
      if ((depth.get(neighborId) || 0) < newDepth) {
        depth.set(neighborId, newDepth)
      }

      if (newDegree === 0) {
        queue.push(neighborId)
      }
    }
  }

  // 3. 按深度分组（每个深度层级 = 一个步骤）
  const depthGroups = new Map<number, string[]>()
  for (const panel of panels) {
    const d = depth.get(panel.id) || 0
    if (!depthGroups.has(d)) {
      depthGroups.set(d, [])
    }
    depthGroups.get(d)!.push(panel.id)
  }

  // 4. 生成步骤
  const steps: CanvasStep[] = []
  const sortedDepths = Array.from(depthGroups.keys()).sort((a, b) => a - b)

  for (const d of sortedDepths) {
    const panelIds = depthGroups.get(d)!
    const stepNames = ['提示词', '生图', '生视频', '合成', '输出']
    const stepName = d < stepNames.length ? stepNames[d] : `步骤 ${d + 1}`

    steps.push({
      id: `step_${Date.now()}_${d}`,
      name: stepName,
      panel_ids: panelIds,
      order: d,
      depends_on: d > 0 ? [`step_${Date.now()}_${d - 1}`] : [],
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
  }

  return steps
}

/**
 * 分析执行顺序（拓扑排序）
 * - 返回按执行顺序排列的节点 ID 列表
 */
export function analyzeExecutionOrder(
  panels: CanvasPanel[],
  connections: CanvasConnection[]
): string[] {
  // 1. 构建邻接表和入度表
  const adjacency = new Map<string, string[]>()
  const inDegree = new Map<string, number>()

  for (const panel of panels) {
    adjacency.set(panel.id, [])
    inDegree.set(panel.id, 0)
  }

  for (const conn of connections) {
    if (!adjacency.has(conn.source_panel_id)) continue
    if (!adjacency.has(conn.target_panel_id)) continue

    adjacency.get(conn.source_panel_id)!.push(conn.target_panel_id)
    inDegree.set(conn.target_panel_id, (inDegree.get(conn.target_panel_id) || 0) + 1)
  }

  // 2. 拓扑排序（Kahn's algorithm）
  const queue: string[] = []
  const order: string[] = []

  // 找到所有入度为 0 的节点（起点）
  for (const [panelId, degree] of inDegree) {
    if (degree === 0) {
      queue.push(panelId)
    }
  }

  while (queue.length > 0) {
    const currentId = queue.shift()!
    order.push(currentId)

    const neighbors = adjacency.get(currentId) || []
    for (const neighborId of neighbors) {
      const newDegree = (inDegree.get(neighborId) || 0) - 1
      inDegree.set(neighborId, newDegree)

      if (newDegree === 0) {
        queue.push(neighborId)
      }
    }
  }

  // 3. 如果有环，警告（部分节点未访问）
  if (order.length < panels.length) {
    console.warn('[Flow Analysis] 检测到环路，部分节点可能无法执行')
  }

  return order
}

/**
 * 检查流程是否有环
 */
export function hasCycle(
  panels: CanvasPanel[],
  connections: CanvasConnection[]
): boolean {
  const order = analyzeExecutionOrder(panels, connections)
  return order.length < panels.length
}

/**
 * 根据步骤分组，计算分组框的边界
 */
export function calculateStepBounds(
  step: CanvasStep,
  panels: CanvasPanel[]
): { left: number; top: number; width: number; height: number } | null {
  const panelIds = step.panel_ids
  const stepPanels = panels.filter(p => panelIds.includes(p.id))

  if (stepPanels.length === 0) return null

  // 计算边界
  const minX = Math.min(...stepPanels.map(p => p.x))
  const minY = Math.min(...stepPanels.map(p => p.y))
  const maxX = Math.max(...stepPanels.map(p => p.x + p.width))
  const maxY = Math.max(...stepPanels.map(p => p.y + p.height))

  return {
    left: minX - 20,
    top: minY - 40,
    width: maxX - minX + 40,
    height: maxY - minY + 60,
  }
}

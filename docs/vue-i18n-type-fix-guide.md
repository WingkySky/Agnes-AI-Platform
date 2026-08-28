# Vue / TypeScript i18n 与类型断言修复指南（无限画布实践）

> 作者：WorkBuddy Agnes | 适用项目：agnes-platform frontend（Vue 3 + Vite + vue-tsc + Pinia）

## 背景

项目中的无限画布模块（`frontend/src/views/CanvasView.vue` + 子组件）暴露两类问题：
1. **i18n raw key 显示**：`t('canvas.xxx.yyy')` 因 pack 缺 key，直接渲染成字符串如 `canvas.messages.downloadFailed`。
2. **vue-tsc 类型错误**（35 处）：使用 `as ImageTaskPollStatus` / `as Record<string, unknown>` 等断言绕过了类型检查，根因是接口未被正确导出/import 或未声明参数类型。

修复原则：**不用断言掩盖类型不匹配，改用正确声明**。

---

## 一、i18n 缺失 key 的诊断流程

### 1.1 理解 `t()` 行为

查看 `src/i18n/index.ts`：

```ts
function t(key: string, ...args: unknown[]): string {
  const value = lookup(pack, key)
  return value != null ? interpolate(value, ...args) : key  // ⚠️ 未命中时返回 raw key
}
```

结论：**缺少 key 不会报错，而是原样输出 key 字符串**，这是"看到 raw key"的根因。

### 1.2 扫描所有被引用的 canvas key

在 `frontend/` 目录运行：

```bash
# 提取所有模板字符串/引号包裹的 canvas.* 字面量
grep -rhoE "['\`](canvas\.[A-Za-z0-9_.]+)['\`]" src/ | sort -u
```

注意排除动态拼接 `${...}` 或末尾带 `.` 的碎片键。

### 1.3 验证 vs pack 是否一致

用 Node.js 脚本加载真实 pack（而非读 `.ts` 文件）：

```js
import fs from 'fs'
// pack 通常是 export default { ... }，替换后 eval
let s = fs.readFileSync('src/i18n/zh-CN.ts', 'utf8')
s = s.replace(/export\s+default/, 'return')
const pack = new Function(s)()

function lookup(obj, path) {
  let cur = obj
  for (const k of path.split('.')) {
    if (cur == null) return undefined
    cur = cur[k]
  }
  return cur
}

const used = new Set([...]) // 1.2 的结果
const missing = [...used].filter(k => lookup(pack, k) === undefined)
console.log(missing)
```

**关键坑点**：
- pack 层级可能和直觉不同。例如本例中 `presetItems` 是 `canvas.presetItems`，而不是 `canvas.templates.presetItems`。
- 先 `grep -n presetItems src/i18n/*.ts` 确认是否真的存在；如果文件里存在但 loader 解析不到，说明层级拼写有误（比如多了一层 `.templates.`）。

### 1.4 补全 pack

按实际层级插入 key。示例（`zh-CN.ts`）：

```ts
canvas: {
  // ...
  nodeNames: {
    text: '文本节点',
    // ... 补全缺失的
    prompt: '提示词',
    blendConfig: '混合配置',
    reversePrompt: '反推提示词',
    // ...
  },
  presetItems: {
    text2image: { name: '文生图', desc: '...' },
    image2image: { name: '图生图', desc: '...' },
    // ...
  },
  // ...
}
```

**en-US.ts 同步补全**，保持 key 结构一致（值可以是空字符串兜底，但不能缺 key）。

### 1.5 验证

重新跑 1.3 脚本 → 输出 `[]`。

---

## 二、类型断言修复（无 `as` 方案）

### 2.1 定位根因

`vue-tsc -b --noEmit --force` 报错时，先看错误类型：

| 错误消息 | 常见根因 |
|---------|---------|
| `Cannot find name 'Foo'` | 接口/类型未 import 或未导出 |
| `Type '{}' is not assignable to 'string'` | prop 未声明类型，TS 推断为 `object` |
| `Property 'trim' does not exist on type '{}'` | 同上，`content` 字段为 `unknown` |
| `Argument of type 'number | undefined' is not assignable to 'number'` | 值可能为 undefined，需要 guard |
| `Conversion to 'EventListener' may be a mistake` | 函数签名不匹配，需加 `Event` 类型 |

### 2.2 分类修复策略

#### A. 接口不在 `<script setup>` 作用域内

**坏**：在 `</template>` 后裸写 `interface Foo { ... }`
**好**：移入 `<script setup lang="ts">` 顶部

```ts
<script setup lang="ts">
interface ImageTaskPollStatus {
  status: string
  result_url?: string | null
  // ...
}
// ...
</script>
```

#### B. 类型未 import

**坏**：`fn(configNode.id, store as CanvasGenerationStore)`
**好**：在被调用的模块 `export interface CanvasGenerationStore`，然后 import：

```ts
// lib/canvas-generation.ts
export interface CanvasGenerationStore {
  panels: GenerationPanel[]
  addPanel(panel: Record<string, any>): string | undefined
  // ...
}

// CanvasView.vue
import { type CanvasGenerationStore } from '@/lib/canvas-generation'
// 之后直接传 store，不用断言
fn(configNode.id, store, ...)
```

#### C. prop 类型太弱（推断为 `object`）

**坏**：`panel: { type: Object, required: true }` → TS 推断为 `{}`
**好**：

```ts
import { type PropType } from 'vue'
import { type CanvasPanel } from '@/stores/canvas'

const props = defineProps({
  panel: { type: Object as PropType<CanvasPanel>, required: true },
})
```

然后在模板中使用辅助函数读取 `Record<string, unknown>` 字段：

```ts
function nodeStr(value: unknown): string {
  return typeof value === 'string' ? value : ''
}
function nodeNum(value: unknown, fallback: number): number {
  return typeof value === 'number' ? value : fallback
}
function nodeBool(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}
```

模板里用：

```html
:value="nodeStr(panel.content.prompt) || ''"
:model-value="nodeBool(panel.content.with_subtitle, true)"
```

**注意**：不要为了"只修一处"就把整个 `panel` 强类型化——如果组件其他逻辑依赖宽松的 panel 类型，改为仅对出问题的那几处加辅助函数，避免引入新的 cascading errors。

#### D. 值可能为 `undefined` 但 API 要求非空

**坏**：
```ts
const sessionId = (session as { id?: number }).id  // number | undefined
deleteChatSession(sessionId)  // 期望 number
```

**好**：
```ts
const session = await createChatSession({ title: '反推' })
const sessionId = session.id  // ChatSession.id 是 number
// 如果不确定，加 guard
if (!sessionId) throw new Error('session id required')
deleteChatSession(sessionId)
```

#### E. Event listener 断言

**坏**：
```ts
window.addEventListener('event-name', handler as EventListener)
```

**好**：让函数签名匹配 `EventListener`（参数为 `Event`），再在函数内收窄：

```ts
function handleUserSwitch(e: Event) {
  const detail = e instanceof CustomEvent ? e.detail : undefined
  const userId = typeof detail?.id === 'number' ? detail.id : null
  // ...
}

window.addEventListener('agnes:user-login', handleUserSwitch)
```

#### F. API 返回类型不够

**坏**：`const status: any = await api.func(); (status as ExtraFields).url`

**好**：
1. 先在 `src/types/index.ts` 定义完整响应类型
2. 更新 API 函数返回该类型
3. 调用方直接用，无需断言

---

## 三、验证清单

每次修完类型问题后，依次执行：

```bash
# 1. 类型检查（必须 0 错误）
cd frontend && ./node_modules/.bin/vue-tsc -b --noEmit --force 2>&1

# 2. 确认断言已消除
grep -n "as ImageTaskPollStatus\|as CanvasGenerationStore\|as Record<string, unknown>" src/ -r

# 3. i18n 完整性检查（用 1.3 脚本）
node verify2.mjs

# 4. 手动冒烟（可选，需 LLM 环境）
# 打开画布 → 创建节点 → 生成任务 → 确认文案正常显示
```

---

## 四、本项目已修复的问题总结

| 位置 | 问题 | 修法 |
|------|------|------|
| `CanvasView.vue` | `ImageTaskPollStatus`/`VideoTaskPollStatus` 接口裸写在 `</template>` 后 | 移入 `<script setup>` |
| `CanvasView.vue` | `store as CanvasGenerationStore` | 在 `canvas-generation.ts` 加 `export`，CanvasView 直接 import |
| `CanvasView.vue` | `(status as ImageTaskPollStatus).url` 重复多次 | `const status: ImageTaskPollStatus = await ...` |
| `CanvasView.vue` | `createImageTask({...} as ImageGenerationRequest)` | 在 `types/index.ts` 已有 `ImageGenerationRequest`，直接去掉 `as` |
| `CanvasView.vue` | `sessionId` 推导为 `number | undefined` | `const session = await createChatSession(...); const sessionId = session.id` |
| `CanvasView.vue` | `handleUserSwitch as EventListener` | 改为 `handleUserSwitch(e: Event)` + `instanceof CustomEvent` 收窄 |
| `CanvasNode.vue` | `:value="(panel.content as Record<...>).prompt"` | 新增 `nodeStr/nodeNum/nodeBool` 辅助函数 |
| `GenerationQuickPanel.vue` | `sourcePanel: { type: Object, default: null }` 推断为 `object` | 改为 `PropType<CanvasPanel | null>` |
| `zh-CN.ts` / `en-US.ts` | 缺 23 个 `canvas.nodeNames.*` 和 `canvas.presetItems.*` key | 按实际层级补齐 |
| `canvas-templates.ts` | 误写 `canvas.templates.presetItems.*` | 改为 `canvas.presetItems.*` |

---

## 五、注意事项

1. **不要为了"让类型检查通过"而大量加 `as`**：断言掩盖了真实的类型不匹配，长期会累积隐患。
2. **优先在源头声明正确类型**：interface 的 `export`、API 的返回类型、prop 的 `PropType`，都比在调用处断言更干净。
3. **i18n key 路径要和 pack 结构对齐**：先 `grep` 确认 pack 里的实际层级，再对照代码引用的 key。
4. **修复后必须跑 `vue-tsc --force`**：不强制会因缓存导致部分错误被跳过。

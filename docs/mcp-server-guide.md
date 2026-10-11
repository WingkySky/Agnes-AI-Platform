# 平台 MCP Server 接入指南（外部 Agent / CLI）

平台通过 MCP（Model Context Protocol）streamable HTTP 对外暴露工具面，外部 Agent（zcode、Claude Code 等任意 MCP client）可以在**浏览器不打开**的情况下操作你的画布、剪辑器和生成任务，完成端到端创作闭环。

## 1. 创建访问令牌（PAT）

1. 登录平台 → 侧边栏「MCP 接入」→ 「API 访问令牌」卡片 → 新建令牌。
2. 选择权限档位：
   - **只读（readonly）**：只能调用查询类工具（清单 / 画布概览 / 任务状态）。
   - **完全（full）**：可执行全部工具（含写操作）。危险确认由外部 Agent 自己的交互层负责（例如 CLI 的权限系统），平台侧不再弹确认。
3. 创建成功后**明文只显示一次**，立即复制保存（`agn_pat_` 开头）。令牌可随时吊销，吊销即时生效。

## 2. 接入方式（三选一）

「MCP 接入」页的「API 访问令牌」卡片的「接入指引」弹窗会按当前环境自动生成以下内容并可一键复制；若手上没有可用明文（令牌只在创建时展示一次），弹窗内可直接「创建令牌并填入」，创建后三种方式的复制内容都会自动嵌入真实令牌——复制出来即可直接使用，无需手工替换。

### 方式 A：发给 Agent 自主添加（最省事）

把下面整段复制发给你的 Agent（对话里粘贴发送），它会自行完成添加与验证：

```
请把以下 MCP 服务器添加到你的配置中（streamable HTTP），添加后重载并调用 tools/list 列出工具确认接入成功：
- 名称：agnes-platform
- URL：http://<你的平台地址>/mcp
- 请求头：Authorization: Bearer agn_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 方式 B：命令行一键添加

在终端执行（Claude Code / ZCode 等 CLI；`--scope user` 写入用户级配置，所有项目可用）：

```bash
claude mcp add --transport http --scope user agnes-platform http://<你的平台地址>/mcp --header "Authorization: Bearer agn_pat_xxx"
```

### 方式 C：手工配置 MCP client

```json
{
  "mcpServers": {
    "agnes-platform": {
      "type": "http",
      "url": "http://<你的平台地址>/mcp",
      "headers": {
        "Authorization": "Bearer agn_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

- URL 指向后端地址（本地开发 `http://localhost:8000/mcp`，部署环境用实际域名）。
- 重启 / 重载 client 后应能看到 16 个工具（前缀多为 `canvas_*` / `editor_*`）。

## 3. 工具清单（16）

| 分组 | 工具 | 写类 | 说明 |
|---|---|---|---|
| 画布 | `canvas_list` | | 用户画布清单（uid/名称/更新时间） |
| 画布 | `canvas_create` | ✅ | 新建画布工作区 |
| 画布 | `canvas_get_overview` | | 画布概要：节点 + 连线（大画布游标分页续读） |
| 画布 | `canvas_apply_ops` | ✅ | 批量落节点（add_panel）/ 连线（add_connection），支持按名引用 |
| 编辑器 | `editor_list_projects` | | 剪辑工程清单 |
| 编辑器 | `editor_create_project` | ✅ | 新建剪辑工程 |
| 编辑器 | `editor_get_document` | | 读时间线文档 JSON + revision |
| 编辑器 | `editor_put_document` | ✅ | 保存时间线（revision 乐观锁，冲突需重读） |
| 编辑器 | `editor_render_submit` | ✅ | 提交渲染成片（幂等键防重复提交） |
| 编辑器 | `editor_render_status` | | 渲染状态 / 进度 / 成片 URL |
| 编辑器 | `editor_rough_cut_analyze` | | AI 粗剪：静音剔除 / 场景切分 → segments |
| 素材 | `asset_list` | | 素材库清单（图片/视频/音频，含 URL） |
| 生成 | `model_list` | | 可用模型（image / video / chat） |
| 生成 | `image_generate` | ✅ | 创建图片任务（扣积分）→ task_id |
| 生成 | `video_generate` | ✅ | 创建视频任务（扣积分）→ task_id |
| 生成 | `generation_get` | | 批量查任务状态（result_url / 错误类目） |

## 4. 典型闭环示例

对 Agent 用自然语言下达，例如：

> 「在我的平台上新建一个画布，把这段分镜落成节点：①开场文本『雨夜码头』②一张氛围图，两者连线；然后生成一张 1024x1024 的雨夜码头概念图，完成后告诉我结果地址。」

Agent 的典型工具序列：

```
canvas_create → canvas_apply_ops（add_panel ×2 + add_connection）
→ image_generate（prompt + size）→ generation_get（轮询到 result_url）
→ canvas_apply_ops（把结果 URL 落成 image 节点）
```

剪辑闭环：

```
asset_list（找素材）→ editor_rough_cut_analyze（静音剔除拿 segments）
→ editor_create_project → editor_get_document → editor_put_document（按 segments 排片段）
→ editor_render_submit → editor_render_status（轮询到 video_url）
```

## 5. 行为与限制

- **纯服务端执行**：所有工具在平台后端直接执行，页面在线与否无关；分镜规划、prompt 撰写等「脑力活」由外部 Agent 自身完成，平台只提供「手脚」。
- **积分**：`image_generate` / `video_generate` 走与页面生成完全相同的扣积分链路（余额不足报错）。
- **乐观锁**：`editor_put_document` 冲突（409 语义）时需重新 `editor_get_document` 再改再存。
- **边界（v1 不做）**：素材上传、works/entities 管理、媒体结果自动落画布（用 `canvas_apply_ops` 自己落）、MCP resources/prompts。

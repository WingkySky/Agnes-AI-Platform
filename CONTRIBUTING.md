# 贡献指南

感谢关注 Agnes AI Platform！欢迎按自己顺手的方式参与，门槛从低到高有三条路径：

1. **提反馈** — 报 Bug、聊使用体验，见下方「提 Bug」
2. **改文档** — README / docs / API.md 的错漏与补充，直接按「提交 PR」流程提即可
3. **改代码** — Bug 修复、新功能，见「代码规范」与「提交 PR」

## 提 Bug

[用模板提交 Bug 反馈](https://github.com/WingkySky/Agnes-AI-Platform/issues/new?template=bug_report.yml)，表单会引导填写：

- 环境方式（Docker / 便携包 / 源码启动）
- 版本号（设置页「关于」，或仓库根目录 `VERSION` 文件）
- 复现步骤、期望行为与实际行为
- 相关日志（`backend/logs/`，或浏览器控制台报错）

## 功能建议

请先到 [Discussions - Ideas](https://github.com/WingkySky/Agnes-AI-Platform/discussions/categories/ideas) 发起讨论，方向聊清楚、确认作者认可后再落地为 issue 开发——避免闷头做了一个项目并不需要的东西。

## 开发环境

按 [README - 3. 手动启动](README.md#3-手动启动)从源码启动后端与前端，然后运行测试：

```bash
cd backend && python -m pytest    # 后端测试
cd frontend && npm run test       # 前端测试（vitest）
```

## 代码规范

**人类贡献者与 AI 助手共用同一套规范：[AGENTS.md](AGENTS.md)**——前后端分层、异步一致性、i18n、保持代码精简等约束都写在里面，动手前请通读一遍。

本项目本身就是用 AI 协作开发的，因此**明确欢迎 AI 辅助贡献**：把 AGENTS.md 全文作为规范提供给你的 AI 助手（ZCode、Claude Code 等），让它按规范改代码，你负责核对结果与提交，这是门槛最低的贡献方式。

## 提交 PR

- 一个 PR 只聚焦一件事，不做无关重构
- commit message 对齐仓库现状：`feat：` / `fix：` / `refactor：` / `ci：` / `chore：` + 中文描述（全角冒号）
- 提交前跑通测试：后端 pytest、前端 vitest 全绿
- 涉及接口或数据表改动时，同步更新 `API.md` 与相关文档；涉及用户可见功能时在 `CHANGELOG.md` 的 Unreleased 段补一条记录
- 提 PR 时按模板 checklist 逐项自查

## 许可证

本项目采用 Apache License 2.0 with Commons Clause（**禁止商用**）。你提交的代码将以同一许可证发布，提交 PR 即表示你同意这一点；个人、教育、研究用途不受影响。

## 待改进方向

以下方向欢迎认领（只列方向、不承诺时间表，动手前请先在 issue 或 Discussions 打个招呼）：

- 文档与翻译完善（README、docs/、部署教程）
- 测试覆盖补充（后端 services、前端 stores 与组件）
- 更多 AI Provider 的适配与实测反馈
- i18n 文案补全
- 各平台部署与运维教程

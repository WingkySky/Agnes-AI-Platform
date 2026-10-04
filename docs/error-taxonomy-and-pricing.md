# 生成可靠性：错误类目 + 调用记账 + 模型倍率定价

> 本批三项：生成错误归类（13 类合同 + 重试闸门）、上游调用记账（api_call_logs + 管理页）、模型倍率动态定价。接口细节见 `API.md` 第 19 章，设计决策见 `.zcode/plans/` 下设计文档（gitignored）。

## 一、生成错误类目

**解决什么问题**：上游失败此前只有一句中文文案（存在 Generation 表都没有的错误字段），用户不知道能不能重试，管理端看不到失败分布。现在每次失败都有类目 + 原因原文，且「重试是否安全」由类目语义决定。

**核心语义（防重复扣费）**：
- 上游明确判死的失败 → 按原因归类（审核拒绝/参数错误/额度不足…），重试安全性由类目表决定；
- **结果未知**的失败（视频提交回执丢失、查询阶段 5xx/超时、轮询超时）→ 一律 `submission_uncertain`，**禁止原地重试**——原任务可能仍在途，重试就是双倍扣费。提示用户稍后在任务历史确认。

**链路**：`UpstreamError` 结构化异常（状态码/响应体摘要/request_id）→ `error_taxonomy.classify` 归类 → Generation 表落库（error_category/error_message）→ 状态端点/历史透出 → 前端 i18n 文案 + 重试闸门（models store `canRetryCategory`）。

**为什么文案在前端 i18n**：类目是语义（code + can_retry），随 `/api/config` 下发；具体措辞双语可改，不锁死在后端。

## 二、上游调用记账

- 每次上游调用一行日志：渠道、模型、类型、耗时、成败、错误类目、request_id、（chat 类的）token 用量。写入在客户端出口 best-effort 完成，故障不影响生成。
- 管理端 `/admin/logs` 第三 Tab「上游调用」：今日/近 7 天调用量、失败率、按类目分布、按渠道分布 + 明细列表筛选。
- 与积分流水的关系：api_call_logs 看「上游发生了什么」，credit_transactions 看「用户被扣了什么」——对账链在 `estimated_credits` 逐步补齐后打通。

## 三、模型倍率定价

- **实扣 = credit_rules 基准价 × 该模型 cost_multiplier**（倍率默认 1.0，下限 0.1）。
- 为什么不是按 token：图片/视频上游 API 不返回 token 用量，真实成本只能来自管理员配置的模型成本参数；倍率制保留 credit_rules 基准体系（全局调价仍是一处改），每模型只管差异系数。
- 管理端「配置管理 → 模型编辑 → 积分倍率」保存立即生效；预估（estimate 接口）与实扣同函数自动一致；先扣后退不动，失败退实扣原额。

## 测试

- 后端：`tests/test_error_taxonomy.py`（14 例表驱动：状态码/关键词/回执语义/闸门）、`tests/test_admin_api_calls.py`（401/403/200 + 聚合结构）、`tests/test_cost_multiplier.py`（5 例：倍率放大/下限/未知模型/旧签名兼容）。
- 前端：`lib/__tests__/error-taxonomy-frontend.spec.ts`（闸门语义 + 批量表行状态带类目）。

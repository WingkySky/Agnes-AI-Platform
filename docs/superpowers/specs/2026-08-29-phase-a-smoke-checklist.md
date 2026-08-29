# Phase A 生成配置下放 — 冒烟清单

> 对应设计：`2026-08-29-generation-config-downshift-design.md`
> 覆盖范围：M1 默认值链 / M2 Composer 底栏统一 / M3 剧本链路
> 自动化校验已通过：`vue-tsc -b --noEmit` 无错、`vite build` 成功、`py_compile` 通过
> 本清单为手工验证项，逐条执行并勾选

---

## 0. 校验命令（先跑一遍）

```bash
cd frontend
npm run type-check      # vue-tsc -b --noEmit，应无输出、退出码 0
npx vite build --outDir /tmp/agnes-verify   # 应 built 成功

cd ../backend
python -m py_compile app/schemas/storyboard.py app/services/storyboard_service.py
```

> 说明：`npm run build` 在受限环境下会失败于 vite 清空 `dist/assets`（触发批量删除保护，阈值 50 个文件），
> 不是代码问题。改用上面的 `--outDir /tmp/...` 绕开即可。

---

## 1. M1 默认值链

| # | 步骤 | 预期 |
| --- | --- | --- |
| 1.1 | 偏好设置页把「默认生图模型」改为非列表第一个的模型，保存后刷新页面 | 偏好值保留 |
| 1.2 | 新建 image 节点，打开悬浮 Composer，不做任何选择直接发送 | 底栏模型标签显示偏好模型；生成产物的模型 = 偏好值 |
| 1.3 | 把偏好里的默认模型改回空/默认 | image / video 节点底栏回落到列表第一个，无空白标签 |

## 2. M2 image 节点 Composer 底栏

| # | 步骤 | 预期 |
| --- | --- | --- |
| 2.1 | image 节点 Composer 底栏选一个非默认模型 + 非默认尺寸，发送 | 产物按所选模型与尺寸生成 |
| 2.2 | 关闭 Composer，重新打开同一节点 | 上次选择的模型与尺寸仍在（已持久化到节点 content） |
| 2.3 | 底栏选一个「模型名很长」的模型 | 标签超长时省略号截断，不撑破 Composer 宽度 |

## 3. M2 video 节点 Composer 底栏

| # | 步骤 | 预期 |
| --- | --- | --- |
| 3.1 | video 节点底栏依次改模型 / 分辨率 / 比例 / 帧率 / 时长，发送 | 产物按全部所选参数生成 |
| 3.2 | 先把时长选到最大值，再把帧率切到更高档（该档时长上限更低） | 时长自动下调到允许的最大值，并写回 content（帧率联动未回归） |
| 3.3 | 重开节点 | 五项选择全部保留 |

## 4. M2 config 节点（替换原生 select 后的回归）

| # | 步骤 | 预期 |
| --- | --- | --- |
| 4.1 | config 节点切换「生图 / 生视频」模式 | 底栏参数项随模式切换（图片：模型+尺寸；视频：模型+分辨率+比例+帧率+时长） |
| 4.2 | 改参数后执行生成 | 与改造前行为一致（`executeMerge*` 读取字段未变） |
| 4.3 | 生成失败后重试 | 沿用节点上已保存的参数重试 |
| 4.4 | 关键帧开关 | 仍在（ParamSelector 无此概念，故保留原控件） |

## 5. M2 + M3 script 节点分镜聊天模型

| # | 步骤 | 预期 |
| --- | --- | --- |
| 5.1 | script 节点 Composer 底栏选一个 chat 模型，生成分镜 | 请求体带上所选 `model`；后端日志/产物确认使用了该模型 |
| 5.2 | 关闭再打开 script 节点 | 所选 chat 模型保留 |

**后端接口直测**（不传 / 传合法 / 传非法三种）：

```bash
# 不传 model：回退第一个 chat 模型（行为与改动前一致）
curl -X POST http://localhost:8000/api/storyboard -H "Content-Type: application/json" -d '{"text":"..."}'

# 传合法 chat 模型 id：使用该模型
curl -X POST http://localhost:8000/api/storyboard -H "Content-Type: application/json" -d '{"text":"...","model":"<chat-model-id>"}'

# 传非法 model：后端 logger.warning 提示回退，仍正常返回
curl -X POST http://localhost:8000/api/storyboard -H "Content-Type: application/json" -d '{"text":"...","model":"not-exist"}'
```

## 6. M3 向导步骤② 资产参考图

| # | 步骤 | 预期 |
| --- | --- | --- |
| 6.1 | 打开剧本向导步骤②，在资产图参数栏选非默认模型 + 尺寸，生成资产参考图 | 按所选生成（不再是硬编码 1024x1024 与默认模型） |
| 6.2 | 关闭向导，重新打开 | 参数栏选择保留 |

## 7. M3 向导步骤③ 批量派生

| # | 步骤 | 预期 |
| --- | --- | --- |
| 7.1 | 步骤③ 分镜图参数区选模型 + 尺寸 → 批量派生分镜图 | 全部 config 节点按所选生成；积分确认弹窗金额按所选尺寸估算 |
| 7.2 | 步骤③ 分镜视频参数区选模型 + 比例/分辨率/帧率/时长 → 批量派生视频 | 全部按所选（不再硬编码 16:9） |
| 7.3 | 视频参数区**不选时长**，给镜头表格里的镜头设不同时长 → 派生 | 各镜头沿用自己表格里的时长（不破坏逐镜头时长能力） |
| 7.4 | 视频参数区**选定时长** → 派生 | 全部镜头用参数栏时长覆盖 |
| 7.5 | 某镜头派生后，在 Composer 里单改参数再重跑 | 以该节点 content 为准（批量参数仅是派生初值） |
| 7.6 | 右键单镜头「重拍视频」 | 与批量派生同源，参数一致（不会两种路径两套参数） |

## 8. 参数继承（本次引入的行为增强，需确认符合预期）

| # | 步骤 | 预期 |
| --- | --- | --- |
| 8.1 | image 节点设了模型/尺寸后，把它连到下游节点并执行下游生成 | 下游输入的 `model` / `size` 继承上游（`resolveInputs` 已有逻辑，现在上游真的有值了） |

> 这是「节点即配置」的自然结果。若不希望继承，需要另行收敛 `stores/canvas.ts` 的 `resolveInputs` 字段白名单。

## 9. 已知缺口（不在本期范围，登记为 backlog）

| 项 | 说明 |
| --- | --- |
| 首开底栏显示默认值 | image / video 节点首次打开底栏显示的是「默认模型/默认参数」，而非该节点历史生成时实际用的模型（产物元数据未回填到 content） |
| 视频批量积分预估精度 | 预估按统一时长估算，实际按「参数栏时长 / 镜头时长」扣费。参数栏选了时长时一致；未选时沿用改动前行为（既有缺口，本次未劣化） |
| ParamSelector 定位 | `el-popover` 在画布缩放容器内的定位未做专项验证，冒烟时留意弹层位置是否跟随 |
| 存量 `✓` 图标 | 5 个既有文件用 U+2713 作功能图标（`ScriptNodeContent.vue`、`ScriptWizardDialog.vue`、`useNodeMention.ts`、`PresetCenter.vue`、`MediaLibraryPanel.vue`），按 P0-1 正则属 Dingbats 区，建议后续统一替换为 Element Plus `Select` 图标 |

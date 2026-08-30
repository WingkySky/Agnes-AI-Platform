# 模型生成能力统一配置方案（gen_params）

## 目标
把散落在代码里的模型特例（参考图上限、AI 水印、尺寸归一化规则、尺寸选项/默认值）收敛为**数据驱动的按模型配置**：未来新模型「同族自动识别、特例弹窗一配」，不再改生成代码。

## 设计核心

**三层解析链**（`provider_registry.get_model_gen_params(model_id)`）：
1. DB 显式配置（`model_definitions.gen_params` JSON 列，管理员可改）
2. 按名自动画像（注册表内 `_GEN_PARAM_PROFILES`：id 含 `seedream` → 关水印+seedream 尺寸规则；`agnes-image-2.1-flash` → 参考图≤6；命中不了的模型 → 无约束默认）——保证同步来的新模型开箱即用
3. Schema 默认值（无任何特例）

**gen_params 已知键**（Pydantic `ModelGenParams` 定义唯一出处，未来加键只改 schema+规则实现）：
- `max_ref_images`（参考图/参考帧上限）
- `watermark_param_off`（请求携带官方 watermark=false）
- `size_rule`（尺寸归一化规则名，如 "seedream"，算法实现在代码、分配在数据）
- `image_sizes` / `default_size`（覆盖该模型尺寸选项与默认值，供前端选择器）

**范围裁剪**：视频契约族判断（V25 双契约、Flash 固定 720P）保留在代码——那是协议族分支不是逐模型旋钮；video2video 能力已走 capabilities 标签，不动；project 服务默认模型兜底是另一问题，不在本期。

## 实施

### 阶段一：后端机制
1. `model_definitions` 加 `gen_params` JSON 列（nullable，main.py 自动迁移已支持 JSON 列，启动即生效）
2. `schemas/common.py`：新增 `ModelGenParams` 模型 + `ModelInfo.gen_params` 字段
3. `provider_registry.py`：`_GEN_PARAM_PROFILES` 自动画像 + `get_model_gen_params()`（含缓存）+ `_build_model_info_from_definition` 透传 gen_params；`add_custom_model`/`update_model` 接收 gen_params
4. 重接三处硬编码（client 内延迟 import 注册表避免循环依赖）：
   - `agnes_client.create_image`：`_IMAGE_REF_LIMITS` 删除，改读 `max_ref_images`
   - `agn_sdk_client.create_image`：`"seedream" in model` 两处判断改读 `watermark_param_off` / `size_rule`（`_normalize_seedream_size` 函数保留为规则实现）
5. `routes/providers.py` + `schemas/providers.py`：模型新增/编辑接口透传 gen_params（经 ModelGenParams 校验）

### 阶段二：前端消费
6. `types/index.ts` ModelInfo 加 `gen_params`；`stores/models.ts` 加 `getModelGenParams(modelId)`
7. `canvas-generation.ts`：删 `IMAGE_MODEL_REF_LIMITS`/`VIDEO_FLASH_REF_MAX` 及两处模型名等值判断，改读所选模型的 `max_ref_images`（后端仍兜底，前端只管 UX）
8. `ParamSelector.vue`：尺寸选项/默认尺寸优先取当前模型 gen_params，缺省回退全局配置

### 阶段三：管理界面
9. `SettingsView.vue` 模型编辑弹窗加 4 个字段：参考图上限（数字，留空=自动）、关闭水印（开关）、尺寸规则（下拉：无/seedream）、默认尺寸；i18n 两语言

## 验证
- py_compile + `npm run type-check`
- 重启后端确认自动迁移加列；`/api/config` 各模型 gen_params 输出正确（seedream 系带水印/尺寸规则，2.1-flash 带上限 6）
- 用 plan Provider 实测回归：seedream lite 请求 1024x1024 仍出 2048x2048 且无水印（确认配置化后行为不回退）

## 交付后效果
- 新增同族模型（如 seedream 新版本）：同步进来即自动获得画像，零配置
- 新特例模型：管理员在模型编辑弹窗配一下，不动代码
- 新类型约束：加一个 schema 键 + 规则实现，一处代码
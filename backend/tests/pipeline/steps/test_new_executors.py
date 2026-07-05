# =====================================================
# Task 29.2: 4 个新 step_type 执行器单元测试
#
# 覆盖：
#   1. human_gate：validate / execute / estimate_credits
#   2. character_gen：validate / execute（上游无清单）/ execute_single（成功 / 失败 / prompt_override）
#   3. prop_gen：validate / execute（上游无清单）/ execute_single（成功 / 失败）
#   4. scene_gen：validate / execute（上游无清单）/ execute_single（成功 / 失败）
#
# Mock 策略：
#   - patch _call_llm / _generate_*_image 为可控返回值，避免真实 API 调用
#   - patch integration.save_batch_generations 避免数据库写入
#   - 用 StepExecutionContext 构造最小上下文
# =====================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.pipeline.steps.base import (
    StepExecutionContext,
    SingleItemContext,
)
from app.services.pipeline.steps.human_gate import HumanGateExecutor
from app.services.pipeline.steps.character_gen import CharacterGenExecutor
from app.services.pipeline.steps.prop_gen import PropGenExecutor
from app.services.pipeline.steps.scene_gen import SceneGenExecutor


# ---------- 辅助：构造执行器 ----------
def _make_executor(cls, step_config, steps_output=None, inputs=None):
    context = StepExecutionContext(
        inputs=inputs or {},
        steps_output=steps_output or {},
        user_id=1,
        run_id=1,
    )
    return cls(step_config, context)


def _character_step_config(**overrides):
    cfg = {
        "type": "character_gen",
        "key": "step_character_gen",
        "name": "角色生成",
        "config": {
            "character_source": "step_storyboard.characters",
            "image_config": {"size": "768x1024"},
            "llm_config": {"model": "test-model"},
        },
    }
    cfg.update(overrides)
    return cfg


def _prop_step_config(**overrides):
    cfg = {
        "type": "prop_gen",
        "key": "step_prop_gen",
        "name": "道具生成",
        "config": {
            "prop_source": "step_storyboard.props",
            "image_config": {"size": "768x1024"},
            "llm_config": {"model": "test-model"},
        },
    }
    cfg.update(overrides)
    return cfg


def _scene_step_config(**overrides):
    cfg = {
        "type": "scene_gen",
        "key": "step_scene_gen",
        "name": "场景生成",
        "config": {
            "scene_source": "step_storyboard.scenes",
            "image_config": {"size": "1024x768"},
            "llm_config": {"model": "test-model"},
        },
    }
    cfg.update(overrides)
    return cfg


# =====================================================
# 1. HumanGateExecutor 测试
# =====================================================

@pytest.mark.asyncio
async def test_human_gate_validate_no_options_passes():
    """未配置 options 时 validate 应通过"""
    executor = _make_executor(
        HumanGateExecutor,
        {"type": "human_gate", "key": "gate", "name": "gate", "config": {}},
    )
    await executor.validate()  # 不抛异常


@pytest.mark.asyncio
async def test_human_gate_validate_with_valid_options_passes():
    """配置合法 options 时 validate 应通过"""
    executor = _make_executor(
        HumanGateExecutor,
        {
            "type": "human_gate", "key": "gate", "name": "gate",
            "config": {
                "options": [
                    {"value": "approve", "label": "通过"},
                    {"value": "reject", "label": "驳回"},
                ],
            },
        },
    )
    await executor.validate()


@pytest.mark.asyncio
async def test_human_gate_validate_rejects_non_list_options():
    """options 非 list 时 validate 应抛 ValueError"""
    executor = _make_executor(
        HumanGateExecutor,
        {
            "type": "human_gate", "key": "gate", "name": "gate",
            "config": {"options": "not a list"},
        },
    )
    with pytest.raises(ValueError, match="options 必须为列表"):
        await executor.validate()


@pytest.mark.asyncio
async def test_human_gate_validate_rejects_option_missing_field():
    """options 元素缺 value/label 字段时 validate 应抛 ValueError"""
    executor = _make_executor(
        HumanGateExecutor,
        {
            "type": "human_gate", "key": "gate", "name": "gate",
            "config": {"options": [{"value": "approve"}]},  # 缺 label
        },
    )
    with pytest.raises(ValueError, match="必须包含 value 和 label"):
        await executor.validate()


@pytest.mark.asyncio
async def test_human_gate_execute_returns_placeholder_with_options():
    """execute 应返回占位结果（decision/comment 为 None），保留 options"""
    options = [{"value": "approve", "label": "通过"}]
    executor = _make_executor(
        HumanGateExecutor,
        {
            "type": "human_gate", "key": "gate", "name": "gate",
            "config": {"options": options},
        },
    )
    result = await executor.execute()
    assert result["decision"] is None
    assert result["comment"] is None
    assert result["options"] == options


@pytest.mark.asyncio
async def test_human_gate_estimate_credits_is_zero():
    """人工确认步骤不消耗积分"""
    executor = _make_executor(
        HumanGateExecutor,
        {"type": "human_gate", "key": "gate", "name": "gate", "config": {}},
    )
    assert await executor.estimate_credits() == 0


# =====================================================
# 2. CharacterGenExecutor 测试
# =====================================================

@pytest.mark.asyncio
async def test_character_gen_validate_missing_source_raises():
    """缺 character_source 配置时 validate 应抛 ValueError"""
    executor = _make_executor(
        CharacterGenExecutor,
        {
            "type": "character_gen", "key": "step_char", "name": "角色生成",
            "config": {},
        },
    )
    with pytest.raises(ValueError, match="缺少 character_source"):
        await executor.validate()


@pytest.mark.asyncio
async def test_character_gen_execute_returns_empty_when_no_upstream():
    """上游无角色清单时 execute 应返回空 items + summary"""
    executor = _make_executor(
        CharacterGenExecutor,
        _character_step_config(),
        steps_output={"step_storyboard": {}},  # 无 characters 字段
    )
    result = await executor.execute()
    assert result["items"] == []
    assert result["summary"]["total"] == 0
    assert result["summary"]["success_count"] == 0


@pytest.mark.asyncio
async def test_character_gen_execute_single_success(monkeypatch):
    """execute_single 成功路径：LLM + 图片都成功"""
    executor = _make_executor(
        CharacterGenExecutor,
        _character_step_config(),
    )
    # mock LLM 与图片生成
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(return_value="设定文本：白衬衫少女"),
    )
    monkeypatch.setattr(
        executor, "_generate_character_image",
        AsyncMock(return_value="https://example.com/char.png"),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "char_001", "name": "主角", "description": "少女"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "success"
    assert result.item["setting_text"] == "设定文本：白衬衫少女"
    assert result.item["image_url"] == "https://example.com/char.png"
    assert result.item["seed"] is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_character_gen_execute_single_llm_failure(monkeypatch):
    """execute_single LLM 失败应返回 failed 状态"""
    executor = _make_executor(CharacterGenExecutor, _character_step_config())
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(side_effect=RuntimeError("LLM 服务不可用")),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "char_001", "name": "主角", "description": "少女"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "failed"
    assert "LLM 生成失败" in result.error
    assert result.item["image_url"] == ""


@pytest.mark.asyncio
async def test_character_gen_execute_single_image_failure(monkeypatch):
    """execute_single 图片生成失败应返回 failed 状态"""
    executor = _make_executor(CharacterGenExecutor, _character_step_config())
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(return_value="设定文本"),
    )
    monkeypatch.setattr(
        executor, "_generate_character_image",
        AsyncMock(side_effect=RuntimeError("图片服务 503")),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "char_001", "name": "主角", "description": "少女"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "failed"
    assert "图片生成失败" in result.error
    # LLM 已成功，setting_text 应保留
    assert result.item["setting_text"] == "设定文本"


@pytest.mark.asyncio
async def test_character_gen_execute_single_prompt_override_skips_llm(monkeypatch):
    """prompt_override 提供时应跳过 LLM 阶段，直接用 override 作为 setting_text"""
    executor = _make_executor(CharacterGenExecutor, _character_step_config())
    # LLM 应该不被调用；如果被调用，让测试失败
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(side_effect=AssertionError("LLM should be skipped")),
    )
    monkeypatch.setattr(
        executor, "_generate_character_image",
        AsyncMock(return_value="https://example.com/char.png"),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "char_001", "name": "主角", "description": ""},
        inputs={},
        steps_output={},
        prompt_override="用户自定义的设定文本",
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "success"
    assert result.item["setting_text"] == "用户自定义的设定文本"


# =====================================================
# 3. PropGenExecutor 测试
# =====================================================

@pytest.mark.asyncio
async def test_prop_gen_validate_missing_source_raises():
    """缺 prop_source 配置时 validate 应抛 ValueError"""
    executor = _make_executor(
        PropGenExecutor,
        {"type": "prop_gen", "key": "step_prop", "name": "道具", "config": {}},
    )
    with pytest.raises(ValueError, match="缺少 prop_source"):
        await executor.validate()


@pytest.mark.asyncio
async def test_prop_gen_execute_returns_empty_when_no_upstream():
    """上游无道具清单时 execute 应返回空 items"""
    executor = _make_executor(
        PropGenExecutor,
        _prop_step_config(),
        steps_output={"step_storyboard": {}},
    )
    result = await executor.execute()
    assert result["items"] == []
    assert result["summary"]["total"] == 0


@pytest.mark.asyncio
async def test_prop_gen_execute_single_success(monkeypatch):
    """execute_single 成功路径"""
    executor = _make_executor(PropGenExecutor, _prop_step_config())
    monkeypatch.setattr(
        executor, "_generate_description_text",
        AsyncMock(return_value="金属长剑，剑柄镶嵌宝石"),
    )
    monkeypatch.setattr(
        executor, "_generate_prop_image",
        AsyncMock(return_value="https://example.com/prop.png"),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "prop_001", "name": "圣剑", "description": "主角的武器"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "success"
    assert result.item["description"] == "金属长剑，剑柄镶嵌宝石"
    assert result.item["image_url"] == "https://example.com/prop.png"


@pytest.mark.asyncio
async def test_prop_gen_execute_single_image_failure(monkeypatch):
    """execute_single 图片生成失败"""
    executor = _make_executor(PropGenExecutor, _prop_step_config())
    monkeypatch.setattr(
        executor, "_generate_description_text",
        AsyncMock(return_value="金属长剑"),
    )
    monkeypatch.setattr(
        executor, "_generate_prop_image",
        AsyncMock(side_effect=RuntimeError("图片服务超时")),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "prop_001", "name": "圣剑", "description": ""},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "failed"
    assert "图片生成失败" in result.error


# =====================================================
# 4. SceneGenExecutor 测试
# =====================================================

@pytest.mark.asyncio
async def test_scene_gen_validate_missing_source_raises():
    """缺 scene_source 配置时 validate 应抛 ValueError"""
    executor = _make_executor(
        SceneGenExecutor,
        {"type": "scene_gen", "key": "step_scene", "name": "场景", "config": {}},
    )
    with pytest.raises(ValueError, match="缺少 scene_source"):
        await executor.validate()


@pytest.mark.asyncio
async def test_scene_gen_execute_returns_empty_when_no_upstream():
    """上游无场景清单时 execute 应返回空 items"""
    executor = _make_executor(
        SceneGenExecutor,
        _scene_step_config(),
        steps_output={"step_storyboard": {}},
    )
    result = await executor.execute()
    assert result["items"] == []
    assert result["summary"]["total"] == 0


@pytest.mark.asyncio
async def test_scene_gen_execute_single_success(monkeypatch):
    """execute_single 成功路径"""
    executor = _make_executor(SceneGenExecutor, _scene_step_config())
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(return_value="黄昏时分的古城堡，光线斜照"),
    )
    monkeypatch.setattr(
        executor, "_generate_scene_image",
        AsyncMock(return_value="https://example.com/scene.png"),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "scene_001", "name": "城堡", "description": "决战场景"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "success"
    assert "黄昏" in result.item["description"]
    assert result.item["image_url"] == "https://example.com/scene.png"


@pytest.mark.asyncio
async def test_scene_gen_execute_single_llm_failure(monkeypatch):
    """execute_single LLM 失败"""
    executor = _make_executor(SceneGenExecutor, _scene_step_config())
    monkeypatch.setattr(
        executor, "_generate_setting_text",
        AsyncMock(side_effect=RuntimeError("LLM 服务 500")),
    )

    ctx = SingleItemContext(
        step=MagicMock(),
        item={"id": "scene_001", "name": "城堡", "description": "决战场景"},
        inputs={},
        steps_output={},
        config=executor.config.get("config", {}),
    )
    result = await executor.execute_single(ctx)

    assert result.status == "failed"
    assert "LLM 生成失败" in result.error

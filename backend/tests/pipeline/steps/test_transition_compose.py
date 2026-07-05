# =====================================================
# 转场合成步骤执行器单元测试
# 功能模块：
#   1. 转场解析与边界钳制（_parse_transitions）
#   2. xfade 转场类型枚举校验（_SUPPORTED_XFADE_TYPES）
#   3. 2 片段 xfade 链式合成滤镜构建（场景 A）
#   4. 3 片段链式 xfade offset 计算（场景 B）
#   5. 转场不足时 hard cut 回退与分组拼接（场景 C）
#   6. duration_ms 边界钳制（场景 E）
#   7. 非法转场类型在 validate / _parse_transitions 中的处理（场景 D）
# Mock 策略：
#   - patch asyncio.create_subprocess_exec 模拟 ffmpeg/ffprobe 子进程
#   - patch 执行器实例方法 _get_video_duration / _probe_has_audio
#   - 不实际调用 FFmpeg，仅验证滤镜构建逻辑与命令参数拼接
# =====================================================

import asyncio
import os

import pytest

from app.services.pipeline.steps.base import StepExecutionContext
from app.services.pipeline.steps.transition_compose import (
    _DEFAULT_DURATION_MS,
    _MAX_DURATION_MS,
    _MIN_DURATION_MS,
    _SUPPORTED_XFADE_TYPES,
    TransitionComposeExecutor,
)


# ---------- 公共 fixture 与辅助 ----------

def _make_executor(tmp_path, video_paths, transitions, run_id=999):
    """构造 TransitionComposeExecutor 实例

    Args:
        video_paths: 上游步骤输出的视频路径列表
        transitions: 转场配置数组
        run_id: 流水线运行 ID（用于输出文件名）
    """
    steps_output = {"video_batch": {"video_paths": video_paths}}
    context = StepExecutionContext(
        inputs={}, steps_output=steps_output, run_id=run_id
    )
    config = {
        "type": "transition_compose",
        "key": "tc",
        "config": {
            "video_clips_from": "video_batch",
            "transitions": transitions,
        },
    }
    return TransitionComposeExecutor(config, context)


@pytest.fixture
def fake_clips(tmp_path):
    """创建 3 个临时假视频文件，返回路径列表"""
    paths = []
    for i in range(3):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(f"fake{i}".encode())
        paths.append(str(p))
    return paths


@pytest.fixture
def patch_output_base(tmp_path, monkeypatch):
    """将 _OUTPUT_BASE 重定向到临时目录，避免污染项目 data 目录"""
    monkeypatch.setattr(
        "app.services.pipeline.steps.transition_compose._OUTPUT_BASE",
        str(tmp_path),
    )
    return str(tmp_path)


class _FakeProc:
    """模拟 asyncio 子进程返回对象"""

    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return (self._stdout, self._stderr)


class _SubprocessRecorder:
    """录制 asyncio.create_subprocess_exec 调用

    - commands: 捕获所有调用过的命令（args 列表）
    - 对 ffmpeg 合成命令（最后一个参数为 .mp4 输出路径），自动创建假输出文件
      以满足被测代码对输出文件存在性 / 大小的检查
    """

    def __init__(self):
        self.commands = []
        self.returncode = 0

    async def __call__(self, *args, **kwargs):
        self.commands.append(list(args))
        # 仅对 ffmpeg 合成 / concat 命令创建假输出文件（输出路径以 .mp4 结尾）
        if args and args[0] == "ffmpeg" and len(args) > 1 and str(args[-1]).endswith(".mp4"):
            out_path = args[-1]
            try:
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"fake output content")
            except Exception:
                pass
        return _FakeProc(returncode=self.returncode)


@pytest.fixture
def mock_subprocess(monkeypatch):
    """patch asyncio.create_subprocess_exec，返回录制器"""
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", recorder)
    return recorder


def _patch_probes(monkeypatch, executor, durations, has_audio=True):
    """patch 执行器的 _get_video_duration / _probe_has_audio 方法

    Args:
        durations: 与 clip_paths 顺序对应的时长列表
        has_audio: 所有片段是否含音频流
    """
    duration_map = {}

    async def fake_get_duration(path, _durations=durations, _map=duration_map):
        if path not in _map:
            _map[path] = _durations[len(_map) % len(_durations)]
        return _map[path]

    async def fake_probe_audio(path):
        return has_audio

    monkeypatch.setattr(executor, "_get_video_duration", fake_get_duration)
    monkeypatch.setattr(executor, "_probe_has_audio", fake_probe_audio)


# =====================================================
# 场景 D: 转场类型枚举验证
# =====================================================

def test_supported_xfade_types_count():
    """验证 _SUPPORTED_XFADE_TYPES 包含 14 种类型"""
    assert len(_SUPPORTED_XFADE_TYPES) == 14


def test_supported_xfade_types_members():
    """验证 14 种 xfade 类型的具体成员"""
    expected = {
        "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
        "slideleft", "slideright", "slideup", "slidedown",
        "circleopen", "circleclose", "dissolve", "pixelize", "radialsmooth",
    }
    assert set(_SUPPORTED_XFADE_TYPES) == expected


def test_parse_transitions_invalid_type_fallback_to_fade(tmp_path):
    """验证非法 type 在 _parse_transitions 中兜底降级为 fade"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": [{"type": "nonexistent_type", "duration_ms": 500}]}
    result = executor._parse_transitions(config, 2)
    assert len(result) == 1
    assert result[0] is not None
    # 非法类型降级为 fade
    assert result[0]["type"] == "fade"
    assert result[0]["duration_ms"] == 500


@pytest.mark.asyncio
async def test_validate_rejects_unknown_transition_type(tmp_path, monkeypatch):
    """验证 validate() 对非法 type 报错（ValueError）"""
    executor = _make_executor(
        tmp_path,
        [],
        [{"type": "nonexistent_type", "duration_ms": 500}],
    )
    # mock ffmpeg -version 检查通过
    async def fake_exec(*args, **kwargs):
        return _FakeProc(returncode=0, stdout=b"ffmpeg version 6.0")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(ValueError, match="不受支持"):
        await executor.validate()


# =====================================================
# 场景 E: duration_ms 边界钳制
# =====================================================

def test_parse_transitions_clamp_min_duration(tmp_path):
    """验证 duration_ms < 100 被钳制为 _MIN_DURATION_MS（100）"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": [{"type": "fade", "duration_ms": 50}]}
    result = executor._parse_transitions(config, 2)
    assert result[0]["duration_ms"] == _MIN_DURATION_MS


def test_parse_transitions_clamp_max_duration(tmp_path):
    """验证 duration_ms > 3000 被钳制为 _MAX_DURATION_MS（3000）"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": [{"type": "fade", "duration_ms": 5000}]}
    result = executor._parse_transitions(config, 2)
    assert result[0]["duration_ms"] == _MAX_DURATION_MS


def test_parse_transitions_default_duration(tmp_path):
    """验证未指定 duration_ms 时使用默认值 _DEFAULT_DURATION_MS（500）"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": [{"type": "fade"}]}
    result = executor._parse_transitions(config, 2)
    assert result[0]["duration_ms"] == _DEFAULT_DURATION_MS


def test_parse_transitions_hard_cut_for_missing_slot(tmp_path):
    """验证未配置的转场槽位返回 None（hard cut 硬切）"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": [{"type": "fade", "duration_ms": 500}]}
    # 3 片段需要 2 个转场槽位，仅配置 1 个
    result = executor._parse_transitions(config, 3)
    assert len(result) == 2
    assert result[0] == {"type": "fade", "duration_ms": 500}
    assert result[1] is None


def test_parse_transitions_non_list_input(tmp_path):
    """验证 transitions 非 list 时回退为空（全部 hard cut）"""
    executor = _make_executor(tmp_path, [], [])
    config = {"transitions": "not a list"}
    result = executor._parse_transitions(config, 3)
    assert result == [None, None]


# =====================================================
# 场景 A: 2 片段 + 1 个转场
# =====================================================

@pytest.mark.asyncio
async def test_scenario_a_2_clips_xfade(
    tmp_path, fake_clips, mock_subprocess, patch_output_base, monkeypatch
):
    """场景 A: 2 片段 + 1 个 fade 转场

    验证：
    - _parse_transitions 返回长度 1 的转场列表
    - ffmpeg xfade 滤镜构建参数正确
    - offset = d0 - dt = 3.0 - 0.5 = 2.500
    """
    transitions_config = [{"type": "fade", "duration_ms": 500}]
    clips = fake_clips[:2]
    executor = _make_executor(tmp_path, clips, transitions_config)

    # 1. 验证 _parse_transitions 解析结果
    parsed = executor._parse_transitions(
        {"transitions": transitions_config}, len(clips)
    )
    assert len(parsed) == 1
    assert parsed[0] == {"type": "fade", "duration_ms": 500}

    # 2. mock 探测方法，固定时长 [3.0, 4.0]，全部含音频
    _patch_probes(monkeypatch, executor, durations=[3.0, 4.0], has_audio=True)

    # 3. 执行（_merge_group_xfade 真实执行，ffmpeg 子进程被 mock）
    result = await executor.execute()

    # 4. 验证 ffmpeg 调用次数（单组单次 xfade 合成）
    ffmpeg_cmds = [c for c in mock_subprocess.commands if c[0] == "ffmpeg"]
    assert len(ffmpeg_cmds) == 1

    cmd = ffmpeg_cmds[0]
    # 验证 filter_complex 参数
    assert "-filter_complex" in cmd
    fc_idx = cmd.index("-filter_complex")
    filter_complex = cmd[fc_idx + 1]

    # 验证 xfade 滤镜：offset = 3.0 - 0.5 = 2.500
    assert "xfade=transition=fade" in filter_complex
    assert "duration=0.500" in filter_complex
    assert "offset=2.500" in filter_complex
    assert "[vout]" in filter_complex

    # 验证 acrossfade 音频滤镜（两片段都有音频流）
    assert "acrossfade=d=0.500" in filter_complex
    assert "[aout]" in filter_complex

    # 验证输入是 2 个片段
    assert cmd.count("-i") == 2

    # 验证返回结果
    assert result["clip_count"] == 2
    assert result["transitions_applied"] == [{"type": "fade", "duration_ms": 500}]


# =====================================================
# 场景 B: 3 片段 + 2 个转场
# =====================================================

@pytest.mark.asyncio
async def test_scenario_b_3_clips_chain_xfade(
    tmp_path, fake_clips, mock_subprocess, patch_output_base, monkeypatch
):
    """场景 B: 3 片段 + 2 个转场（fade + wipeleft）

    验证：
    - _parse_transitions 返回长度 2 的转场列表
    - 链式 xfade 的 offset 计算：
      offset_1 = d0 - dt0 = 3.0 - 0.5 = 2.500
      offset_2 = (d0+d1) - (dt0+dt1) = 7.0 - 0.8 = 6.200
    """
    transitions_config = [
        {"type": "fade", "duration_ms": 500},
        {"type": "wipeleft", "duration_ms": 300},
    ]
    clips = fake_clips
    executor = _make_executor(tmp_path, clips, transitions_config)

    # 1. 验证 _parse_transitions 解析结果
    parsed = executor._parse_transitions(
        {"transitions": transitions_config}, len(clips)
    )
    assert len(parsed) == 2
    assert parsed[0] == {"type": "fade", "duration_ms": 500}
    assert parsed[1] == {"type": "wipeleft", "duration_ms": 300}

    # 2. mock 探测方法，固定时长 [3.0, 4.0, 2.5]
    _patch_probes(monkeypatch, executor, durations=[3.0, 4.0, 2.5], has_audio=True)

    # 3. 执行
    result = await executor.execute()

    # 4. 验证 ffmpeg 调用（3 片段同一组，1 次 xfade 链式合成）
    ffmpeg_cmds = [c for c in mock_subprocess.commands if c[0] == "ffmpeg"]
    assert len(ffmpeg_cmds) == 1

    cmd = ffmpeg_cmds[0]
    fc_idx = cmd.index("-filter_complex")
    filter_complex = cmd[fc_idx + 1]

    # 验证第 1 个 xfade（fade）：offset = 3.0 - 0.5 = 2.500
    assert "xfade=transition=fade:duration=0.500:offset=2.500" in filter_complex
    # 验证第 2 个 xfade（wipeleft）：offset = (3.0+4.0) - (0.5+0.3) = 6.200
    assert "xfade=transition=wipeleft:duration=0.300:offset=6.200" in filter_complex

    # 验证中间标签与最终输出标签
    assert "[v0]" in filter_complex
    assert "[vout]" in filter_complex
    assert "[a0]" in filter_complex
    assert "[aout]" in filter_complex

    # 验证输入是 3 个片段
    assert cmd.count("-i") == 3

    # 验证返回结果
    assert result["clip_count"] == 3
    assert result["transitions_applied"] == [
        {"type": "fade", "duration_ms": 500},
        {"type": "wipeleft", "duration_ms": 300},
    ]


# =====================================================
# 场景 C: 3 片段 + 1 个转场（转场不足回退 hard cut）
# =====================================================

@pytest.mark.asyncio
async def test_scenario_c_fallback_to_hard_cut(
    tmp_path, fake_clips, patch_output_base, monkeypatch
):
    """场景 C: 3 片段 + 1 个 fade 转场，第二对回退为 hard cut

    验证：
    - _parse_transitions 返回 [fade, None]
    - 分组逻辑：前两个片段（有转场）归为一组，第三个片段单独一组
    - _merge_group_xfade 仅被调用 1 次（组内仅 2 个片段）
    - _concat_videos 被调用 1 次（2 个组需要拼接）
    - transitions_applied 记录第二对为 hard_cut
    """
    transitions_config = [{"type": "fade", "duration_ms": 500}]
    clips = fake_clips
    executor = _make_executor(tmp_path, clips, transitions_config)

    # 1. 验证 _parse_transitions 返回 [fade, None]
    parsed = executor._parse_transitions(
        {"transitions": transitions_config}, len(clips)
    )
    assert len(parsed) == 2
    assert parsed[0] == {"type": "fade", "duration_ms": 500}
    assert parsed[1] is None  # hard cut

    # 2. mock 探测方法
    _patch_probes(monkeypatch, executor, durations=[3.0, 4.0, 2.5], has_audio=True)

    # 3. mock _merge_group_xfade 与 _concat_videos，捕获调用参数
    merge_calls = []

    async def fake_merge_group_xfade(clip_paths, durs, has_audios, trans, gi):
        merge_calls.append({
            "clip_paths": list(clip_paths),
            "durations": list(durs),
            "transitions": list(trans),
            "group_index": gi,
        })
        out = tmp_path / f"group_{gi}_merged.mp4"
        out.write_bytes(b"merged")
        return str(out)

    concat_calls = []

    async def fake_concat(paths, output):
        concat_calls.append({"paths": list(paths), "output": output})
        # 创建最终输出文件
        with open(output, "wb") as f:
            f.write(b"final")
        return None

    monkeypatch.setattr(executor, "_merge_group_xfade", fake_merge_group_xfade)
    monkeypatch.setattr(executor, "_concat_videos", fake_concat)

    # 4. 执行
    result = await executor.execute()

    # 5. 验证 _merge_group_xfade 仅被调用 1 次（前两个片段一组）
    assert len(merge_calls) == 1
    assert merge_calls[0]["group_index"] == 0
    # 组内只有 2 个片段（前两个）
    assert len(merge_calls[0]["clip_paths"]) == 2
    assert merge_calls[0]["clip_paths"] == clips[:2]
    # 组内仅 1 个转场
    assert merge_calls[0]["transitions"] == [{"type": "fade", "duration_ms": 500}]

    # 6. 验证 _concat_videos 被调用 1 次（2 个组需要拼接）
    assert len(concat_calls) == 1
    # 2 个组的输出（xfade 合成结果 + 单片段原路径）
    assert len(concat_calls[0]["paths"]) == 2

    # 7. 验证返回结果
    assert result["clip_count"] == 3
    assert len(result["transitions_applied"]) == 2
    # 第一对：fade 转场
    assert result["transitions_applied"][0] == {"type": "fade", "duration_ms": 500}
    # 第二对：hard_cut 硬切
    assert result["transitions_applied"][1] == {"type": "hard_cut", "duration_ms": 0}

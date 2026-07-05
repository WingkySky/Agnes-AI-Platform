# =====================================================
# 转场合成步骤执行器
# 功能：
#   1. 从上游 video_batch 步骤获取多个视频片段
#   2. 应用 FFmpeg xfade 转场合成单个视频
#   3. 支持 14 种 xfade 转场类型
#   4. transitions 数组未覆盖的片段对使用 hard cut（concat 直切）
#   5. 链式 filter_complex 实现 N 段视频的连续转场
#
# 输出：
#   {
#     "merged_video_path": "/path/to/merged.mp4",
#     "clip_count": N,
#     "transitions_applied": [{"type": "fade", "duration_ms": 500}, ...]
#   }
# =====================================================

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor

logger = logging.getLogger("agnes_platform.pipeline")

# 最终视频输出目录（与 ffmpeg_composite 一致，通过 /api/pipeline/outputs/ 路由对外提供访问）
_OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "pipeline_outputs",
)
os.makedirs(_OUTPUT_BASE, exist_ok=True)

# 支持的 xfade 转场类型（14 种）
_SUPPORTED_XFADE_TYPES = frozenset({
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circleopen", "circleclose", "dissolve", "pixelize", "radialsmooth",
})

# 转场时长默认值与范围（毫秒）
_DEFAULT_DURATION_MS = 500
_MIN_DURATION_MS = 100
_MAX_DURATION_MS = 3000


@register_step_executor
class TransitionComposeExecutor(BaseStepExecutor):
    """
    转场合成步骤执行器

    将上游 video_batch 步骤产出的多个视频片段通过 FFmpeg xfade 滤镜合成单个视频。
    支持配置转场类型与时长，未配置的片段对使用 hard cut（concat 拼接）。
    """

    step_type = "transition_compose"

    async def validate(self) -> None:
        """验证输入：必须指定 video_clips_from，ffmpeg 可用，transitions 配置合法"""
        config = self.config.get("config", {})
        from_step = config.get("video_clips_from")
        if not from_step:
            raise ValueError("transition_compose 必须指定 video_clips_from（上游 video_batch 步骤 key）")

        # 检查 ffmpeg 是否可用
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode != 0:
                raise RuntimeError("ffmpeg 不可用")
        except Exception as e:
            raise ValueError(f"ffmpeg 不可用: {e}")

        # 校验 transitions 配置（数组中每项含 type 和可选 duration_ms）
        transitions = config.get("transitions", []) or []
        if not isinstance(transitions, list):
            raise ValueError("transitions 必须是数组")
        for i, t in enumerate(transitions):
            if not isinstance(t, dict):
                raise ValueError(f"transitions[{i}] 必须是对象")
            ttype = t.get("type")
            if not ttype:
                raise ValueError(f"transitions[{i}] 缺少 type 字段")
            if ttype not in _SUPPORTED_XFADE_TYPES:
                raise ValueError(
                    f"transitions[{i}].type='{ttype}' 不受支持，"
                    f"支持的类型: {', '.join(sorted(_SUPPORTED_XFADE_TYPES))}"
                )
            duration_ms = t.get("duration_ms", _DEFAULT_DURATION_MS)
            try:
                d = int(duration_ms)
                if d < _MIN_DURATION_MS or d > _MAX_DURATION_MS:
                    raise ValueError(
                        f"transitions[{i}].duration_ms={d} 超出范围 "
                        f"[{_MIN_DURATION_MS}, {_MAX_DURATION_MS}]"
                    )
            except (ValueError, TypeError):
                raise ValueError(f"transitions[{i}].duration_ms 必须是整数")

    async def execute(self) -> Dict[str, Any]:
        """执行转场合成：下载片段 → 探测时长 → 分组合成 → 拼接输出"""
        config = self.config.get("config", {})
        from_step = config.get("video_clips_from")

        # 1. 解析上游视频片段列表
        clips_data = self._resolve_video_clips(from_step)
        if len(clips_data) < 1:
            raise ValueError(f"上游步骤 '{from_step}' 没有视频片段")
        if len(clips_data) == 1:
            # 单片段：无需转场，直接复制到输出目录
            logger.info(f"[转场合成] 仅 1 个片段，直接复制到输出: step_key={self.step_key}")
            run_id = self.context.run_id or "tmp"
            dest = os.path.join(_OUTPUT_BASE, f"transition_merged_{run_id}.mp4")
            shutil.copy2(clips_data[0]["path"] or clips_data[0]["url"], dest)
            return {
                "merged_video_path": dest,
                "clip_count": 1,
                "transitions_applied": [],
            }

        self._total = len(clips_data)
        logger.info(f"[转场合成] 开始处理 {len(clips_data)} 个片段: step_key={self.step_key}")

        # 2. 解析转场配置（补齐到 clip_count-1 个槽位，hard cut 用 None）
        transitions = self._parse_transitions(config, len(clips_data))

        # 3. 下载所有片段到临时目录
        self._progress_phase = "downloading"
        self._completed_count = 0
        clip_paths = await self._download_clips(clips_data)

        # 4. 探测每个片段的时长和音频流
        self._progress_phase = "probing"
        self._completed_count = 0
        durations: List[float] = []
        has_audio_list: List[bool] = []
        for path in clip_paths:
            d = await self._get_video_duration(path)
            if d <= 0:
                raise RuntimeError(f"无法获取视频时长: {path}")
            durations.append(d)
            has_audio_list.append(await self._probe_has_audio(path))
            self._completed_count += 1

        # 5. 分组合成：同组内 xfade 链式合成，组间 concat 硬切
        self._progress_phase = "merging"
        merged_path, transitions_applied = await self._merge_with_transitions(
            clip_paths, durations, has_audio_list, transitions
        )

        logger.info(f"[转场合成] 完成: {merged_path}, 片段数={len(clip_paths)}")
        return {
            "merged_video_path": merged_path,
            "clip_count": len(clip_paths),
            "transitions_applied": transitions_applied,
        }

    async def estimate_credits(self) -> int:
        """转场合成不消耗外部 API 积分"""
        return 1

    async def get_progress(self) -> Dict[str, Any]:
        """返回合成进度（分阶段：下载/探测/合并）"""
        total = getattr(self, "_total", 0)
        if total == 0:
            return {}
        phase = getattr(self, "_progress_phase", "")
        completed = getattr(self, "_completed_count", 0)

        phase_map = {
            "downloading": (0.0, 0.3, "下载视频片段"),
            "probing": (0.3, 0.4, "探测视频时长"),
            "merging": (0.4, 1.0, "应用转场合并"),
        }
        if phase not in phase_map:
            return {}
        start, end, text = phase_map[phase]
        if phase in ("downloading", "probing"):
            percent = round(start + (end - start) * (completed / total if total > 0 else 0), 3)
        else:
            percent = end
        return {
            "current": completed if phase in ("downloading", "probing") else total,
            "total": total,
            "percent": percent,
            "phase": phase,
            "phase_text": text,
        }

    # ---------- 内部方法 ----------

    def _resolve_video_clips(self, from_step: str) -> List[Dict[str, Any]]:
        """从上游步骤输出中解析视频片段列表

        支持两种上游输出格式：
        - video_paths: 字符串数组（URL 或本地路径）
        - videos: 对象数组，含 video_url 字段（video_batch 标准输出）
        """
        step_output = self.context.steps_output.get(from_step, {})

        # 优先用 video_paths（字符串数组）
        video_paths = step_output.get("video_paths")
        if isinstance(video_paths, list) and video_paths:
            result = []
            for i, p in enumerate(video_paths):
                if not isinstance(p, str) or not p:
                    continue
                result.append({"index": i, "url": p, "path": p if os.path.exists(p) else ""})
            return result

        # 回退到 videos（video_batch 标准输出：对象数组）
        videos = step_output.get("videos", [])
        if not isinstance(videos, list):
            return []

        result = []
        for i, v in enumerate(videos):
            if not isinstance(v, dict):
                continue
            url = v.get("video_url") or v.get("url") or ""
            if not url:
                continue
            result.append({
                "index": v.get("index", i),
                "url": url,
                "path": url if os.path.exists(url) else "",
            })

        # 按 index 排序，保证片段顺序正确
        result.sort(key=lambda x: x["index"])
        return result

    def _parse_transitions(
        self, config: Dict[str, Any], clip_count: int
    ) -> List[Optional[Dict[str, Any]]]:
        """解析转场配置，补齐到 clip_count-1 个槽位

        未配置的槽位返回 None（表示 hard cut 硬切）
        """
        raw = config.get("transitions", []) or []
        if not isinstance(raw, list):
            raw = []

        result: List[Optional[Dict[str, Any]]] = []
        for i in range(clip_count - 1):
            if i < len(raw) and isinstance(raw[i], dict):
                t = raw[i]
                ttype = t.get("type", "fade")
                if ttype not in _SUPPORTED_XFADE_TYPES:
                    # validate() 已校验，这里兜底降级为 fade
                    logger.warning(f"[转场合成] 不支持的转场类型 '{ttype}'，降级为 fade")
                    ttype = "fade"
                duration_ms = int(t.get("duration_ms", _DEFAULT_DURATION_MS))
                # clamp 到合法范围
                duration_ms = max(_MIN_DURATION_MS, min(_MAX_DURATION_MS, duration_ms))
                result.append({"type": ttype, "duration_ms": duration_ms})
            else:
                result.append(None)  # hard cut

        return result

    async def _download_clips(self, clips: List[Dict[str, Any]]) -> List[str]:
        """下载所有视频片段到临时目录

        本地路径直接使用；远程 URL 通过 httpx 下载。
        任意片段下载失败则抛出异常（xfade 需要全部片段才能合成）。
        """
        temp_dir = tempfile.mkdtemp(prefix="agnes_transition_")
        paths: List[str] = []

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for i, clip in enumerate(clips):
                # 优先用本地路径
                local_path = clip.get("path", "")
                if local_path and os.path.exists(local_path):
                    paths.append(local_path)
                    self._completed_count = i + 1
                    continue

                url = clip.get("url", "")
                if not url:
                    raise RuntimeError(f"片段 #{i} 没有 URL 且无本地路径")

                out_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
                try:
                    resp = await client.get(url, headers={"User-Agent": "Agnes-Platform"})
                    if resp.status_code != 200:
                        raise RuntimeError(f"HTTP {resp.status_code}")
                    with open(out_path, "wb") as f:
                        f.write(resp.content)
                    paths.append(out_path)
                    logger.debug(f"[转场合成] 下载片段 #{i}: {len(resp.content)} bytes")
                except Exception as e:
                    raise RuntimeError(f"下载片段 #{i} 失败: {e}")

                self._completed_count = i + 1

        return paths

    async def _probe_has_audio(self, video_path: str) -> bool:
        """用 ffprobe 检测视频是否包含音频流"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1",
                video_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return b"audio" in stdout
        except Exception:
            return False

    async def _get_video_duration(self, video_path: str) -> float:
        """用 ffprobe 获取视频时长（秒）"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return float(stdout.decode().strip())
        except Exception:
            return 0.0

    async def _merge_with_transitions(
        self,
        clip_paths: List[str],
        durations: List[float],
        has_audio_list: List[bool],
        transitions: List[Optional[Dict[str, Any]]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """按转场分组合成

        策略：
        - 连续的 xfade 转场归为同一组，组内用 xfade 链式合成
        - hard cut（None）处切分组，组间用 concat 拼接
        - 最终输出到 _OUTPUT_BASE/transition_merged_{run_id}.mp4
        """
        # 构建 transitions_applied（完整列表，包含 hard_cut 记录）
        transitions_applied: List[Dict[str, Any]] = []
        for i in range(len(clip_paths) - 1):
            t = transitions[i] if i < len(transitions) else None
            if t is not None:
                transitions_applied.append({"type": t["type"], "duration_ms": t["duration_ms"]})
            else:
                transitions_applied.append({"type": "hard_cut", "duration_ms": 0})

        # 1. 按转场分组：连续的非 None 转场归为同一组
        groups: List[List[int]] = []
        current_group: List[int] = [0]
        for i in range(len(clip_paths) - 1):
            trans = transitions[i] if i < len(transitions) else None
            if trans is not None:
                current_group.append(i + 1)
            else:
                groups.append(current_group)
                current_group = [i + 1]
        groups.append(current_group)

        logger.info(
            f"[转场合成] 分组完成: {len(groups)} 组，"
            f"组大小={[len(g) for g in groups]}"
        )

        # 2. 合成每个组
        group_outputs: List[str] = []
        for gi, group in enumerate(groups):
            if len(group) == 1:
                # 单片段组：直接用原路径
                group_outputs.append(clip_paths[group[0]])
            else:
                # 多片段组：用 xfade 链式合成
                group_clips = [clip_paths[i] for i in group]
                group_durations = [durations[i] for i in group]
                group_has_audio = [has_audio_list[i] for i in group]
                # 组内转场：group[j] 与 group[j+1] 之间的转场是 transitions[group[j]]
                group_transitions = [
                    transitions[idx] for idx in group[:-1] if idx < len(transitions)
                ]
                merged = await self._merge_group_xfade(
                    group_clips, group_durations, group_has_audio, group_transitions, gi
                )
                group_outputs.append(merged)

        # 3. 拼接所有组（concat）
        run_id = self.context.run_id or "tmp"
        final_path = os.path.join(_OUTPUT_BASE, f"transition_merged_{run_id}.mp4")

        if len(group_outputs) == 1:
            # 只有一个组：直接复制到输出目录
            shutil.copy2(group_outputs[0], final_path)
        else:
            # 多个组：concat 拼接
            await self._concat_videos(group_outputs, final_path)

        return final_path, transitions_applied

    async def _merge_group_xfade(
        self,
        clip_paths: List[str],
        durations: List[float],
        has_audio_list: List[bool],
        transitions: List[Dict[str, Any]],
        group_index: int,
    ) -> str:
        """对一组片段应用 xfade 链式合成

        - 视频：xfade 链式 filter_complex
          offset_i = (sum_d_0..i) - (sum_dt_0..i)
          即累计前置片段时长减去累计转场时长
        - 音频：若所有片段都有音频流，用 acrossfade 链式合成；否则丢弃音频
        """
        n = len(clip_paths)
        if n == 1:
            return clip_paths[0]

        # 检查所有片段是否都有音频流
        all_have_audio = all(has_audio_list)

        # 输出到临时文件
        temp_dir = os.path.dirname(clip_paths[0]) or tempfile.gettempdir()
        group_out = os.path.join(temp_dir, f"group_{group_index}_merged.mp4")

        # 构建 filter_complex
        # 视频：[0:v][1:v]xfade=...[v0]; [v0][2:v]xfade=...[v1]; ... [vout]
        # 音频：[0:a][1:a]acrossfade=...[a0]; [a0][2:a]acrossfade=...[a1]; ... [aout]
        video_filters: List[str] = []
        audio_filters: List[str] = []

        prev_v_label = "[0:v]"
        prev_a_label = "[0:a]"
        sum_d = durations[0]  # 累计前置片段时长
        sum_dt = 0.0  # 累计转场时长

        for i in range(n - 1):
            t = transitions[i]
            dt = t["duration_ms"] / 1000.0
            ttype = t["type"]

            # offset_i = sum_d(0..i) - sum_dt(0..i)
            # 当前 sum_d 已是 d_0+...+d_i，sum_dt 是 dt_0+...+dt_(i-1)
            offset = sum_d - sum_dt - dt
            if offset < 0:
                # 转场时长超过前置片段时长，clamp 到 0（ffmpeg 会自动处理）
                logger.warning(
                    f"[转场合成] 组{group_index} 第{i}个转场 offset<0，"
                    f"sum_d={sum_d:.3f} sum_dt={sum_dt:.3f} dt={dt:.3f}"
                )
                offset = 0.0

            # 最后一个 xfade 输出标签为 [vout]/[aout]，中间用 [vN]/[aN]
            is_last = (i == n - 2)
            v_out_label = "[vout]" if is_last else f"[v{i}]"
            a_out_label = "[aout]" if is_last else f"[a{i}]"

            video_filters.append(
                f"{prev_v_label}[{i+1}:v]xfade=transition={ttype}"
                f":duration={dt:.3f}:offset={offset:.3f}{v_out_label}"
            )
            prev_v_label = v_out_label

            if all_have_audio:
                audio_filters.append(
                    f"{prev_a_label}[{i+1}:a]acrossfade=d={dt:.3f}{a_out_label}"
                )
                prev_a_label = a_out_label

            # 更新累计值
            sum_d += durations[i + 1]
            sum_dt += dt

        # 组合 filter_complex
        filter_parts = video_filters + audio_filters
        filter_complex = ";".join(filter_parts)

        # 构建 ffmpeg 命令
        cmd: List[str] = ["ffmpeg", "-y"]
        for p in clip_paths:
            cmd.extend(["-i", p])
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[vout]"])
        if all_have_audio:
            cmd.extend(["-map", "[aout]"])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
        ])
        if all_have_audio:
            cmd.extend(["-c:a", "aac"])
        cmd.extend(["-movflags", "+faststart", group_out])

        logger.debug(
            f"[转场合成] 组{group_index} filter_complex: {filter_complex[:200]}..."
        )

        # 执行 ffmpeg
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode != 0:
                err_text = stderr.decode(errors="ignore")
                logger.error(f"[转场合成] xfade 合成失败（组{group_index}）: {err_text[-500:]}")
                raise RuntimeError(f"xfade 合成失败（组{group_index}）: {err_text[-300:]}")
            if not os.path.exists(group_out) or os.path.getsize(group_out) == 0:
                raise RuntimeError(f"xfade 合成输出文件为空（组{group_index}）")
            return group_out
        except asyncio.TimeoutError:
            raise RuntimeError(f"xfade 合成超时（组{group_index}）")

    async def _concat_videos(self, video_paths: List[str], output_path: str) -> None:
        """拼接多个视频（concat demuxer）

        优先用 -c copy（无重编码，最快）；
        如果失败（编码/分辨率不一致），fallback 到重编码。
        """
        valid_paths = [p for p in video_paths if p and os.path.exists(p)]
        if not valid_paths:
            raise ValueError("没有可拼接的视频文件")

        # 创建 concat list 文件
        list_path = output_path + ".concat.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for p in valid_paths:
                # concat demuxer 要求单引号转义
                escaped = p.replace("'", "\\'")
                f.write(f"file '{escaped}'\n")

        # 第一阶段：尝试 -c copy（最快）
        copy_ok = await self._try_concat_copy(list_path, output_path)
        if copy_ok:
            self._cleanup_file(list_path)
            return

        # 第二阶段：fallback 到重编码
        logger.warning("[转场合成] concat copy 失败，改用重编码模式")
        reencode_ok = await self._try_concat_reencode(list_path, output_path)
        self._cleanup_file(list_path)
        if not reencode_ok:
            raise RuntimeError("视频拼接失败（copy 和 reencode 均失败）")

    async def _try_concat_copy(self, list_path: str, output_path: str) -> bool:
        """尝试用 -c copy 拼接（无重编码）"""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode != 0:
                logger.debug(
                    f"[转场合成] concat copy 失败: {stderr.decode(errors='ignore')[:200]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.debug(f"[转场合成] concat copy 异常: {e}")
            return False

    async def _try_concat_reencode(self, list_path: str, output_path: str) -> bool:
        """重编码拼接（处理编码/分辨率不一致的情况）"""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600.0)
            if proc.returncode != 0:
                logger.warning(
                    f"[转场合成] concat reencode 失败: {stderr.decode(errors='ignore')[:300]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.warning(f"[转场合成] concat reencode 异常: {e}")
            return False

    def _cleanup_file(self, path: str) -> None:
        """清理临时文件"""
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

# =====================================================
# 视频剪辑步骤执行器（灵感源自 video-use 项目 helpers/render.py）
#
# 核心功能:
#   1. 基于时间戳裁剪/删除指定片段（trim / cut 两种操作）
#   2. 30ms 音频淡入淡出，避免切点爆音（移植自 video-use render.py）
#   3. 多段片段自动拼接为最终视频
#
# 应用场景:
#   - 用户在 PipelineResultView 看到生成结果后，剔除不满意的分镜片段
#   - 对单个长视频裁剪出精彩片段
#   - 删除中间的废片段落，保留首尾有效内容
#
# 输入配置 (config):
#   from_step: 上游视频步骤 key（必填）
#   operations: 编辑操作列表（必填），每项格式:
#     [
#       {"type": "trim", "start": 2.0, "end": 8.5},   # 保留 2.0~8.5 秒
#       {"type": "cut", "start": 10.0, "end": 15.0},  # 删除 10.0~15.0 秒
#       ...
#     ]
#   - trim 操作：仅保留 [start, end] 区间
#   - cut 操作：删除 [start, end] 区间，保留其余部分
#   - 同一视频上多个操作按顺序执行
#   - 单视频源（from_step.videos 长度为 1）时直接对该视频操作
#   - 多视频源时，对每个视频独立应用相同操作列表
#
# 输出:
#   {
#     "videos": [{"index": 0, "video_url": "...", "success": True}, ...],
#     "total": N, "success_count": N, "failed_count": 0,
#     "operations_applied": 2
#   }
# =====================================================

import asyncio
import logging
import os
import tempfile
from typing import Dict, Any, List, Optional, Tuple

import httpx

from app.core.database import new_async_session
from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor
from app.services.pipeline import integration

logger = logging.getLogger("agnes_platform.pipeline")

# 最终视频输出目录（与 ffmpeg_composite 共用）
_OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "pipeline_outputs",
)
os.makedirs(_OUTPUT_BASE, exist_ok=True)

# 音频淡入淡出时长（秒），来自 video-use render.py Rule 3
_AUDIO_FADE_DURATION = 0.03


@register_step_executor
class VideoEditExecutor(BaseStepExecutor):
    """
    视频剪辑步骤执行器

    对上游视频应用 trim/cut 操作，支持多段拼接。
    所有切点叠加 30ms 音频淡入淡出，避免爆音。
    """

    step_type = "video_edit"

    async def validate(self) -> None:
        """验证输入：必须指定 from_step 和 operations"""
        config = self.config.get("config", {})
        if not config.get("from_step"):
            raise ValueError("video_edit 必须指定 from_step（上游视频步骤）")

        operations = config.get("operations") or []
        if not operations:
            raise ValueError("video_edit 必须指定 operations（编辑操作列表）")

        # 校验每个操作
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                raise ValueError(f"操作 #{i} 必须是字典")
            op_type = op.get("type")
            if op_type not in ("trim", "cut"):
                raise ValueError(f"操作 #{i} type 必须是 trim 或 cut，当前: {op_type}")
            start = op.get("start")
            end = op.get("end")
            if start is None or end is None:
                raise ValueError(f"操作 #{i} 必须指定 start 和 end")
            try:
                start_f = float(start)
                end_f = float(end)
            except (ValueError, TypeError):
                raise ValueError(f"操作 #{i} start/end 必须是数字")
            if start_f < 0 or end_f < 0:
                raise ValueError(f"操作 #{i} start/end 不能为负数")
            if end_f <= start_f:
                raise ValueError(f"操作 #{i} end 必须大于 start")

        # 检查 ffmpeg 可用性
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

    async def execute(self) -> Dict[str, Any]:
        """执行视频剪辑"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        operations: List[Dict[str, Any]] = config.get("operations") or []

        logger.info(
            f"[视频剪辑] 开始: step={self.step_key}, from={from_step}, "
            f"operations={len(operations)}"
        )

        # 1. 获取上游视频列表
        step_output = self.context.steps_output.get(from_step, {})
        videos: List[Dict[str, Any]] = step_output.get("videos", [])
        if not videos:
            raise ValueError(f"上游步骤 '{from_step}' 没有视频产出")

        # 2. 下载所有视频到临时目录
        self._progress_phase = "downloading"
        self._completed_count = 0
        self._total = len(videos)
        video_paths = await self._download_all_videos(videos)

        # 3. 逐个视频应用剪辑操作
        self._progress_phase = "editing"
        self._completed_count = 0
        edited_videos: List[Dict[str, Any]] = []
        for idx, vpath in enumerate(video_paths):
            if not vpath:
                logger.warning(f"[视频剪辑] 跳过空视频 #{idx}")
                edited_videos.append({
                    "index": idx,
                    "video_url": videos[idx].get("video_url", ""),
                    "success": False,
                    "error": "下载失败",
                })
                continue

            try:
                out_path = await self._apply_operations(vpath, idx, operations)
                filename = os.path.basename(out_path)
                url = f"/api/pipeline/outputs/{filename}"
                edited_videos.append({
                    "index": idx,
                    "video_url": url,
                    "success": True,
                    "local_path": out_path,
                })
            except Exception as e:
                logger.warning(f"[视频剪辑] 视频 #{idx} 处理失败: {e}")
                edited_videos.append({
                    "index": idx,
                    "video_url": videos[idx].get("video_url", ""),
                    "success": False,
                    "error": str(e),
                })
            self._completed_count = idx + 1

        success_count = sum(1 for v in edited_videos if v.get("success"))

        # 4. 保存生成记录
        if success_count > 0 and self.context.run_id:
            try:
                async with new_async_session() as db:
                    success_items = [v for v in edited_videos if v.get("success")]
                    await integration.save_batch_generations(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        items=success_items,
                        gen_type="video",
                        user_id=self.context.user_id,
                    )
            except Exception as e:
                logger.warning(f"[视频剪辑] 保存生成记录失败: {e}")

        logger.info(
            f"[视频剪辑] 完成: 成功 {success_count}/{len(edited_videos)}, "
            f"operations={len(operations)}"
        )

        return {
            "videos": edited_videos,
            "total": len(edited_videos),
            "success_count": success_count,
            "failed_count": len(edited_videos) - success_count,
            "operations_applied": len(operations),
        }

    async def estimate_credits(self) -> int:
        """剪辑步骤不消耗外部 API 积分"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        if from_step:
            step_output = self.context.steps_output.get(from_step, {})
            count = len(step_output.get("videos", []))
        else:
            count = 1
        return max(count, 1) * 2  # 每个视频 2 积分（剪辑比调色稍重）

    async def get_progress(self) -> Dict[str, Any]:
        """返回剪辑进度"""
        total = getattr(self, "_total", 0)
        if total == 0:
            return {}
        phase = getattr(self, "_progress_phase", "")
        completed = getattr(self, "_completed_count", 0)
        phase_map = {
            "downloading": (0.0, 0.3, "下载视频片段"),
            "editing": (0.3, 1.0, "应用剪辑操作"),
        }
        if phase not in phase_map:
            return {}
        start, end, text = phase_map[phase]
        percent = round(start + (end - start) * (completed / total if total > 0 else 0), 3)
        return {
            "current": completed,
            "total": total,
            "percent": percent,
            "phase": phase,
            "phase_text": text,
        }

    # ---------- 内部方法 ----------

    async def _download_all_videos(self, videos: List[Dict[str, Any]]) -> List[str]:
        """下载所有视频到临时目录"""
        temp_dir = tempfile.mkdtemp(prefix="agnes_edit_")
        paths: List[str] = []
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for idx, video in enumerate(videos):
                url = video.get("video_url") or video.get("url", "")
                if not url:
                    paths.append("")
                    continue
                try:
                    out_path = os.path.join(temp_dir, f"src_{idx:03d}.mp4")
                    resp = await client.get(url, headers={"User-Agent": "Agnes-Platform"})
                    if resp.status_code == 200:
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        paths.append(out_path)
                    else:
                        logger.warning(f"[视频剪辑] 下载视频 #{idx} 失败: HTTP {resp.status_code}")
                        paths.append("")
                except Exception as e:
                    logger.warning(f"[视频剪辑] 下载视频 #{idx} 异常: {e}")
                    paths.append("")
                self._completed_count = idx + 1
        return paths

    async def _apply_operations(
        self,
        video_path: str,
        index: int,
        operations: List[Dict[str, Any]],
    ) -> str:
        """
        对单个视频应用剪辑操作列表

        策略：
        1. 先将 operations 归一化为"保留区间列表" keep_ranges
           - trim 操作：直接作为保留区间
           - cut 操作：从 [0, duration] 中扣除 cut 区间，剩余部分作为保留区间
        2. 对每个保留区间用 ffmpeg -ss + -t 提取（含 30ms 音频淡入淡出）
        3. 多段保留区间用 concat demuxer 拼接

        Returns:
            输出视频文件路径
        """
        # 1. 获取视频总时长
        duration = await self._get_video_duration(video_path)
        if duration <= 0:
            raise RuntimeError("无法获取视频时长")

        # 2. 计算"保留区间"列表
        keep_ranges = self._compute_keep_ranges(operations, duration)
        if not keep_ranges:
            raise RuntimeError("剪辑后无有效保留区间")

        logger.info(
            f"[视频剪辑] 视频 #{index} 保留区间: {keep_ranges} "
            f"(原时长 {duration:.2f}s → 保留 {sum(e-s for s,e in keep_ranges):.2f}s)"
        )

        run_id = self.context.run_id or "tmp"

        # 3. 提取每个保留区间
        segment_paths: List[str] = []
        temp_dir = tempfile.mkdtemp(prefix=f"agnes_edit_{run_id}_{index}_")
        for seg_idx, (start, end) in enumerate(keep_ranges):
            seg_duration = end - start
            if seg_duration <= 0.01:
                continue
            seg_path = os.path.join(temp_dir, f"seg_{seg_idx:03d}.mp4")
            await self._extract_segment(
                video_path, start, seg_duration, seg_path
            )
            segment_paths.append(seg_path)

        if not segment_paths:
            raise RuntimeError("无有效片段可拼接")

        # 4. 拼接所有片段
        out_path = os.path.join(_OUTPUT_BASE, f"edited_{run_id}_{index:03d}.mp4")
        if len(segment_paths) == 1:
            # 单段：直接重编码输出（已经是带音频淡入淡出的完整片段）
            await self._reencode(segment_paths[0], out_path)
        else:
            # 多段：用 concat demuxer 拼接
            await self._concat_segments(segment_paths, out_path)

        return out_path

    def _compute_keep_ranges(
        self,
        operations: List[Dict[str, Any]],
        duration: float,
    ) -> List[Tuple[float, float]]:
        """
        将操作列表归一化为"保留区间"列表

        - trim 操作：直接作为保留区间（多个 trim 取并集）
        - cut 操作：从 [0, duration] 中扣除 cut 区间

        混合使用时：先处理所有 trim（取并集），再在 trim 结果上应用 cut。
        如果只有 cut 操作，则初始区间为 [0, duration]。

        Returns:
            保留区间列表 [(start, end), ...]，按 start 升序，无重叠
        """
        trims: List[Tuple[float, float]] = []
        cuts: List[Tuple[float, float]] = []

        for op in operations:
            op_type = op.get("type")
            start = float(op.get("start", 0))
            end = float(op.get("end", 0))
            # 边界裁剪
            start = max(0.0, min(start, duration))
            end = max(0.0, min(end, duration))
            if end <= start:
                continue
            if op_type == "trim":
                trims.append((start, end))
            elif op_type == "cut":
                cuts.append((start, end))

        # 初始区间：如果有 trim，用 trim 的并集；否则用 [0, duration]
        if trims:
            keep = self._merge_ranges(trims)
        else:
            keep = [(0.0, duration)]

        # 应用 cut：从 keep 中扣除每个 cut 区间
        for cut_start, cut_end in cuts:
            keep = self._subtract_range(keep, cut_start, cut_end)

        return keep

    def _merge_ranges(self, ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """合并重叠/相邻的区间"""
        if not ranges:
            return []
        sorted_ranges = sorted(ranges, key=lambda r: r[0])
        merged: List[Tuple[float, float]] = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                # 重叠或相邻，合并
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _subtract_range(
        self,
        keep: List[Tuple[float, float]],
        cut_start: float,
        cut_end: float,
    ) -> List[Tuple[float, float]]:
        """从 keep 区间列表中扣除 [cut_start, cut_end]"""
        result: List[Tuple[float, float]] = []
        for start, end in keep:
            if cut_end <= start or cut_start >= end:
                # 无交集
                result.append((start, end))
                continue
            # 有交集，切分
            if cut_start > start:
                result.append((start, cut_start))
            if cut_end < end:
                result.append((cut_end, end))
        return result

    async def _extract_segment(
        self,
        source: str,
        start: float,
        duration: float,
        out_path: str,
    ) -> None:
        """
        提取单个片段（移植自 video-use render.py extract_segment）

        - -ss 在 -i 之前：快速精确 seek
        - 30ms 音频淡入淡出：避免切点爆音
        - libx264 fast CRF 20：与 video-use final 质量一致
        """
        fade_out_start = max(0.0, duration - _AUDIO_FADE_DURATION)
        af = (
            f"afade=t=in:st=0:d={_AUDIO_FADE_DURATION:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={_AUDIO_FADE_DURATION:.3f}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", source,
            "-t", f"{duration:.3f}",
            "-af", af,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            out_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[-500:]
            raise RuntimeError(f"ffmpeg 提取片段失败 (start={start}, dur={duration}): {err_text}")

    async def _reencode(self, src_path: str, out_path: str) -> None:
        """单段直接重编码输出（保证编码一致性）"""
        cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[-500:]
            raise RuntimeError(f"ffmpeg 重编码失败: {err_text}")

    async def _concat_segments(self, segment_paths: List[str], out_path: str) -> None:
        """
        拼接多个片段（concat demuxer）

        由于各片段已经是相同编码参数（libx264 fast CRF 20 + aac 192k），
        优先尝试 -c copy，失败时 fallback 到重编码。
        """
        run_id = self.context.run_id or "tmp"
        list_path = os.path.join(_OUTPUT_BASE, f"concat_edit_{run_id}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for p in segment_paths:
                escaped = p.replace("'", "\\'")
                f.write(f"file '{escaped}'\n")

        # 第一阶段：-c copy
        copy_ok = await self._try_concat_copy(list_path, out_path)
        if copy_ok:
            self._cleanup_file(list_path)
            return

        # 第二阶段：重编码
        logger.warning("[视频剪辑] concat copy 失败，改用重编码")
        reencode_ok = await self._try_concat_reencode(list_path, out_path)
        self._cleanup_file(list_path)
        if not reencode_ok:
            raise RuntimeError("视频拼接失败（copy 和 reencode 均失败）")

    async def _try_concat_copy(self, list_path: str, output_path: str) -> bool:
        """尝试 -c copy 拼接"""
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
                    f"[视频剪辑] concat copy 失败: {stderr.decode(errors='ignore')[:200]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.debug(f"[视频剪辑] concat copy 异常: {e}")
            return False

    async def _try_concat_reencode(self, list_path: str, output_path: str) -> bool:
        """重编码拼接"""
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
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
                    f"[视频剪辑] concat reencode 失败: {stderr.decode(errors='ignore')[:300]}"
                )
                return False
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.warning(f"[视频剪辑] concat reencode 异常: {e}")
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

    def _cleanup_file(self, path: str) -> None:
        """清理临时文件"""
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

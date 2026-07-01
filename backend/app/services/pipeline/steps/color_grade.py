# =====================================================
# 调色步骤执行器（移植自 video-use 项目 helpers/grade.py）
#
# 核心功能:
#   1. 对上游视频应用调色滤镜链（4 个预设 + 自定义滤镜）
#   2. 支持单视频或多视频批量处理
#   3. 可选叠加 30ms 音频淡入淡出，避免切点爆音
#
# 预设说明（来自 video-use）:
#   - subtle:          轻微清理，无可感色偏
#   - neutral_punch:   中性增艳，轻对比 + S 曲线
#   - warm_cinematic:  暖色电影感（创意向，默认不启用）
#   - none:            不调色（占位）
#
# 输入：
#   from_step 上游步骤产出的 videos 列表（每项含 video_url）
# 输出：
#   {
#     "videos": [{"index": 0, "video_url": "...", "success": True}, ...],
#     "total": N, "success_count": N, "failed_count": 0,
#     "grade_preset": "neutral_punch"
#   }
# =====================================================

import asyncio
import logging
import os
import tempfile
from typing import Dict, Any, List, Optional

import httpx

from app.core.database import new_async_session
from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor
from app.services.pipeline import integration

logger = logging.getLogger("agnes_platform.pipeline")

# 最终视频输出目录（与 ffmpeg_composite 共用，便于通过路由对外提供访问）
_OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "pipeline_outputs",
)
os.makedirs(_OUTPUT_BASE, exist_ok=True)

# ---------- 调色预设（移植自 video-use helpers/grade.py PRESETS）----------
# 每个预设是一段 ffmpeg -vf 滤镜链
GRADE_PRESETS: Dict[str, str] = {
    # 轻微清理：无可感色偏，作为安全底线
    "subtle": "eq=contrast=1.03:saturation=0.98",
    # 中性增艳：轻对比 + S 曲线，无色偏，推荐默认值
    "neutral_punch": (
        "eq=contrast=1.06:brightness=0.0:saturation=1.0,"
        "curves=master='0/0 0.25/0.23 0.75/0.77 1/1'"
    ),
    # 暖色电影感（创意向，默认不启用）：+12% 对比 + 压黑 -12% 饱和 + 暖阴影冷高光
    "warm_cinematic": (
        "eq=contrast=1.12:brightness=-0.02:saturation=0.88,"
        "colorbalance="
        "rs=0.02:gs=0.0:bs=-0.03:"
        "rm=0.04:gm=0.01:bm=-0.02:"
        "rh=0.08:gh=0.02:bh=-0.05,"
        "curves=master='0/0 0.25/0.22 0.75/0.78 1/1'"
    ),
    # 占位：不调色
    "none": "",
}


def resolve_grade_filter(grade_field: Optional[str]) -> str:
    """
    解析调色字段，返回 ffmpeg -vf 滤镜链字符串。

    支持三种输入：
    - 预设名（subtle/neutral_punch/warm_cinematic/none）：返回对应预设
    - 'auto'：降级为 neutral_punch（不实现 video-use 的逐帧分析，避免引入复杂依赖）
    - 自定义滤镜链（含 = 或 ,）：原样返回
    - 空/None：返回空字符串
    """
    if not grade_field:
        return ""
    if grade_field == "auto":
        # video-use 的 auto 模式依赖 signalstats 逐帧分析，这里简化为 neutral_punch
        return GRADE_PRESETS["neutral_punch"]
    if grade_field in GRADE_PRESETS:
        return GRADE_PRESETS[grade_field]
    # 含 = 或 , 视为原始滤镜链
    return grade_field


@register_step_executor
class ColorGradeExecutor(BaseStepExecutor):
    """
    调色步骤执行器

    对上游 video_batch 或 ffmpeg_composite 产出的视频应用调色滤镜链。
    支持 4 个内置预设（subtle/neutral_punch/warm_cinematic/none）和自定义滤镜链。
    """

    step_type = "color_grade"

    async def validate(self) -> None:
        """验证输入：必须指定 from_step，且 ffmpeg 可用"""
        config = self.config.get("config", {})
        if not config.get("from_step"):
            raise ValueError("color_grade 必须指定 from_step（上游视频步骤）")

        # 校验预设名（如果是预设名而非自定义滤镜）
        preset = config.get("preset") or config.get("grade") or "neutral_punch"
        if preset not in GRADE_PRESETS and preset != "auto":
            # 不是预设名也不是 auto，必须含 = 才算合法自定义滤镜链
            if "=" not in preset and "," not in preset:
                raise ValueError(
                    f"未知的调色预设: {preset}。"
                    f"可选: {', '.join(GRADE_PRESETS.keys())} / auto / 自定义滤镜链"
                )

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
        """执行调色处理"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        preset = config.get("preset") or config.get("grade") or "neutral_punch"
        # 是否叠加 30ms 音频淡入淡出（默认 True，避免切点爆音）
        with_audio_fade = config.get("with_audio_fade", True)

        grade_filter = resolve_grade_filter(preset)
        logger.info(
            f"[调色] 开始处理: step={self.step_key}, preset={preset}, "
            f"filter={grade_filter or '(none)'}, audio_fade={with_audio_fade}"
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

        # 3. 逐个应用调色滤镜
        self._progress_phase = "grading"
        self._completed_count = 0
        graded_videos: List[Dict[str, Any]] = []
        for idx, vpath in enumerate(video_paths):
            if not vpath:
                logger.warning(f"[调色] 跳过空视频 #{idx}")
                graded_videos.append({
                    "index": idx,
                    "video_url": videos[idx].get("video_url", ""),
                    "success": False,
                    "error": "下载失败",
                })
                continue

            try:
                out_path = await self._apply_grade(
                    vpath, idx, grade_filter, with_audio_fade
                )
                # 生成前端可访问的 URL
                filename = os.path.basename(out_path)
                url = f"/api/pipeline/outputs/{filename}"
                graded_videos.append({
                    "index": idx,
                    "video_url": url,
                    "success": True,
                    "local_path": out_path,
                })
            except Exception as e:
                logger.warning(f"[调色] 视频 #{idx} 处理失败: {e}")
                # 失败时降级使用原视频
                graded_videos.append({
                    "index": idx,
                    "video_url": videos[idx].get("video_url", ""),
                    "success": False,
                    "error": str(e),
                })
            self._completed_count = idx + 1

        success_count = sum(1 for v in graded_videos if v.get("success"))

        # 4. 保存生成记录
        if success_count > 0 and self.context.run_id:
            try:
                async with new_async_session() as db:
                    success_items = [v for v in graded_videos if v.get("success")]
                    await integration.save_batch_generations(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        items=success_items,
                        gen_type="video",
                        user_id=self.context.user_id,
                    )
            except Exception as e:
                logger.warning(f"[调色] 保存生成记录失败: {e}")

        logger.info(
            f"[调色] 完成: 成功 {success_count}/{len(graded_videos)}, preset={preset}"
        )

        return {
            "videos": graded_videos,
            "total": len(graded_videos),
            "success_count": success_count,
            "failed_count": len(graded_videos) - success_count,
            "grade_preset": preset,
        }

    async def estimate_credits(self) -> int:
        """调色步骤不消耗外部 API 积分，仅本地 ffmpeg 处理"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        if from_step:
            step_output = self.context.steps_output.get(from_step, {})
            count = len(step_output.get("videos", []))
        else:
            count = 1
        return max(count, 1) * 1  # 每个视频 1 积分（象征性）

    async def get_progress(self) -> Dict[str, Any]:
        """返回调色进度"""
        total = getattr(self, "_total", 0)
        if total == 0:
            return {}
        phase = getattr(self, "_progress_phase", "")
        completed = getattr(self, "_completed_count", 0)
        phase_map = {
            "downloading": (0.0, 0.3, "下载视频片段"),
            "grading": (0.3, 1.0, "应用调色滤镜"),
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
        temp_dir = tempfile.mkdtemp(prefix="agnes_grade_")
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
                        logger.warning(f"[调色] 下载视频 #{idx} 失败: HTTP {resp.status_code}")
                        paths.append("")
                except Exception as e:
                    logger.warning(f"[调色] 下载视频 #{idx} 异常: {e}")
                    paths.append("")
                self._completed_count = idx + 1
        return paths

    async def _apply_grade(
        self,
        video_path: str,
        index: int,
        grade_filter: str,
        with_audio_fade: bool,
    ) -> str:
        """
        对单个视频应用调色滤镜

        Args:
            video_path: 输入视频路径
            index: 视频序号（用于命名输出文件）
            grade_filter: ffmpeg -vf 滤镜链（为空则跳过调色，仅做音频淡入淡出）
            with_audio_fade: 是否叠加 30ms 音频淡入淡出

        Returns:
            输出视频文件路径
        """
        run_id = self.context.run_id or "tmp"
        out_path = os.path.join(_OUTPUT_BASE, f"graded_{run_id}_{index:03d}.mp4")

        # 获取视频时长（用于计算音频淡出起始时间）
        duration = await self._get_video_duration(video_path) if with_audio_fade else 0.0

        # 构建 -vf 滤镜链
        vf_parts: List[str] = []
        if grade_filter:
            vf_parts.append(grade_filter)
        vf_arg = ",".join(vf_parts) if vf_parts else None

        # 构建 -af 音频滤镜链（30ms 淡入淡出）
        af_arg: Optional[str] = None
        if with_audio_fade and duration > 0.06:
            fade_out_start = max(0.0, duration - 0.03)
            af_arg = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03"

        # 构建 ffmpeg 命令
        cmd: List[str] = ["ffmpeg", "-y", "-i", video_path]
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
        if af_arg:
            cmd.extend(["-af", af_arg])
        cmd.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out_path,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[-500:]
            raise RuntimeError(f"ffmpeg 调色失败: {err_text}")
        return out_path

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

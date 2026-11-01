# =====================================================
# 剪映草稿导出（JianYing Pro / CapCut 同构草稿格式）
#
# 依据实测格式规则（剪映可直接打开纯 JSON 草稿，打开后由剪映转存加密）独立实现：
# - 草稿目录 = draft_info.json + draft_meta_info.json（+ assets/ 素材），打包 zip 下载
# - 时间全部微秒、按工程帧率对齐（相邻片段共享切点）；图片素材时长用 3 小时占位
# - 每个文件登记 meta.draft_materials（group 0）+ material.local_material_id 关联
#   （缺关联剪映媒体面板不出素材）
# - 视频自带音频不重复建轨：音量写进视频片段（muted→0）；音频轨单独建 audio 轨
# - 字幕走剪映字幕轨（flag=1 + config.subtitle_taskinfo），白字黑边、随工程样式缩放
# - 转场统一「叠化」、效果器黑白/模糊按内置名称导出（name 解析，未生效可在剪映重选）；
#   运镜不导出；素材 path 为草稿内相对路径（解压到剪映草稿目录后打开）
# =====================================================

import asyncio
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

PHOTO_US = 10_800_000_000  # 图片在剪映里的时长占位：3 小时
PLATFORM = {"app_id": 3704, "app_source": "lv", "app_version": "5.9.0", "os": "windows"}

# 空草稿也列出的素材种类键（剪映读取时不强校验齐全性，缺省键会报错）
MATERIAL_KINDS = [
    "ai_translates", "audio_balances", "audio_effects", "audio_fades", "audio_track_indexes", "audios", "beats",
    "canvases", "chromas", "color_curves", "digital_humans", "drafts", "effects", "flowers", "green_screens",
    "handwrites", "hsl", "images", "log_color_wheels", "loudnesses", "manual_deformations", "masks",
    "material_animations", "material_colors", "multi_language_refs", "placeholders", "plugin_effects",
    "primary_color_wheels", "realtime_denoises", "shapes", "smart_crops", "smart_relights",
    "sound_channel_mappings", "speeds", "stickers", "tail_leaders", "text_templates", "texts", "time_marks",
    "transitions", "video_effects", "video_trackings", "videos", "vocal_beautifys", "vocal_separations",
    "filters",
]

TRANSITION_NAME = "叠化"  # crossfade/fade/wipe 统一（wipe 方向细节对不齐，叠化兜底）
FILTER_NAME = {"grayscale": "黑白", "blur": "模糊"}


def _hex32() -> str:
    return uuid.uuid4().hex


def _upper_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _us(seconds: float, fps: int) -> int:
    """秒 → 微秒（先按帧率取整到帧边界，相邻片段共享切点）"""
    return round(round(seconds * fps) * 1_000_000 / fps)


def _crop_default() -> dict:
    return {
        "upper_left_x": 0, "upper_left_y": 0, "upper_right_x": 1, "upper_right_y": 0,
        "lower_left_x": 0, "lower_left_y": 1, "lower_right_x": 1, "lower_right_y": 1,
    }


def _clip_settings(scale: float, x: float, y: float) -> dict:
    return {
        "alpha": 1, "flip": {"horizontal": False, "vertical": False}, "rotation": 0,
        "scale": {"x": scale, "y": scale}, "transform": {"x": x, "y": y},
    }


def _segment(**fields) -> dict:
    base = {
        "enable_adjust": True, "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_color_match_adjust": False, "enable_color_wheels": True, "enable_lut": True,
        "enable_smart_color_adjust": False, "last_nonzero_volume": 1, "reverse": False,
        "track_attribute": 0, "track_render_index": 0, "visible": True, "id": _hex32(),
        "common_keyframes": [], "keyframe_refs": [], "speed": 1, "volume": 1, "is_tone_modify": False,
    }
    base.update(fields)
    return base


def _hex_to_rgb01(color: str) -> list[float]:
    """#RRGGBB → [r,g,b] 0~1"""
    raw = (color or "#FFFFFF").lstrip("#")
    try:
        return [round(int(raw[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return [1.0, 1.0, 1.0]


def _full_frame(rect: dict | None) -> bool:
    return not rect or (float(rect.get("w", 1)) >= 1 and float(rect.get("h", 1)) >= 1)


def build_draft(document: dict, title: str, media: dict[int, dict], now_ms: int | None = None) -> tuple[dict, dict]:
    """document + 素材元数据 → (draft_info, draft_meta_info) 纯函数（黄金测试直测）。

    media: assetId → {path: 草稿内相对路径, kind: 'video'|'image'|'audio',
                      duration_us: int, width: int, height: int}
    """
    fps = int(document.get("timebase") or 30)
    canvas_w = int(document.get("width") or 1280)
    canvas_h = int(document.get("height") or 720)
    clips = [c for c in document.get("clips", []) if isinstance(c, dict)]

    materials: dict[str, list] = {k: [] for k in MATERIAL_KINDS}
    library: list[dict] = []
    material_of: dict[str, str] = {}

    def register_media(aid: int, metetype: str) -> str:
        """meta 素材库条目（一文件一条，同素材多片段复用）"""
        key = f"lib:{aid}"
        if key in material_of:
            return material_of[key]
        m = media[aid]
        lib_id = _upper_uuid()
        library.append({
            "ai_group_type": "", "create_time": -1,
            "duration": PHOTO_US if metetype == "photo" else m.get("duration_us", 0),
            "enter_from": 0, "extra_info": os.path.basename(m["path"]), "file_Path": m["path"],
            "height": m.get("height", 0), "id": lib_id, "import_time": -1, "import_time_ms": -1,
            "item_source": 1, "material_color_tag": "", "md5": "", "metetype": metetype,
            "roughcut_time_range": {"duration": -1, "start": -1},
            "sub_time_range": {"duration": -1, "start": -1}, "type": 0,
            "width": m.get("width", 0),
        })
        material_of[key] = lib_id
        return lib_id

    def media_material(aid: int, media_kind: str) -> str | None:
        """视频/图片/音频 material（一素材一 material）"""
        if aid not in media:
            return None
        key = f"{media_kind}:{aid}"
        if key in material_of:
            return material_of[key]
        mid = _hex32()
        m = media[aid]
        name = os.path.basename(m["path"])
        if media_kind == "audio":
            materials["audios"].append({
                "app_id": 0, "category_id": "", "category_name": "local", "check_flag": 3,
                "copyright_limit_type": "none", "duration": m.get("duration_us", 0), "effect_id": "",
                "formula_id": "", "id": mid, "local_material_id": register_media(aid, "music"),
                "music_id": mid, "name": name, "path": m["path"], "source_platform": 0,
                "type": "extract_music", "wave_points": [],
            })
        else:
            still = media_kind == "image"
            materials["videos"].append({
                "audio_fade": None, "category_id": "", "category_name": "local", "check_flag": 63487,
                "crop": _crop_default(), "crop_ratio": "free", "crop_scale": 1,
                "duration": PHOTO_US if still else m.get("duration_us", 0),
                "height": m.get("height", canvas_h), "width": m.get("width", canvas_w),
                "id": mid, "local_material_id": register_media(aid, "photo" if still else "video"),
                "material_id": mid, "material_name": name, "media_path": "", "path": m["path"],
                "type": "photo" if still else "video",
            })
        material_of[key] = mid
        return mid

    def speed_material(speed: float) -> str:
        sid = _hex32()
        materials["speeds"].append({"curve_speed": None, "id": sid, "mode": 0, "speed": speed, "type": "speed"})
        return sid

    def filter_material(effect_type: str) -> str | None:
        name = FILTER_NAME.get(effect_type)
        if not name:
            return None
        fid = _hex32()
        materials["filters"].append({
            "id": fid, "type": "filter", "name": name, "category_name": "滤镜", "category_id": "",
            "effect_id": "", "duration": 0, "resource_id": "", "platforms": [], "filter_mask": None,
        })
        return fid

    def transition_material(duration_us: int) -> str:
        tid = _hex32()
        materials["transitions"].append({
            "id": tid, "type": "transition", "name": TRANSITION_NAME, "category_name": "基础",
            "category_id": "", "effect_id": "", "duration": duration_us, "resource_id": "",
        })
        return tid

    def fade_material(fade_in_us: int, fade_out_us: int) -> str | None:
        if fade_in_us <= 0 and fade_out_us <= 0:
            return None
        fid = _hex32()
        materials["audio_fades"].append({
            "id": fid, "fade_in_duration": fade_in_us, "fade_out_duration": fade_out_us,
            "fade_type": 0, "type": "audio_fade",
        })
        return fid

    # —— 视频轨（order 小=底层=剪映主轨在前）——
    tracks: list[dict] = []
    render_index = 0
    video_tracks = sorted(
        (t for t in document.get("tracks", []) if isinstance(t, dict) and t.get("kind") == "video"),
        key=lambda t: int(t.get("order") or 0),
    )
    for track in video_tracks:
        segs_out: list[dict] = []
        prev_seg: dict | None = None
        prev_clip_id: str | None = None
        track_clips = sorted(
            (c for c in clips if c.get("trackId") == track.get("id")),
            key=lambda c: float(c.get("start") or 0),
        )
        for clip in track_clips:
            aid = clip.get("assetId")
            mid = media_material(aid, "image" if (aid in media and media[aid]["kind"] == "image") else "video") if isinstance(aid, int) else None
            if not mid:
                continue  # 素材缺失片段跳过（与渲染剔除语义一致）
            m = media[aid]
            props = clip.get("props") or {}
            speed = float(props.get("speed") or 1)
            start = float(clip.get("start") or 0)
            dur = float(clip.get("duration") or 0)
            target = {"start": _us(start, fps), "duration": _us(dur, fps)}
            if m["kind"] == "image":
                source = {"start": 0, "duration": target["duration"]}
                sw, sh = m.get("width", canvas_w), m.get("height", canvas_h)
                fit = min(canvas_w / sw, canvas_h / sh) if sw and sh else 1
                scale, x, y = 1.0, 0.0, 0.0  # 图片=整图适配（contain 基线）
            else:
                source = {"start": _us(float(clip.get("trimStart") or 0), fps),
                          "duration": _us(dur * speed, fps)}
                sw, sh = m.get("width", canvas_w), m.get("height", canvas_h)
                fit = min(canvas_w / sw, canvas_h / sh) if sw and sh else 1
                rect = props.get("rect")
                if rect and not _full_frame(rect):
                    # PIP：display 宽 = rect.w × 画布宽；中心偏移换半画布单位、y 向上
                    scale = round(float(rect["w"]) * canvas_w / (sw * fit), 6)
                    x = round(2 * (float(rect["x"]) + float(rect["w"]) / 2 - 0.5), 6)
                    y = round(-2 * (float(rect["y"]) + float(rect["h"]) / 2 - 0.5), 6)
                else:
                    scale, x, y = round(1 / fit, 6), 0.0, 0.0  # 全帧=cover（参考实测基线）
            refs = [speed_material(speed)]
            for e in props.get("effects") or []:
                fid = filter_material(str(e.get("type")))
                if fid:
                    refs.append(fid)
            seg = _segment(
                material_id=mid, target_timerange=target, source_timerange=source,
                visible=not (track.get("flags") or {}).get("hidden", False),
                volume=0 if props.get("muted") else min(max(float(props.get("volume") or 1), 0), 2),
                extra_material_refs=refs, clip=_clip_settings(scale, x, y),
                uniform_scale={"on": True, "value": 1},
                hdr_settings={"intensity": 1, "mode": 1, "nits": 1000}, render_index=render_index,
            )
            # 转场挂前一片段（extra_material_refs）
            if prev_seg is not None:
                for tr in track.get("transitions") or []:
                    if isinstance(tr, dict) and tr.get("afterClipId") == prev_clip_id:
                        refs = list(prev_seg["extra_material_refs"])
                        refs.append(transition_material(_us(float(tr.get("duration") or 0), fps)))
                        prev_seg["extra_material_refs"] = refs
                        break
            segs_out.append(seg)
            prev_seg = seg
            prev_clip_id = clip.get("id")
        if segs_out:
            tracks.append({
                "attribute": 0, "flag": 0, "id": _hex32(), "is_default_name": False,
                "name": str(track.get("id")), "type": "video", "segments": segs_out,
            })
            render_index += 1

    # —— 音频轨 ——
    audio_tracks = sorted(
        (t for t in document.get("tracks", []) if isinstance(t, dict) and t.get("kind") == "audio"),
        key=lambda t: int(t.get("order") or 0),
    )
    for track in audio_tracks:
        segs_out: list[dict] = []
        for clip in sorted(
            (c for c in clips if c.get("trackId") == track.get("id")),
            key=lambda c: float(c.get("start") or 0),
        ):
            aid = clip.get("assetId")
            mid = media_material(aid, "audio") if isinstance(aid, int) else None
            if not mid:
                continue
            props = clip.get("props") or {}
            speed = float(props.get("speed") or 1)
            refs = [speed_material(speed)]
            fade = fade_material(
                _us(float(props.get("fadeIn") or 0), fps), _us(float(props.get("fadeOut") or 0), fps),
            )
            if fade:
                refs.append(fade)
            volume = min(max(float(props.get("volume") or 1), 0), 2)
            segs_out.append(_segment(
                material_id=mid,
                target_timerange={"start": _us(float(clip.get("start") or 0), fps),
                                  "duration": _us(float(clip.get("duration") or 0), fps)},
                source_timerange={"start": _us(float(clip.get("trimStart") or 0), fps),
                                  "duration": _us(float(clip.get("duration") or 0) * speed, fps)},
                volume=volume, last_nonzero_volume=volume or 1,
                extra_material_refs=refs, clip=None, hdr_settings=None, render_index=render_index,
            ))
        if segs_out:
            tracks.append({
                "attribute": 1 if (track.get("flags") or {}).get("muted", False) else 0,
                "flag": 0, "id": _hex32(), "is_default_name": False,
                "name": str(track.get("id")), "type": "audio", "segments": segs_out,
            })
            render_index += 1

    # —— 字幕轨（flag=1，剪映原生字幕） ——
    style = document.get("subtitleStyle") or {}
    cues = sorted(
        (c for c in clips if isinstance(c, dict)
         and any(isinstance(t, dict) and t.get("kind") == "subtitle" and t.get("id") == c.get("trackId")
                 for t in document.get("tracks", []))),
        key=lambda c: float(c.get("start") or 0),
    )
    cues = [c for c in cues if str(c.get("text") or "").strip() and float(c.get("duration") or 0) > 0]
    subtitle_tasks: list[dict] = []
    if cues:
        language = "zh-CN"
        task = f"{_hex32()[:24]}_0_0"
        group = f"{language}_{now_ms or 0}"
        subtitle_tasks.append({
            "id": task, "type": 10, "language": language, "content": "", "remove_invalid_task_id": "",
            "ai_accurate_recognize_enable": False, "supplies_commit_id": "", "is_local_asr": False,
        })
        base_size = round(6 * float(style.get("size") or 48) / 48, 2)
        stroke = round(0.08 if style.get("outline", True) else 0, 3)
        rgb = _hex_to_rgb01(str(style.get("color") or "#FFFFFF"))
        text_y = {"bottom": -0.8, "center": 0.0, "top": 0.8}.get(str(style.get("position") or "bottom"), -0.8)
        segs_out: list[dict] = []
        for cue in cues:
            text = str(cue["text"]).strip()
            tid = _hex32()
            materials["texts"].append({
                "id": tid, "type": "subtitle", "add_type": 1, "recognize_task_id": task,
                "recognize_text": text, "language": language, "group_id": group,
                "words": {"start_time": [], "end_time": [], "text": []},
                "current_words": {"start_time": [], "end_time": [], "text": []},
                "subtitle_keywords": {"range": []}, "typesetting": 0, "alignment": 1,
                "letter_spacing": 0, "line_spacing": 0.02, "line_feed": 1, "line_max_width": 0.82,
                "force_apply_line_max_width": False, "check_flag": 15, "global_alpha": 1,
                "content": json.dumps({
                    "styles": [{
                        "fill": {"alpha": 1, "content": {"render_type": "solid", "solid": {"alpha": 1, "color": rgb}}},
                        "range": [0, len(text)], "size": base_size, "bold": False, "italic": False,
                        "underline": False,
                        "strokes": [{"content": {"render_type": "solid", "solid": {"alpha": 1, "color": [0, 0, 0]}}, "width": stroke}],
                    }],
                    "text": text,
                }, ensure_ascii=False),
            })
            start_us = _us(float(cue.get("start") or 0), fps)
            segs_out.append(_segment(
                material_id=tid,
                target_timerange={"start": start_us, "duration": _us(float(cue.get("duration") or 0), fps)},
                source_timerange=None, extra_material_refs=[],
                clip=_clip_settings(1, 0, text_y), uniform_scale={"on": True, "value": 1},
                render_index=render_index,
            ))
        tracks.append({
            "attribute": 0, "flag": 1, "id": _hex32(), "is_default_name": False,
            "name": "字幕", "type": "text", "segments": segs_out,
        })

    total_us = max(
        (_us(float(c.get("start") or 0) + float(c.get("duration") or 0), fps) for c in clips),
        default=0,
    )
    now = now_ms if now_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
    draft_id = _upper_uuid()
    info = {
        "canvas_config": {"width": canvas_w, "height": canvas_h, "ratio": "original"},
        "color_space": 0,
        "config": {
            "adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1, "export_range": None,
            "extract_audio_last_index": 1, "lyrics_recognition_id": "", "lyrics_sync": True,
            "lyrics_taskinfo": [], "maintrack_adsorb": False, "material_save_mode": 0,
            "multi_language_current": "none", "multi_language_list": [], "multi_language_main": "none",
            "multi_language_mode": "none", "original_sound_last_index": 1, "record_audio_last_index": 1,
            "sticker_max_index": 1, "subtitle_keywords_config": None, "subtitle_recognition_id": "",
            "subtitle_sync": True, "subtitle_taskinfo": subtitle_tasks if cues else [],
            "system_font_list": [], "video_mute": False, "zoom_info_params": None,
        },
        "cover": None, "create_time": 0, "duration": total_us, "extra_info": None, "fps": fps,
        "free_render_index_mode_on": False, "group_container": None, "id": draft_id,
        "keyframe_graph_list": [],
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [],
                      "stickers": [], "texts": [], "videos": []},
        "last_modified_platform": PLATFORM, "platform": PLATFORM, "materials": materials,
        "mutable_config": None, "name": title,
        "new_version": "110.0.0", "relationships": [], "render_index_track_mode_on": False,
        "retouch_cover": None, "source": "default", "static_cover_image_path": "", "time_marks": None,
        "tracks": tracks, "update_time": 0, "version": 360000,
    }
    meta = {
        "cloud_package_completed_time": "", "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False, "draft_cloud_materials": [],
        "draft_cloud_purchase_info": "", "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "", "draft_cover": "", "draft_deeplink_url": "",
        "draft_enterprise_info": {"draft_enterprise_extra": "", "draft_enterprise_id": "",
                                  "draft_enterprise_name": "", "enterprise_material": []},
        "draft_fold_path": title, "draft_id": draft_id, "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False, "draft_is_ai_translate": False, "draft_is_article_video_draft": False,
        "draft_is_from_deeplink": "false", "draft_is_invisible": False,
        "draft_materials": [{"type": t, "value": library if t == 0 else []} for t in (0, 1, 2, 3, 6, 7, 8)],
        "draft_materials_copied_info": [], "draft_name": title, "draft_new_version": "",
        "draft_removable_storage_device": "", "draft_root_path": "", "draft_segment_extra_info": [],
        "draft_type": "", "tm_draft_cloud_completed": "", "tm_draft_cloud_modified": 0,
        "tm_draft_create": now, "tm_draft_modified": now, "tm_draft_removed": 0, "tm_duration": total_us,
    }
    return info, meta


# =====================================================
# zip 组装（素材本地化 → 草稿 JSON → 打包；路由以 FileResponse 流式下发 + BackgroundTask 清理）
# =====================================================

def _safe_folder(title: str) -> str:
    keep = "".join(ch for ch in (title or "draft").strip() if ch not in '\\/:*?"<>|' and ord(ch) >= 32)
    return (keep or "draft")[:60]


async def _probe_media(path: str, kind: str, fps: int) -> dict:
    """ffprobe 宽高/时长（微秒帧对齐）；图片无时长、音频无宽高，按 0 兜底"""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_entries", "stream=width,height:format=duration", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    width = height = 0
    duration_us = 0
    try:
        data = json.loads(stdout.decode("utf-8", "replace"))
        for stream in data.get("streams") or []:
            if isinstance(stream.get("width"), int):
                width, height = stream["width"], stream.get("height", 0)
                break
        raw = (data.get("format") or {}).get("duration")
        if raw:
            duration_us = round(round(float(raw) * fps) * 1_000_000 / fps)
    except (ValueError, KeyError, TypeError):
        pass  # 探测失败宽高/时长 0，草稿仍可打开（剪映读文件自愈）
    return {"kind": kind, "width": width, "height": height, "duration_us": duration_us}


async def export_jianying_zip(db, project) -> tuple[str, str]:
    """剪辑工程 → 剪映草稿 zip。返回 (zip 临时路径, 草稿目录名)；临时目录清理由调用方负责。"""
    from fastapi import HTTPException
    from sqlalchemy.future import select

    from app.models.asset import Asset
    from app.services.editor.media_source import resolve_asset_local_file

    document = project.document or {}
    if not document.get("clips"):
        raise HTTPException(status_code=400, detail="时间线为空，没有可导出内容")
    fps = int(document.get("timebase") or 30)
    asset_ids = {
        c.get("assetId") for c in document.get("clips", [])
        if isinstance(c, dict) and isinstance(c.get("assetId"), int)
    }
    assets = {
        a.id: a
        for a in (
            await db.scalars(select(Asset).where(Asset.id.in_(asset_ids)))
        ).all()
        if a.user_id == project.user_id
    }

    folder = _safe_folder(project.title)
    tmp_root = tempfile.mkdtemp(prefix="jy_")
    try:
        draft_dir = Path(tmp_root) / folder
        assets_dir = draft_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        media: dict[int, dict] = {}
        for aid, asset in assets.items():
            local = await resolve_asset_local_file(asset, str(assets_dir))
            if not local:
                continue  # 素材不可用跳过（与渲染剔除语义一致）
            name = f"{aid}_{os.path.basename(local)}"
            staged = assets_dir / name
            if os.path.abspath(local) != os.path.abspath(str(staged)):
                shutil.copyfile(local, str(staged))
            kind = asset.kind if asset.kind in ("video", "image", "audio") else "video"
            media[aid] = {"path": f"assets/{name}", **await _probe_media(str(staged), kind, fps)}

        info, meta = build_draft(document, project.title, media)
        (draft_dir / "draft_info.json").write_text(
            json.dumps(info, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (draft_dir / "draft_meta_info.json").write_text(
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        zip_path = draft_dir.parent / f"{folder}.zip"
        # 草稿目录内容全部由本函数创建（两个 JSON + assets 平铺清单），无需目录遍历
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(draft_dir / "draft_info.json", f"{folder}/draft_info.json",
                     compress_type=zipfile.ZIP_DEFLATED)
            zf.write(draft_dir / "draft_meta_info.json", f"{folder}/draft_meta_info.json",
                     compress_type=zipfile.ZIP_DEFLATED)
            for name in sorted(os.listdir(assets_dir)):
                staged = assets_dir / name
                if staged.is_file():
                    zf.write(staged, f"{folder}/assets/{name}", compress_type=zipfile.ZIP_STORED)
        return str(zip_path), folder
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise

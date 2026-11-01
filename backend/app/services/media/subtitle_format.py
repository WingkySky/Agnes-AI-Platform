# =====================================================
# 字幕格式构建公共层（SRT / ASS，原 project/subtitle_service 纯格式函数转正）
# 供 ffmpeg 烧录与前端下载使用；字幕「生成」（LLM/whisper）仍在各业务域
# =====================================================


# =====================================================
# 默认字幕样式
# =====================================================
DEFAULT_SUBTITLE_STYLE = {
    "font_family": "Microsoft YaHei",
    "font_size": 48,
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_vertical": 60,
}


def format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_time(seconds: float) -> str:
    """ASS 时间格式 H:MM:SS.cc（百分秒）"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def build_srt(clips: list[dict]) -> str:
    """构建 SRT 格式字幕文本"""
    lines: list[str] = []
    for idx, clip in enumerate(clips, start=1):
        start = format_srt_time(clip["start_time"])
        end = format_srt_time(clip["start_time"] + clip["duration"])
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(clip["text"])
        lines.append("")  # 空行分隔
    return "\n".join(lines)


def build_ass(clips: list[dict], style: dict | None = None) -> str:
    """
    构建 ASS 格式字幕文件（含样式，供 ffmpeg subtitles 滤镜烧录）

    ASS 格式支持丰富的字幕样式（字体/颜色/位置/描边等），
    ffmpeg 的 subtitles 滤镜优先使用 ASS。
    """
    s = style or DEFAULT_SUBTITLE_STYLE

    # 颜色转换：#RRGGBB → ASS 的 &H00BBGGRR（BGR 倒序）
    def to_ass_color(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}".upper()

    primary_color = to_ass_color(s.get("font_color", "#FFFFFF"))
    outline_color = to_ass_color(s.get("outline_color", "#000000"))
    font_name = s.get("font_family", "Microsoft YaHei")
    font_size = int(s.get("font_size", 48))
    outline_width = int(s.get("outline_width", 2))
    # 位置：bottom→2 (默认), top→8, center→5
    alignment = {"bottom": 2, "top": 8, "center": 5}.get(s.get("position", "bottom"), 2)
    margin_v = int(s.get("margin_vertical", 60))
    # PlayRes=实际视频分辨率（\pos 逐 cue 坐标空间；字幕尺寸随视频分辨率正确缩放）
    play_w = max(2, int(s.get("width") or 1280))
    play_h = max(2, int(s.get("height") or 720))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline_width},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for clip in clips:
        start = format_ass_time(clip["start_time"])
        end = format_ass_time(clip["start_time"] + clip["duration"])
        # 转义 ASS 特殊字符
        text = clip["text"].replace("\n", "\\N")
        # 逐 cue 样式覆盖（inline override tags 与全局 Default 样式叠加；缺键继承）
        override = ""
        style = clip.get("style")
        if isinstance(style, dict):
            if isinstance(style.get("font"), str) and style["font"].strip():
                # \fn 字体名：剥掉会破坏 ASS override 块的字符
                safe_font = str(style["font"]).replace("{", "").replace("}", "").replace("\\", "").strip()
                if safe_font:
                    override += "{\\fn" + safe_font + "}"
            if isinstance(style.get("color"), str) and len(style["color"]) == 7:
                override += f"{{\\1c{to_ass_color(style['color'])}}}"
            if isinstance(style.get("size"), (int, float)):
                override += "{\\fs" + str(int(style["size"])) + "}"
            # 自由位置（预览拖拽产物）：x/y 为归一化中心 → \an5\pos(x*W, y*H) 覆盖预设位
            free_pos = isinstance(style.get("x"), (int, float)) and isinstance(style.get("y"), (int, float))
            if free_pos:
                px = round(max(0.0, min(1.0, float(style["x"]))) * play_w, 2)
                py = round(max(0.0, min(1.0, float(style["y"]))) * play_h, 2)
                override += f"{{\\an5\\pos({px},{py})}}"  # 自由位=中心锚；跳过 position \an 防覆盖
            if style.get("position") in ("bottom", "center", "top") and not free_pos:
                override += "{\\an" + {"bottom": "2", "center": "5", "top": "8"}[style["position"]] + "}"
        # 整条淡变（毫秒）；未配置时不加覆盖块，输出与旧版一致
        fi = float(clip.get("fade_in") or 0)
        fo = float(clip.get("fade_out") or 0)
        fade = f"{{\\fad({round(fi * 1000)},{round(fo * 1000)})}}" if fi > 0 or fo > 0 else ""
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{override}{fade}{text}")

    return header + "\n".join(events) + "\n"

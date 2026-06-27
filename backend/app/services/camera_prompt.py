# =====================================================
# 摄像机参数 Prompt 拼接函数
# 将摄像机参数字典转为自然语言描述，
# 追加到图片/视频生成 prompt 末尾。
#
# 拼接规则遵循 Phase 1 开发文档 §6.1：
#   {原始prompt}。摄像机采用{camera_model}，{focal_length}焦段，
#   光圈{aperture}，{depth_of_field}景深，快门{shutter_speed}，
#   快门角度{shutter_angle}°。运镜采用{camera_movement}方式，
#   {camera_angle}视角，画幅{aspect_ratio}，{visual_style}画面风格。
#
# 仅拼接非空字段；若所有字段均为空则返回空字符串。
# =====================================================


def build_camera_prompt_suffix(camera_params: dict) -> str:
    """
    将摄像机参数字典拼接为自然语言描述字符串。

    参数格式示例:
        {
            "enabled": true,
            "camera_model": "Sony FX3",
            "focal_length": "85mm",
            "aperture": "f/2.8",
            "depth_of_field": "浅景深",
            "shutter_speed": "1/500",
            "shutter_angle": 180,
            "camera_movement": "跟",
            "camera_angle": "平视",
            "aspect_ratio": "16:9",
            "visual_style": "暖色调胶片风格",
        }

    返回格式（追加到原始 prompt 末尾）:
        "。摄像机采用 Sony FX3，85mm 焦段，光圈 f/2.8，浅景深 景深，快门 1/500，
         快门角度 180°。运镜采用 跟 方式，平视 视角，画幅 16:9，暖色调胶片风格 画面风格。"

    - camera_params.enabled=False 时返回空字符串
    - 仅拼接非空参数，未填写的字段不出现
    - 所有字段为空时返回空字符串
    """
    if not camera_params:
        return ""

    # 若显式禁用，则不拼接
    if camera_params.get("enabled") is False:
        return ""

    # 字段 → 中文模板映射（顺序与 Phase 1 文档 §6.1 一致）
    mapping = {
        "camera_model": "摄像机采用{}",
        "focal_length": "{}焦段",
        "aperture": "光圈{}",
        "depth_of_field": "{}景深",
        "shutter_speed": "快门{}",
        "shutter_angle": "快门角度{}°",
        "camera_movement": "运镜采用{}方式",
        "camera_angle": "{}视角",
        "aspect_ratio": "画幅{}",
        "visual_style": "{}画面风格",
    }

    parts = []
    for key, template in mapping.items():
        value = camera_params.get(key)
        # 过滤 None / 空字符串 / 空数值
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        parts.append(template.format(value))

    if not parts:
        return ""

    # 中文自然语言拼接：以句号开头，逗号分隔，句号结尾
    return "。" + "，".join(parts) + "。"

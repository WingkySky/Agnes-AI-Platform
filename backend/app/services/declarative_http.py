# =====================================================
# 声明式 HTTP 渠道公共助手（纯函数，无 app 内依赖）
# 模板渲染（占位符 + JSON 转义）与点路径提取，
# 供 declarative_client 与 schemas/providers 校验共用。
#
# 渲染规则：str → JSON 转义内文（json.dumps(v)[1:-1]，模板中占位符自带引号）；
#           int/float → str(v)；list/dict → json.dumps(v)（模板中占位符不带引号）。
# 点路径：`data.0.url` 按段遍历（数字段=数组下标）；空串 → None。
# =====================================================

import json
from typing import Any


def render_template(template: str, values: dict[str, Any]) -> str:
    """把 {{placeholder}} 替换为渲染值；未知占位符原样保留（便于排查漏填）"""
    out = template or ""
    for key, value in values.items():
        token = "{{" + key + "}}"
        if token not in out:
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        elif value is None:
            rendered = ""
        else:
            rendered = json.dumps(str(value), ensure_ascii=False)[1:-1]
        out = out.replace(token, rendered)
    return out


def extract_path(payload: Any, path: str) -> Any:
    """按 `data.0.url` 点路径取值；空路径返回 None；中途缺失返回 None"""
    if not path:
        return None
    current = payload
    for segment in str(path).split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def sample_template_values(kind: str) -> dict[str, Any]:
    """保存校验用的样例占位值（与客户端实际渲染的字段集保持一致）"""
    if kind == "image_create":
        return {
            "prompt": "样例提示词",
            "model": "sample-model",
            "size": "1024x1024",
            "image": "https://example.com/ref.png",
            "images": ["https://example.com/ref.png"],
        }
    if kind == "video_create":
        return {
            "prompt": "样例提示词",
            "model": "sample-model",
            "width": 1280,
            "height": 720,
            "seconds": 5,
            "aspect_ratio": "16:9",
            "negative_prompt": "",
            "image": "https://example.com/ref.png",
            "images": ["https://example.com/ref.png"],
        }
    # video_poll / models_endpoint 路径占位
    return {"task_id": "sample-task-id"}


def render_and_parse_body(template: str, values: dict[str, Any]) -> dict | list:
    """渲染请求体模板并解析；非法 JSON 抛 ValueError（文案可直接透出给管理员）"""
    rendered = render_template(template, values)
    try:
        parsed = json.loads(rendered)
    except json.JSONDecodeError as e:
        raise ValueError(f"请求体模板渲染后不是合法 JSON：{e}（渲染结果前 200 字符：{rendered[:200]}）")
    if not isinstance(parsed, (dict, list)):
        raise ValueError("请求体模板渲染后必须是 JSON 对象或数组")
    return parsed

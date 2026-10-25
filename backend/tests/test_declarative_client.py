# =====================================================
# 声明式 HTTP 渠道测试（M1）
# 模板渲染（特殊字符转义/数字/数组/未知占位符保留）、点路径提取、
# DeclarativeHttpClient 契约（图片映射/视频两段式/轮询状态机/list_models 三模式/
# 非 2xx 翻译/网络异常 error_kind/重试）、HttpConfigModel 校验、API 保存与 test-http
# =====================================================

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.schemas.providers import HttpConfigModel
from app.services import provider_registry as pr_module
from app.services.declarative_client import DeclarativeHttpClient
from app.services.declarative_http import (
    extract_path,
    render_and_parse_body,
    render_template,
)

# ---------- 纯函数 ----------

def test_render_template_escapes_special_chars():
    rendered = render_template('{"p": "{{prompt}}"}', {"prompt": '他说"你好"\\换行'})
    assert json.loads(rendered)["p"] == '他说"你好"\\换行'


def test_render_template_numbers_and_arrays():
    rendered = render_template('{"n": {{width}}, "arr": {{images}}, "s": "{{model}}"}',
                               {"width": 1280, "images": ["http://a.png", "http://b.png"], "model": "m1"})
    parsed = json.loads(rendered)
    assert parsed == {"n": 1280, "arr": ["http://a.png", "http://b.png"], "s": "m1"}


def test_render_template_unknown_placeholder_preserved():
    assert render_template("{{known}} {{unknown}}", {"known": "v"}) == "v {{unknown}}"


def test_extract_path_dotted_and_missing():
    payload = {"data": [{"url": "u1", "meta": {"w": 720}}]}
    assert extract_path(payload, "data.0.url") == "u1"
    assert extract_path(payload, "data.0.meta.w") == 720
    assert extract_path(payload, "data.1.url") is None
    assert extract_path(payload, "") is None
    assert extract_path(payload, "data.x.url") is None


def test_render_and_parse_body_rejects_invalid_json():
    # 模板本身结构损坏（值会被 JSON 转义，坏不到 JSON；模板坏才会）
    with pytest.raises(ValueError, match="合法 JSON"):
        render_and_parse_body('{"p": "{{prompt}}"} xx', {"prompt": "ok"})
    with pytest.raises(ValueError, match="合法 JSON"):
        render_and_parse_body('{"p": {{prompt}}}', {"prompt": "ok"})  # 字符串值填进无引号占位
    assert render_and_parse_body('{"p": "{{prompt}}"}', {"prompt": "ok"}) == {"p": "ok"}


# ---------- HttpConfigModel 校验 ----------

def _minimal_config(**overrides):
    base = {
        "models_mode": "static",
        "static_models": [{"id": "m1"}],
        "image_create": {"path": "/img", "body": '{"prompt": "{{prompt}}"}', "url_path": "data.0.url"},
    }
    base.update(overrides)
    return base


def test_config_valid_minimal():
    cfg = HttpConfigModel(**_minimal_config())
    assert cfg.image_create.url_path == "data.0.url"


def test_config_rejects_bad_status_map_value():
    with pytest.raises((ValueError, Exception)):
        HttpConfigModel(**_minimal_config(
            video_create={"path": "/v", "body": "{}", "task_id_path": "id"},
            video_poll={"path": "/p", "status_path": "s", "status_map": {"DONE": "done_ok"}},
        ))


def test_config_requires_video_create_and_poll_together():
    with pytest.raises((ValueError, Exception)):
        HttpConfigModel(**_minimal_config(
            video_poll={"path": "/p", "status_path": "s", "status_map": {"X": "processing"}},
        ))


def test_config_rejects_unknown_keys():
    with pytest.raises((ValueError, Exception)):
        HttpConfigModel(**_minimal_config(image_create={
            "path": "/img", "body": "{}", "url_path": "", "typo_field": 1,
        }))


def test_config_requires_at_least_one_action():
    with pytest.raises((ValueError, Exception)):
        HttpConfigModel(**{"models_mode": "static", "static_models": [{"id": "m"}]})


# ---------- DeclarativeHttpClient（httpx.MockTransport） ----------

def _client_with(handler, config: dict) -> DeclarativeHttpClient:
    dc = DeclarativeHttpClient("http://upstream.test/v1", "sk-test", config)
    dc.provider_id = 9
    dc.provider_name = "声明式测试渠道"
    dc._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return dc


IMAGE_CONFIG = {
    "models_mode": "static",
    "static_models": [{"id": "smoke-model", "type": "image"}],
    "image_create": {
        "path": "/images/generations", "method": "POST",
        "body": '{"model": "{{model}}", "prompt": "{{prompt}}", "size": "{{size}}"}',
        "url_path": "data.0.url", "b64_path": "data.0.b64_json",
    },
}

VIDEO_CONFIG = {
    "models_mode": "openai",
    "video_create": {
        "path": "/video/create", "method": "POST",
        "body": '{"prompt": "{{prompt}}", "model": "{{model}}", "width": {{width}}}',
        "task_id_path": "data.task_id",
    },
    "video_poll": {
        "path": "/video/status?task_id={{task_id}}", "method": "GET",
        "status_path": "data.status",
        "status_map": {"SUCCESS": "success", "RUNNING": "processing", "FAILED": "failed"},
        "video_url_path": "data.video_url", "progress_path": "data.progress", "error_path": "message",
    },
}


@pytest.mark.asyncio
async def test_create_image_maps_response(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"data": [{"url": "http://cdn/x.png"}]})

    dc = _client_with(handler, IMAGE_CONFIG)
    result = await dc.create_image(prompt='猫"与"狗', model="smoke-model", size="1024x1024")
    await dc.shutdown()
    assert result == {"data": [{"url": "http://cdn/x.png"}]}
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {"model": "smoke-model", "prompt": '猫"与"狗', "size": "1024x1024"}


@pytest.mark.asyncio
async def test_create_image_missing_mapping_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": 1})

    dc = _client_with(handler, IMAGE_CONFIG)
    with pytest.raises(Exception, match="未找到图片数据"):
        await dc.create_image(prompt="p", model="m")
    await dc.shutdown()


@pytest.mark.asyncio
async def test_non_2xx_raises_upstream_error_with_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "参数不合法"}})

    dc = _client_with(handler, IMAGE_CONFIG)
    from app.services.agnes_client import UpstreamError
    with pytest.raises(UpstreamError) as info:
        await dc.create_image(prompt="p", model="m")
    await dc.shutdown()
    assert info.value.status_code == 400
    assert "参数不合法" in str(info.value)


@pytest.mark.asyncio
async def test_network_error_kind():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    dc = _client_with(handler, IMAGE_CONFIG)
    from app.services.agnes_client import UpstreamError
    with pytest.raises(UpstreamError) as info:
        await dc.create_image(prompt="p", model="m")
    await dc.shutdown()
    assert info.value.error_kind == "network"


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"data": [{"b64_json": "aGk="}]})

    dc = _client_with(handler, IMAGE_CONFIG)
    result = await dc.create_image(prompt="p", model="m")
    await dc.shutdown()
    assert calls["n"] == 3
    assert result == {"data": [{"b64_json": "aGk="}]}


@pytest.mark.asyncio
async def test_video_create_and_poll_state_machine():
    poll_results = [
        {"data": {"status": "RUNNING", "progress": "42%"}},
        {"data": {"status": "WEIRD_UNKNOWN"}},          # 未命中 status_map → processing
        {"data": {"status": "SUCCESS", "video_url": "http://cdn/v.mp4"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/video/create"):
            return httpx.Response(200, json={"data": {"task_id": "t-1"}})
        return httpx.Response(200, json=poll_results.pop(0))

    dc = _client_with(handler, VIDEO_CONFIG)
    created = await dc.create_video_task(prompt="p", model="v1", width=1280, height=720)
    assert created["task_id"] == "t-1" and created["id"] == "t-1"

    first = await dc.poll_video_status(task_id="t-1", model_name="v1")
    second = await dc.poll_video_status(video_id=None, task_id="t-1", model_name="v1")
    third = await dc.poll_video_status(task_id="t-1", model_name="v1")
    await dc.shutdown()
    assert first["status"] == "processing" and first["progress"] == 42
    assert second["status"] == "processing"
    assert third["status"] == "success" and third["video_url"] == "http://cdn/v.mp4" and third["progress"] == 100


@pytest.mark.asyncio
async def test_video_success_without_valid_url_marks_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"status": "SUCCESS", "video_url": "not-a-url"}})

    dc = _client_with(handler, VIDEO_CONFIG)
    result = await dc.poll_video_status(task_id="t-1", model_name="v1")
    await dc.shutdown()
    assert result["status"] == "failed" and "视频地址" in (result["error"] or "")


@pytest.mark.asyncio
async def test_video_create_missing_task_id_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    dc = _client_with(handler, VIDEO_CONFIG)
    with pytest.raises(Exception, match="未找到任务 ID"):
        await dc.create_video_task(prompt="p", model="v1")
    await dc.shutdown()


@pytest.mark.asyncio
async def test_list_models_three_modes():
    static_dc = _client_with(lambda r: httpx.Response(500), IMAGE_CONFIG)
    static_models = await static_dc.list_models()
    await static_dc.shutdown()
    assert static_models == [{"id": "smoke-model", "type": "image"}]

    def openai_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "oa-1"}, {"id": "oa-2"}]})

    openai_dc = _client_with(openai_handler, VIDEO_CONFIG)
    openai_models = await openai_dc.list_models()
    await openai_dc.shutdown()
    assert [m["id"] for m in openai_models] == ["oa-1", "oa-2"]

    custom_cfg = {
        "models_mode": "custom",
        "models_endpoint": {"path": "/list", "method": "GET"},
        "image_create": {"path": "/img", "body": "{}", "url_path": "u"},
    }
    custom_dc = _client_with(lambda r: httpx.Response(200, json=["bare-1", {"id": "bare-2"}]), custom_cfg)
    custom_models = await custom_dc.list_models()
    await custom_dc.shutdown()
    assert [m["id"] for m in custom_models] == ["bare-1", "bare-2"]


# ---------- API 层（保存 + test-http） ----------

def _bind(session):
    @asynccontextmanager
    async def _fake():
        yield session
    return _fake


@pytest_asyncio.fixture
async def admin_client(memory_db, monkeypatch):
    fake = _bind(memory_db)
    monkeypatch.setattr(pr_module, "new_async_session", fake)
    user = User(username="adminx", email="adminx@example.com", password_hash="x",
                role="admin", is_admin=True, credits=0)
    memory_db.add(user)
    await memory_db.commit()
    await memory_db.refresh(user)

    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_provider_with_http_config_roundtrip(admin_client):
    resp = await admin_client.post("/api/providers", json={
        "name": "声明式冒烟", "provider_type": "http_custom",
        "base_url": "http://127.0.0.1:9910/v1", "api_key": "key-1",
        "http_config": IMAGE_CONFIG,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["provider_type"] == "http_custom"
    assert data["http_config"]["image_create"]["url_path"] == "data.0.url"
    assert data["http_config"]["static_models"][0]["id"] == "smoke-model"


@pytest.mark.asyncio
async def test_create_provider_invalid_body_template_400(admin_client):
    resp = await admin_client.post("/api/providers", json={
        "name": "坏模板", "provider_type": "http_custom",
        "base_url": "http://127.0.0.1:9910/v1", "api_key": "key-1",
        "http_config": _minimal_config(image_create={
            "path": "/img", "body": '{"p": "{{prompt}}" xx}', "url_path": "u",
        }),
    })
    assert resp.status_code == 400
    assert "模板校验失败" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_provider_invalid_http_config_422(admin_client):
    resp = await admin_client.post("/api/providers", json={
        "name": "坏配置", "provider_type": "http_custom",
        "base_url": "http://127.0.0.1:9910/v1", "api_key": "key-1",
        "http_config": {"models_mode": "what"},
    })
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_test_http_endpoint_static_mode(admin_client):
    create = await admin_client.post("/api/providers", json={
        "name": "静态目录渠道", "provider_type": "http_custom",
        "base_url": "http://127.0.0.1:9910/v1", "api_key": "key-1",
        "http_config": IMAGE_CONFIG,
    })
    pid = create.json()["data"]["id"]
    resp = await admin_client.post(f"/api/providers/{pid}/test-http")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is True and data["mode"] == "static" and data["count"] == 1


@pytest.mark.asyncio
async def test_test_http_endpoint_non_declarative_400(admin_client):
    create = await admin_client.post("/api/providers", json={
        "name": "普通渠道", "provider_type": "openai",
        "base_url": "http://127.0.0.1:9910/v1", "api_key": "key-1",
    })
    pid = create.json()["data"]["id"]
    resp = await admin_client.post(f"/api/providers/{pid}/test-http")
    assert resp.status_code == 400

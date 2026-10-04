# =====================================================
# 提示词优化端点测试（POST /api/prompts/optimize）
# 三态锁死：未登录 401 / 空提示词与非法枚举 400 / 正常 200
# service 层 mock（call_llm 不出网）
# =====================================================

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_db
from app.main import app
from app.services import prompt_optimize_service as svc

pytestmark = pytest.mark.asyncio

OPTIMIZE_URL = "/api/prompts/optimize"

_FAKE_RESULT = {
    "positive": "一位穿红裙的少女站在樱花树下",
    "negative": "模糊、低分辨率",
    "changes": ["补充了主体与环境"],
    "assumptions": [],
    "variants": [{"label": "电影感", "prompt": "电影感的樱花树下红裙少女"}],
}


@pytest_asyncio.fixture
async def anon_client(memory_db):
    """不带鉴权头的 ASGI client（401 三态用）"""
    async def _override_db():
        yield memory_db

    app.dependency_overrides[get_async_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_optimize_requires_auth(anon_client):
    resp = await anon_client.post(OPTIMIZE_URL, json={"prompt": "少女", "mode": "refine"})
    assert resp.status_code == 401


async def test_optimize_empty_prompt_400(auth_client):
    resp = await auth_client.post(OPTIMIZE_URL, json={"prompt": "   "})
    assert resp.status_code == 400


async def test_optimize_invalid_mode_400(auth_client):
    resp = await auth_client.post(OPTIMIZE_URL, json={"prompt": "少女", "mode": "bogus"})
    assert resp.status_code == 400


async def test_optimize_invalid_target_400(auth_client):
    resp = await auth_client.post(OPTIMIZE_URL, json={"prompt": "少女", "target": "audio"})
    assert resp.status_code == 400


async def test_optimize_success_200(auth_client, monkeypatch):
    async def _fake_optimize(**kwargs):
        assert kwargs["prompt"] == "少女"
        assert kwargs["mode"] == "expand"
        assert kwargs["model_id"] == "seedream-4.0"
        assert kwargs["reference_names"] == ["人物.png"]
        return dict(_FAKE_RESULT)

    monkeypatch.setattr(svc, "optimize_prompt", _fake_optimize)
    resp = await auth_client.post(OPTIMIZE_URL, json={
        "prompt": "少女",
        "mode": "expand",
        "target": "image",
        "context": {"model_id": "seedream-4.0", "reference_asset_names": ["人物.png"]},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["positive"] == _FAKE_RESULT["positive"]
    assert len(body["data"]["variants"]) == 1


async def test_optimize_llm_failure_maps_502(auth_client, monkeypatch):
    async def _fail(**kwargs):
        raise RuntimeError("LLM 返回为空")

    monkeypatch.setattr(svc, "optimize_prompt", _fail)
    resp = await auth_client.post(OPTIMIZE_URL, json={"prompt": "少女"})
    assert resp.status_code == 502
    assert "LLM" in resp.json()["detail"] or "优化" in resp.json()["detail"]


# =====================================================
# 输出语言硬规则（钉死防中英摇摆）
# =====================================================

def test_language_rule_chinese_input_pins_simplified_chinese():
    from app.services.prompt_optimize_service import _build_prompt

    prompt = _build_prompt("一只小猫", "refine", "image", "", [])
    assert "简体中文" in prompt
    assert "禁止输出英文提示词" in prompt


def test_language_rule_english_input_follows_input():
    from app.services.prompt_optimize_service import _build_prompt

    prompt = _build_prompt("a cute kitten", "refine", "image", "", [])
    assert "简体中文" not in prompt
    assert "与用户提示词保持一致" in prompt

# =====================================================
# SPA 同源托管测试（main.py register_spa_fallback）
# 用临时 dist 在独立 FastAPI app 上验证：根路径 HTML、history 路由 fallback、
# dist 静态文件直返、/api 未知路径 404 不被吞、路径穿越不泄露文件
# =====================================================

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import register_spa_fallback

pytestmark = pytest.mark.asyncio


@pytest.fixture
def spa_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa-index</html>", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"fake-ico")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


@pytest.fixture
def spa_app(spa_dist: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def api_health():
        return {"ok": True}

    assert register_spa_fallback(app, str(spa_dist)) is True
    return app


@pytest_asyncio.fixture
async def spa_client(spa_app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=spa_app), base_url="http://test") as client:
        yield client


async def test_root_serves_index(spa_client: AsyncClient):
    resp = await spa_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "spa-index" in resp.text


async def test_unknown_path_falls_back_to_index(spa_client: AsyncClient):
    resp = await spa_client.get("/canvas/some/deep/link")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "spa-index" in resp.text


async def test_dist_static_file_served(spa_client: AsyncClient):
    resp = await spa_client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log(1)" in resp.text
    resp = await spa_client.get("/favicon.ico")
    assert resp.status_code == 200


async def test_api_unknown_path_not_swallowed(spa_client: AsyncClient):
    resp = await spa_client.get("/api/missing")
    assert resp.status_code == 404


async def test_path_traversal_not_leaking(spa_dist: Path, spa_client: AsyncClient):
    secret = spa_dist.parent / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    resp = await spa_client.get("/../secret.txt")
    assert "top-secret" not in resp.text


def test_register_skipped_without_dist(tmp_path: Path):
    app = FastAPI()
    assert register_spa_fallback(app, str(tmp_path / "no-dist")) is False

from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from starlette import status

from app.core.errors import register_exception_handlers
from app.main import _default_static_dir, create_app, mount_static_frontend


@pytest.mark.asyncio
async def test_static_frontend_serves_index_asset_and_spa_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>AgentLens</html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('agentlens');", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    mount_static_frontend(app, static_dir=static_dir)
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        index_response = await client.get("/")
        explicit_index_response = await client.get("/index.html")
        asset_response = await client.get("/assets/app.js")
        fallback_response = await client.get("/trajectory/123")

    assert index_response.status_code == status.HTTP_200_OK
    assert index_response.text == "<html>AgentLens</html>"
    assert index_response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert explicit_index_response.status_code == status.HTTP_200_OK
    assert explicit_index_response.headers["cache-control"] == (
        "no-cache, no-store, must-revalidate"
    )
    assert asset_response.status_code == status.HTTP_200_OK
    assert asset_response.text == "console.log('agentlens');"
    assert fallback_response.status_code == status.HTTP_200_OK
    assert fallback_response.text == "<html>AgentLens</html>"
    assert fallback_response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


@pytest.mark.asyncio
async def test_static_frontend_does_not_fallback_for_unknown_api_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>AgentLens</html>", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    register_exception_handlers(app)
    mount_static_frontend(app, static_dir=static_dir)
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"].startswith("application/json")
    assert "<html" not in response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_default_static_dir_ignores_incomplete_cwd_static(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd_static_dir = tmp_path / "static"
    cwd_static_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    default_static_dir = _default_static_dir()

    assert default_static_dir != cwd_static_dir
    assert (default_static_dir / "index.html").is_file()


@pytest.mark.asyncio
async def test_openapi_schema_uses_api_prefix_as_server() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/openapi.json")

    assert response.status_code == status.HTTP_200_OK
    payload: dict[str, Any] = response.json()
    assert payload["servers"] == [{"url": "/api/v1"}]
    assert "/health" in payload["paths"]
    assert "/api/v1/health" not in payload["paths"]

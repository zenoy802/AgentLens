from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from starlette import status

from app.main import create_app


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
    app = create_app()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        index_response = await client.get("/")
        asset_response = await client.get("/assets/app.js")
        fallback_response = await client.get("/trajectory/123")

    assert index_response.status_code == status.HTTP_200_OK
    assert index_response.text == "<html>AgentLens</html>"
    assert asset_response.status_code == status.HTTP_200_OK
    assert asset_response.text == "console.log('agentlens');"
    assert fallback_response.status_code == status.HTTP_200_OK
    assert fallback_response.text == "<html>AgentLens</html>"


@pytest.mark.asyncio
async def test_static_frontend_does_not_fallback_for_unknown_api_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>AgentLens</html>", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    app = create_app()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"].startswith("application/json")
    assert "<html" not in response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


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

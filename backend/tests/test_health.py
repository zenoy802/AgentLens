from importlib.metadata import PackageNotFoundError
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import inspect
from starlette import status

from app.core import version as version_module
from app.core.config import get_settings
from app.core.version import APP_VERSION, get_app_version
from app.db.session import get_engine, initialize_metadata_database
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["version"], str)
    assert payload["version"]
    assert payload["version"] == app.version
    assert payload["metadata_db"] == "ok"
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["uptime_seconds"] >= 0


def test_get_app_version_prefers_unified_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        if package_name == "agentlens":
            return "1.0.0"
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(version_module, "version", fake_version)

    assert get_app_version() == "1.0.0"


def test_get_app_version_falls_back_to_legacy_backend_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(package_name: str) -> str:
        if package_name == "AgentLens-backend":
            return "0.9.0"
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(version_module, "version", fake_version)

    assert get_app_version() == "0.9.0"


def test_get_app_version_falls_back_to_current_app_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_version(package_name: str) -> str:
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(version_module, "version", fake_version)

    assert get_app_version() == APP_VERSION


def test_initialize_metadata_database_creates_expected_tables() -> None:
    initialize_metadata_database()

    settings = get_settings()
    assert settings.metadata_db_path.exists()

    inspector = inspect(get_engine())
    table_names = set(inspector.get_table_names())
    assert "connections" in table_names
    assert "named_queries" in table_names
    assert "alembic_version" in table_names

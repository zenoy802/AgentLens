import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.session import dispose_engine

_TEST_FALLBACK_DIR = Path(__file__).parent / ".agentlens-test-data"
os.environ["AGENTLENS_DATA_DIR"] = str(_TEST_FALLBACK_DIR)


@pytest.fixture(autouse=True)
def isolate_test_data_dir(tmp_path: Path) -> Iterator[None]:
    test_dir = tmp_path / "agentlens-data"
    test_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AGENTLENS_DATA_DIR", str(test_dir))

    get_settings.cache_clear()
    dispose_engine()

    yield

    dispose_engine()
    get_settings.cache_clear()
    monkeypatch.undo()

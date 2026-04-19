import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.session import dispose_engine

TEST_DATA_DIR = Path(__file__).parent / ".agentlens-test-data"
os.environ["AGENTLENS_DATA_DIR"] = str(TEST_DATA_DIR)


@pytest.fixture(autouse=True)
def isolate_test_data_dir() -> Iterator[None]:
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)

    get_settings.cache_clear()
    dispose_engine()

    yield

    dispose_engine()
    get_settings.cache_clear()
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)

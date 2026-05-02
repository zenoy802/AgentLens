from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def require_real_mysql_url() -> Iterator[None]:
    if not os.environ.get("AGENT_LENS_TEST_MYSQL_URL"):
        pytest.skip("Set AGENT_LENS_TEST_MYSQL_URL to run real MySQL integration tests.")
    yield

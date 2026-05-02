from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pytest import MonkeyPatch

from app.api.admin import _scheduler_jobs
from app.core import scheduler as scheduler_module
from app.core.config import Settings


@dataclass
class _PendingJob:
    id: str = "cleanup"
    name: str = "Cleanup expired queries and query history"
    trigger: str = "cron[hour='3', minute='0']"


class _PendingScheduler:
    def get_jobs(self) -> list[_PendingJob]:
        return [_PendingJob()]


@dataclass
class _Process:
    name: str


def test_scheduler_jobs_handles_pending_jobs_without_next_run_time() -> None:
    jobs = _scheduler_jobs(_PendingScheduler())

    assert len(jobs) == 1
    assert jobs[0].id == "cleanup"
    assert jobs[0].next_run is None


def test_reload_flag_skips_main_process_but_starts_child(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, reload=False)
    monkeypatch.delenv("RUN_MAIN", raising=False)
    monkeypatch.setattr(sys, "argv", ["uvicorn", "app.main:app", "--reload"])

    monkeypatch.setattr(
        scheduler_module,
        "current_process",
        lambda: _Process(name="MainProcess"),
    )
    assert scheduler_module._should_start_scheduler(settings) is False

    monkeypatch.setattr(
        scheduler_module,
        "current_process",
        lambda: _Process(name="SpawnProcess-1"),
    )
    assert scheduler_module._should_start_scheduler(settings) is True

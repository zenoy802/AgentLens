from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pytest import MonkeyPatch

from app.api.admin import _scheduler_jobs
from app.core import scheduler as scheduler_module
from app.core.config import Settings

BRIDGE_CLEANUP_INTERVAL_HOURS = 6


@dataclass
class _PendingJob:
    id: str = "cleanup"
    name: str = "Cleanup expired queries and query history"
    trigger: str = "cron[hour='3', minute='0']"


class _PendingScheduler:
    def get_jobs(self) -> list[_PendingJob]:
        return [_PendingJob()]


class _RecordingScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict[str, object]] = []
        self.started = False

    def add_job(self, func: object, trigger: str, **kwargs: object) -> object:
        job = {"func": func, "trigger": trigger, **kwargs}
        self.jobs.append(job)
        return job

    def get_jobs(self) -> list[dict[str, object]]:
        return self.jobs

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = True) -> None:
        _ = wait


@dataclass
class _Process:
    name: str


def test_scheduler_jobs_handles_pending_jobs_without_next_run_time() -> None:
    jobs = _scheduler_jobs(_PendingScheduler())

    assert len(jobs) == 1
    assert jobs[0].id == "cleanup"
    assert jobs[0].next_run is None


def test_scheduler_registers_agent_bridge_cleanup_jobs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    recording_scheduler = _RecordingScheduler()

    def build_recording_scheduler(timezone: object) -> _RecordingScheduler:
        _ = timezone
        return recording_scheduler

    def skip_scheduler_start(settings: Settings) -> bool:
        _ = settings
        return False

    monkeypatch.setattr(
        scheduler_module,
        "_BackgroundScheduler",
        build_recording_scheduler,
    )
    monkeypatch.setattr(scheduler_module, "_should_start_scheduler", skip_scheduler_start)

    scheduler = scheduler_module.start_scheduler(Settings(data_dir=tmp_path, reload=False))

    assert scheduler is recording_scheduler
    jobs_by_id = {str(job["id"]): job for job in recording_scheduler.jobs}
    assert jobs_by_id["cleanup"]["trigger"] == "cron"
    assert jobs_by_id["cleanup_expired_annotations"]["trigger"] == "interval"
    assert jobs_by_id["cleanup_expired_annotations"]["hours"] == BRIDGE_CLEANUP_INTERVAL_HOURS
    assert jobs_by_id["cleanup_expired_selection_snapshots"]["trigger"] == "interval"
    assert (
        jobs_by_id["cleanup_expired_selection_snapshots"]["hours"] == BRIDGE_CLEANUP_INTERVAL_HOURS
    )
    assert recording_scheduler.started is False


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

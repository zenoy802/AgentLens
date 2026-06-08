from __future__ import annotations

import os
import sys
from datetime import UTC
from multiprocessing import current_process
from typing import Any, Protocol, cast

from apscheduler.schedulers.background import (  # type: ignore[import-untyped]
    BackgroundScheduler as _BackgroundScheduler,
)
from loguru import logger

from app.core.config import Settings, get_settings
from app.core.logging import safe_exception_context
from app.db.session import get_session_factory
from app.services.cleanup_service import CleanupService


class Scheduler(Protocol):
    def add_job(self, func: object, trigger: str, **kwargs: Any) -> object: ...

    def get_jobs(self) -> list[Any]: ...

    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


def start_scheduler(settings: Settings | None = None) -> Scheduler:
    active_settings = settings or get_settings()
    scheduler = cast(Scheduler, _BackgroundScheduler(timezone=UTC))
    scheduler.add_job(
        _run_cleanup_job,
        "cron",
        hour=3,
        minute=0,
        id="cleanup",
        name="Cleanup expired queries and query history",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled cleanup job registered")
    scheduler.add_job(
        _run_cleanup_expired_annotations_job,
        "interval",
        hours=6,
        id="cleanup_expired_annotations",
        name="Cleanup expired annotations",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_cleanup_expired_selection_snapshots_job,
        "interval",
        hours=6,
        id="cleanup_expired_selection_snapshots",
        name="Cleanup expired selection snapshots",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled Agent Bridge cleanup jobs registered")

    if _should_start_scheduler(active_settings):
        scheduler.start()
        logger.info("Background scheduler started")
    else:
        logger.info("Background scheduler start skipped in reload parent process")

    return scheduler


def shutdown_scheduler(scheduler: Scheduler | None) -> None:
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
    except Exception as exc:  # pragma: no cover - defensive shutdown path
        logger.warning(
            "Background scheduler shutdown skipped: context={}",
            safe_exception_context(exc),
        )


def _run_cleanup_job() -> None:
    session = get_session_factory()()
    try:
        report = CleanupService().run(session)
        logger.info("Scheduled cleanup completed: {}", report.model_dump())
    except Exception as exc:  # pragma: no cover - scheduler path is covered by service tests
        session.rollback()
        logger.error("Scheduled cleanup failed: context={}", safe_exception_context(exc))
    finally:
        session.close()


def _run_cleanup_expired_annotations_job() -> None:
    session = get_session_factory()()
    try:
        deleted_count = CleanupService().delete_expired_annotations(session)
        logger.info("Expired annotation cleanup completed: deleted={}", deleted_count)
    except Exception as exc:  # pragma: no cover - scheduler path is covered by service tests
        session.rollback()
        logger.error("Expired annotation cleanup failed: context={}", safe_exception_context(exc))
    finally:
        session.close()


def _run_cleanup_expired_selection_snapshots_job() -> None:
    session = get_session_factory()()
    try:
        deleted_count = CleanupService().delete_expired_selection_snapshots(session)
        logger.info("Expired selection snapshot cleanup completed: deleted={}", deleted_count)
    except Exception as exc:  # pragma: no cover - scheduler path is covered by service tests
        session.rollback()
        logger.error(
            "Expired selection snapshot cleanup failed: context={}",
            safe_exception_context(exc),
        )
    finally:
        session.close()


def _should_start_scheduler(settings: Settings) -> bool:
    run_main = os.environ.get("RUN_MAIN")
    if run_main is not None:
        return run_main == "true"
    return not (
        (settings.reload or _argv_has_reload_flag()) and current_process().name == "MainProcess"
    )


def _argv_has_reload_flag() -> bool:
    return "--reload" in sys.argv

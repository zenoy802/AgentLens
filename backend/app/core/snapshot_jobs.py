from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache, partial

from loguru import logger

from app.core.logging import safe_exception_context
from app.db.session import get_session_factory
from app.services.snapshot_service import SnapshotService

_SNAPSHOT_WORKERS = 2


class SnapshotJobRunner:
    def __init__(self, *, max_workers: int = _SNAPSHOT_WORKERS) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="agentlens-snapshot",
        )
        self._lock = threading.Lock()
        self._futures: dict[str, Future[None]] = {}

    def submit(self, snapshot_id: str) -> bool:
        with self._lock:
            existing = self._futures.get(snapshot_id)
            if existing is not None and not existing.done():
                return False
            future = self._executor.submit(_run_snapshot_build, snapshot_id)
            self._futures[snapshot_id] = future
            future.add_done_callback(partial(self._completed, snapshot_id))
            return True

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _completed(self, snapshot_id: str, future: Future[None]) -> None:
        with self._lock:
            self._futures.pop(snapshot_id, None)
        exception = future.exception()
        if exception is not None:
            logger.warning(
                "Snapshot background job failed: snapshot_id={} context={}",
                snapshot_id,
                safe_exception_context(exception),
            )


@lru_cache(maxsize=1)
def get_snapshot_job_runner() -> SnapshotJobRunner:
    return SnapshotJobRunner()


def recover_interrupted_snapshot_builds() -> int:
    session = get_session_factory()()
    try:
        recovered = SnapshotService(session).recover_incomplete()
        if recovered:
            logger.warning("Interrupted snapshot builds marked failed: count={}", recovered)
        return recovered
    finally:
        session.close()


def shutdown_snapshot_jobs() -> None:
    if get_snapshot_job_runner.cache_info().currsize == 0:
        return
    get_snapshot_job_runner().shutdown()
    get_snapshot_job_runner.cache_clear()


def _run_snapshot_build(snapshot_id: str) -> None:
    session = get_session_factory()()
    try:
        SnapshotService(session).build(snapshot_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

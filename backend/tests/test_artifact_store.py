from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import cast

import pytest

from app.core.artifact_store import ArtifactStore
from app.core.errors import ArtifactCorruptedError, ArtifactPathError, ArtifactWriteError

_MANIFEST = b'{"schema_version":"run-snapshot/v1"}'


def test_artifact_store_writes_deterministic_atomic_gzip_and_verifies(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    lines = [_MANIFEST, b'{"schema_version":"run-row/v1","trace_id":"one"}']

    first = store.write_gzip_jsonl("snapshots/first.jsonl.gz", lines)
    second = store.write_gzip_jsonl("snapshots/second.jsonl.gz", lines)

    assert first.sha256 == second.sha256
    assert first.size_bytes == second.size_bytes
    manifest = store.verify(
        first.relative_path,
        expected_sha256=first.sha256,
        expected_size_bytes=first.size_bytes,
        expected_schema_version="run-snapshot/v1",
    )
    assert manifest["schema_version"] == "run-snapshot/v1"
    assert (
        list(
            store.iter_gzip_jsonl(
                first.relative_path,
                expected_sha256=first.sha256,
                expected_size_bytes=first.size_bytes,
                expected_schema_version="run-snapshot/v1",
            )
        )
        == lines
    )


@pytest.mark.parametrize("path", ["../outside.json", "/tmp/outside.json", "snapshots/../../x"])
def test_artifact_store_rejects_path_traversal(tmp_path: Path, path: str) -> None:
    with pytest.raises(ArtifactPathError):
        ArtifactStore(tmp_path).resolve(path)


def test_artifact_store_rejects_symlink_escape(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactPathError):
        store.resolve("escape/artifact.json.gz")


def test_artifact_store_detects_same_size_tamper(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    info = store.write_gzip_jsonl("snapshots/tampered.jsonl.gz", [_MANIFEST])
    path = store.resolve(info.relative_path, must_exist=True)
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 1
    path.write_bytes(payload)

    with pytest.raises(ArtifactCorruptedError) as exc_info:
        store.verify(
            info.relative_path,
            expected_sha256=info.sha256,
            expected_size_bytes=info.size_bytes,
            expected_schema_version="run-snapshot/v1",
        )

    assert exc_info.value.detail == {"reason": "sha256_mismatch"}


def test_artifact_store_rejects_oversized_record_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArtifactStore(tmp_path)
    monkeypatch.setattr("app.core.artifact_store._MAX_JSONL_LINE_BYTES", 8)

    with pytest.raises(ArtifactWriteError):
        store.write_gzip_jsonl("snapshots/oversized.jsonl.gz", [_MANIFEST])

    assert not store.resolve("snapshots/oversized.jsonl.gz").exists()
    assert list(store.root.rglob("*.agentlens-tmp")) == []


def test_artifact_store_cleans_temp_file_when_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ArtifactStore(tmp_path)

    def fail_fsync(_: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr("app.core.artifact_store.os.fsync", fail_fsync)

    with pytest.raises(ArtifactWriteError):
        store.write_gzip_jsonl("snapshots/failed.jsonl.gz", [_MANIFEST])

    assert not store.resolve("snapshots/failed.jsonl.gz").exists()
    assert list(store.root.rglob("*.agentlens-tmp")) == []


@pytest.mark.parametrize("failure_point", ["open", "write", "rename"])
def test_artifact_store_never_exposes_partial_file_at_other_failure_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    store = ArtifactStore(tmp_path)
    lines: object = [_MANIFEST]
    if failure_point == "open":
        monkeypatch.setattr(
            "app.core.artifact_store.tempfile.mkstemp",
            lambda **_: (_ for _ in ()).throw(OSError("injected open failure")),
        )
    elif failure_point == "write":

        def failing_lines() -> Iterator[bytes]:
            yield _MANIFEST
            raise OSError("injected write failure")

        lines = failing_lines()
    else:
        monkeypatch.setattr(
            Path,
            "replace",
            lambda *_: (_ for _ in ()).throw(OSError("injected rename failure")),
        )

    with pytest.raises(ArtifactWriteError):
        store.write_gzip_jsonl("snapshots/partial.jsonl.gz", cast(Iterable[bytes], lines))

    assert not store.resolve("snapshots/partial.jsonl.gz").exists()
    assert list(store.root.rglob("*.agentlens-tmp")) == []

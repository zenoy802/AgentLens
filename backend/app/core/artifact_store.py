from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

from app.core.config import get_settings
from app.core.errors import ArtifactCorruptedError, ArtifactPathError, ArtifactWriteError
from app.core.logging import sanitize_exception_message

_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_JSONL_LINE_BYTES = 8 * 1024 * 1024
_TEMP_SUFFIX = ".agentlens-tmp"


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    relative_path: str
    sha256: str
    size_bytes: int


class ArtifactStore:
    """Content-verified artifact IO constrained to the AgentLens artifacts directory."""

    def __init__(self, data_dir: Path | None = None) -> None:
        active_data_dir = data_dir or get_settings().data_dir
        self.root = (active_data_dir / "artifacts").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        normalized = PurePosixPath(relative_path)
        if (
            not relative_path
            or normalized.is_absolute()
            or any(part in {"", ".", ".."} for part in normalized.parts)
        ):
            raise ArtifactPathError(detail={"reason": "path_not_safe"})
        candidate = (self.root / Path(*normalized.parts)).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise ArtifactPathError(detail={"reason": "path_outside_data_dir"})
        if must_exist and not candidate.is_file():
            raise ArtifactCorruptedError(detail={"reason": "artifact_missing"})
        return candidate

    def write_gzip_jsonl(
        self,
        relative_path: str,
        lines: Iterable[bytes],
    ) -> ArtifactInfo:
        destination = self.resolve(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        renamed = False
        try:
            descriptor, raw_temp_path = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=_TEMP_SUFFIX,
                dir=destination.parent,
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(descriptor, "wb") as raw_file:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=raw_file,
                    mtime=0,
                ) as gzip_file:
                    for line in lines:
                        if len(line) > _MAX_JSONL_LINE_BYTES:
                            raise ValueError("JSONL record exceeds the maximum supported size")
                        if b"\n" in line or b"\r" in line:
                            raise ValueError("JSONL records must not contain raw line breaks")
                        gzip_file.write(line)
                        gzip_file.write(b"\n")
                raw_file.flush()
                os.fsync(raw_file.fileno())
            temp_path.replace(destination)
            renamed = True
            self._fsync_directory(destination.parent)
            sha256, size_bytes = self._hash_and_size(destination)
            return ArtifactInfo(
                relative_path=relative_path,
                sha256=sha256,
                size_bytes=size_bytes,
            )
        except Exception as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if renamed:
                destination.unlink(missing_ok=True)
            if isinstance(exc, ArtifactPathError):
                raise
            raise ArtifactWriteError(
                detail={"reason": "atomic_write_failed", "error": sanitize_exception_message(exc)}
            ) from exc

    def verify(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
        expected_schema_version: str,
    ) -> Mapping[str, Any]:
        path = self.resolve(relative_path, must_exist=True)
        actual_sha256, actual_size = self._hash_and_size(path)
        self._assert_integrity(
            actual_sha256,
            actual_size,
            expected_sha256=expected_sha256,
            expected_size_bytes=expected_size_bytes,
        )
        try:
            with gzip.open(path, "rb") as artifact:
                first_line = self._read_bounded_line(artifact)
            manifest = self._decode_manifest(first_line, expected_schema_version)
        except ArtifactCorruptedError:
            raise
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptedError(detail={"reason": "gzip_or_manifest_invalid"}) from exc
        return manifest

    def iter_gzip_jsonl(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
        expected_schema_version: str,
    ) -> Iterator[bytes]:
        path = self.resolve(relative_path, must_exist=True)
        try:
            with path.open("rb") as raw_artifact:
                actual_sha256, actual_size = self._hash_stream(raw_artifact)
                self._assert_integrity(
                    actual_sha256,
                    actual_size,
                    expected_sha256=expected_sha256,
                    expected_size_bytes=expected_size_bytes,
                )
                raw_artifact.seek(0)
                with gzip.GzipFile(fileobj=raw_artifact, mode="rb") as artifact:
                    first_line = self._read_bounded_line(artifact)
                    self._decode_manifest(first_line, expected_schema_version)
                    yield first_line
                    while True:
                        line = self._read_bounded_line(artifact, allow_eof=True)
                        if line == b"":
                            break
                        yield line
        except ArtifactCorruptedError:
            raise
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptedError(detail={"reason": "gzip_stream_invalid"}) from exc

    def delete(self, relative_path: str) -> None:
        path = self.resolve(relative_path)
        path.unlink(missing_ok=True)

    def cleanup_temporary_files(self) -> int:
        removed = 0
        for path in self.root.rglob(f"*{_TEMP_SUFFIX}"):
            resolved = path.resolve(strict=False)
            if resolved.is_relative_to(self.root) and path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _hash_and_size(path: Path) -> tuple[str, int]:
        with path.open("rb") as artifact:
            return ArtifactStore._hash_stream(artifact)

    @staticmethod
    def _hash_stream(artifact: BinaryIO) -> tuple[str, int]:
        digest = hashlib.sha256()
        size_bytes = 0
        while chunk := artifact.read(_HASH_CHUNK_BYTES):
            size_bytes += len(chunk)
            digest.update(chunk)
        return digest.hexdigest(), size_bytes

    @staticmethod
    def _assert_integrity(
        actual_sha256: str,
        actual_size_bytes: int,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> None:
        if actual_size_bytes != expected_size_bytes:
            raise ArtifactCorruptedError(
                detail={"reason": "size_mismatch", "expected": expected_size_bytes}
            )
        if actual_sha256 != expected_sha256:
            raise ArtifactCorruptedError(detail={"reason": "sha256_mismatch"})

    @staticmethod
    def _decode_manifest(
        first_line: bytes,
        expected_schema_version: str,
    ) -> Mapping[str, Any]:
        manifest = json.loads(first_line)
        if not isinstance(manifest, Mapping):
            raise ArtifactCorruptedError(detail={"reason": "manifest_not_object"})
        if manifest.get("schema_version") != expected_schema_version:
            raise ArtifactCorruptedError(
                detail={
                    "reason": "schema_version_unsupported",
                    "expected": expected_schema_version,
                }
            )
        return manifest

    @staticmethod
    def _read_bounded_line(artifact: Any, *, allow_eof: bool = False) -> bytes:
        line = artifact.readline(_MAX_JSONL_LINE_BYTES + 1)
        if line == b"" and allow_eof:
            return b""
        if line == b"":
            raise ArtifactCorruptedError(detail={"reason": "manifest_missing"})
        if len(line) > _MAX_JSONL_LINE_BYTES:
            raise ArtifactCorruptedError(detail={"reason": "jsonl_line_too_large"})
        if not line.endswith(b"\n"):
            raise ArtifactCorruptedError(detail={"reason": "jsonl_line_incomplete"})
        return cast(bytes, line[:-1])

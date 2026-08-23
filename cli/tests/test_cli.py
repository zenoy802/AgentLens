from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from agentlens_client.context_export import export_context
from agentlens_client.errors import BackendBusinessError, BackendUnavailableError
from agentlens_client.sync_client import AgentLensSyncClient
from click.testing import CliRunner

from agentlens_cli.main import cli

BASE_ENV = {
    "AGENTLENS_BACKEND_URL": "http://testserver",
    "AGENTLENS_TIMEOUT": "30",
    "AGENTLENS_AUTHOR": "human",
    "AGENTLENS_OUTPUT_FORMAT": "json",
}
EXPECTED_QUERY_ID = 7
EXPECTED_ROW_COUNT = 2
MIN_COLLISION_ROWS = 2
TRUNCATED_PAGE_SIZE = 100
EXIT_BACKEND_UNAVAILABLE = 3
EXIT_BACKEND_BUSINESS = 4
EXPECTED_MISSING_SELECTION_REQUESTED_COUNT = 2


class FakeClient:
    last: FakeClient | None = None

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.created_annotations: list[dict[str, Any]] = []
        self.batch_annotations: list[list[dict[str, Any]]] = []
        self.clear_filters: list[dict[str, Any]] = []
        self.executed: list[dict[str, Any]] = []
        FakeClient.last = self

    def list_connections(self) -> dict[str, Any]:
        return {"items": [{"id": 1, "name": "local", "password": "***"}], "pagination": {}}

    def show_connection(self, name: str) -> dict[str, Any]:
        return {"id": 1, "name": name, "extra_params": {"api_key": "***"}}

    def list_queries(self) -> dict[str, Any]:
        return {"items": [{"id": 1, "name": "q"}], "pagination": {}}

    def show_query(self, query_id: int) -> dict[str, Any]:
        return {"id": query_id, "sql_text": "SELECT 1"}

    def exec_query(self, connection: str, sql: str, row_limit: int | None = None) -> dict[str, Any]:
        self.executed.append({"connection": connection, "sql": sql, "row_limit": row_limit})
        return _execution_result(query_id=EXPECTED_QUERY_ID)

    def rerun_query(self, query_id: int) -> dict[str, Any]:
        return _execution_result(query_id=query_id)

    def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        rows = [
            {"_row_identity": "a", "value": 1},
            {"_row_identity": "b", "value": 2},
        ]
        return {
            "query_id": query_id,
            "columns": [{"name": "value", "sql_type": "INT", "inferred_type": "integer"}],
            "rows": rows[offset : offset + limit],
            "total": len(rows),
            "fingerprints": {"sql": "s", "schema": "c", "result": "r"},
            "suggested_field_renders": {},
        }

    def get_trajectories(self, query_id: int, session_id: str | None = None) -> dict[str, Any]:
        trajectories = [{"group_key": "s1", "message_count": 1, "messages": []}]
        if session_id is not None:
            trajectories = [item for item in trajectories if item["group_key"] == session_id]
        return {"query_id": query_id, "trajectories": trajectories}

    def get_labels(self, query_id: int) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "labels_by_row": {
                "a": {"quality": "bad"},
                "b": {"quality": "good"},
            },
        }

    def get_annotations(self, query_id: int, **filters: Any) -> list[dict[str, Any]]:
        return [
            {"id": 1, "query_id": query_id, "row_identity": "a", "color": "red", **filters},
            {"id": 2, "query_id": query_id, "row_identity": "b", "color": "yellow"},
        ]

    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return {
            "id": selection_id,
            "query_id": 1,
            "row_identities": ["b"],
            "count": 1,
            "source": "ui",
        }

    def create_annotation(self, query_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        annotation = {"id": 10, "query_id": query_id, **payload}
        self.created_annotations.append(annotation)
        return annotation

    def create_annotations_batch(
        self,
        query_id: int,
        annotations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.batch_annotations.append(annotations)
        return [
            {"id": index + 1, "query_id": query_id, **item}
            for index, item in enumerate(annotations)
        ]

    def clear_annotations(self, query_id: int, **filters: Any) -> dict[str, Any]:
        self.clear_filters.append(filters)
        return {"query_id": query_id, "deleted_count": 2, "filters": filters}

    def schema_info(self) -> dict[str, Any]:
        return {
            "backend_version": "0.1.0",
            "cli_version": "unknown",
            "annotation": {
                "colors": ["red", "yellow", "green", "blue", "gray"],
                "severities": ["info", "warning", "error"],
                "max_text_length": 2000,
                "author_pattern": "^[a-zA-Z0-9_:.-]+$",
            },
            "recommended_workflow": "",
        }

    def get_column_schema(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "columns": [{"name": "value"}]}

    def get_label_schema(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "fields": []}


class MissingSelectionRowClient(FakeClient):
    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return {
            "id": selection_id,
            "query_id": 1,
            "row_identities": ["b", "missing-row"],
            "count": 2,
            "source": "ui",
        }


class UnavailableClient(FakeClient):
    def schema_info(self) -> dict[str, Any]:
        raise BackendUnavailableError("Cannot connect to AgentLens backend at http://testserver")


class CollisionClient(FakeClient):
    def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        assert query_id == 1
        assert limit >= MIN_COLLISION_ROWS
        rows = [
            {
                "_row_identity": "user-value-a",
                "_agent_lens_row_identity": "agentlens-a",
                "value": 1,
            },
            {
                "_row_identity": "user-value-b",
                "_agent_lens_row_identity": "agentlens-b",
                "value": 2,
            },
        ]
        return {
            "query_id": query_id,
            "columns": [
                {"name": "_row_identity", "sql_type": "TEXT", "inferred_type": "text"},
                {"name": "value", "sql_type": "INT", "inferred_type": "integer"},
            ],
            "rows": rows[offset : offset + limit],
            "total": len(rows),
            "truncated": False,
            "fingerprints": {"sql": "s", "schema": "c", "result": "r"},
            "suggested_field_renders": {},
            "warnings": [
                {
                    "code": "ROW_IDENTITY_KEY_COLLISION",
                    "message": "collision",
                    "detail": {
                        "requested_key": "_row_identity",
                        "fallback_key": "_agent_lens_row_identity",
                    },
                }
            ],
        }

    def get_labels(self, query_id: int) -> dict[str, Any]:
        assert query_id == 1
        return {
            "query_id": query_id,
            "labels_by_row": {
                "agentlens-b": {"quality": "good"},
            },
        }

    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return {
            "id": selection_id,
            "query_id": 1,
            "row_identities": ["agentlens-b"],
            "count": 1,
            "source": "ui",
        }


class TruncatedExportClient(FakeClient):
    def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        payload = super().get_rows(query_id, limit=limit, offset=offset)
        payload["truncated"] = True
        payload["execution"] = {"truncated": True}
        payload["warnings"] = [{"code": "RESULT_TRUNCATED", "message": "truncated"}]
        return payload


def test_top_level_help_mentions_live_and_snapshot() -> None:
    result = CliRunner().invoke(cli, ["--help"], env=BASE_ENV)

    assert result.exit_code == 0
    assert "Live access:" in result.output
    assert "agentlens data rows --query 42" in result.output
    assert "Snapshot export:" in result.output
    assert "agentlens context export --query 42" in result.output


def test_local_diff_json_reports_observed_and_action_divergence(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(_local_diff_run("baseline", assistant_text="I will search.", limit=10)),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(_local_diff_run("candidate", assistant_text="I shall search.", limit=100)),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            "--baseline-trace",
            str(baseline),
            "--candidate-trace",
            str(candidate),
            "--format",
            "json",
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "trajectory-alignment/v1"
    assert payload["first_observed_divergence"]["category"] == "assistant_content_changed"
    assert payload["first_action_divergence"]["category"] == "tool_argument_changed"
    assert payload["steps"][1]["field_diffs"][0]["path"] == "$.arguments.limit"


def test_local_diff_rejects_invalid_trace_without_backend_request(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            "--baseline-trace",
            str(invalid),
            "--candidate-trace",
            str(invalid),
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 1
    assert "Unable to diff traces" in result.output


def test_local_diff_text_accepts_wrapped_trace_and_policy(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy = tmp_path / "policy.json"
    baseline.write_text(
        json.dumps({"run": _local_diff_run("baseline", assistant_text="same", limit=10)}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"run": _local_diff_run("candidate", assistant_text="same", limit=10)}),
        encoding="utf-8",
    )
    policy.write_text(
        json.dumps(
            {
                "canonicalization_policy": {"version": "canonicalization/v1"},
                "alignment_policy": {"version": "alignment/v1"},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            "--baseline-trace",
            str(baseline),
            "--candidate-trace",
            str(candidate),
            "--policy",
            str(policy),
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 0, result.output
    assert "quality: exact" in result.output
    assert "first observed divergence: none" in result.output
    assert "first action divergence: none" in result.output


def test_local_diff_accepts_canonical_trajectory_fixtures(tmp_path: Path) -> None:
    from app.schemas.trace_contract import CanonicalRunRow  # noqa: PLC0415
    from app.services.canonicalization import canonicalize_run  # noqa: PLC0415

    baseline = tmp_path / "baseline-canonical.json"
    candidate = tmp_path / "candidate-canonical.json"
    baseline_trajectory = canonicalize_run(
        CanonicalRunRow.model_validate(_local_diff_run("baseline", assistant_text="same", limit=10))
    )
    candidate_trajectory = canonicalize_run(
        CanonicalRunRow.model_validate(
            _local_diff_run("candidate", assistant_text="same", limit=11)
        )
    )
    baseline.write_text(baseline_trajectory.model_dump_json(), encoding="utf-8")
    candidate.write_text(candidate_trajectory.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            "--baseline-trace",
            str(baseline),
            "--candidate-trace",
            str(candidate),
            "--format",
            "json",
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["first_action_divergence"]["category"] == (
        "tool_argument_changed"
    )


def _local_diff_run(trace_id: str, *, assistant_text: str, limit: int) -> dict[str, Any]:
    return {
        "schema_version": "run-row/v1",
        "task_id": "task-1",
        "trial_id": None,
        "trace_id": trace_id,
        "pairing_key": None,
        "outcome": "success",
        "score": None,
        "metrics": {"latency_ms": None, "token_usage": None, "cost_usd": None},
        "messages": [
            {
                "event_index": 0,
                "kind": None,
                "role": "assistant",
                "content": assistant_text,
                "name": None,
                "tool_call_id": None,
                "tool_calls": None,
                "status": "unknown",
                "parent_event_id": None,
                "timestamp": None,
                "latency_ms": None,
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": None,
                "source_ref": {"query_id": 1, "row_identity": "row-0", "json_path": None},
            },
            {
                "event_index": 1,
                "kind": None,
                "role": "assistant",
                "content": "",
                "name": None,
                "tool_call_id": None,
                "tool_calls": [{"function": {"name": "search", "arguments": {"limit": limit}}}],
                "status": "unknown",
                "parent_event_id": None,
                "timestamp": None,
                "latency_ms": None,
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": None,
                "source_ref": {"query_id": 1, "row_identity": "row-1", "json_path": None},
            },
        ],
        "error": None,
        "metadata": {},
    }


def test_top_level_help_does_not_import_backend_server_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules.pop("agentlens_cli.commands.server", None)
    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "agentlens_cli.commands.server" or name in {"uvicorn", "sqlalchemy"}:
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    result = CliRunner().invoke(cli, ["--help"], env=BASE_ENV)

    assert result.exit_code == 0
    assert "run" in result.output


def test_server_command_reports_unified_package_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules.pop("agentlens_cli.commands.server", None)
    sys.modules.pop("app.server_runtime", None)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend"))
    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "uvicorn":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    result = CliRunner().invoke(cli, ["run"], env=BASE_ENV)

    assert result.exit_code != 0
    assert "requires the unified agentlens package" in result.output
    assert "git clone --branch v0.1.1 --depth 1" in result.output
    assert "https://github.com/zenoy802/AgentLens.git" in result.output
    assert "cd AgentLens" in result.output
    assert "pipx run --spec build pyproject-build" in result.output
    assert "Missing dependency: uvicorn" in result.output
    assert "Traceback" not in result.output


def test_server_command_reports_missing_backend_app_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("app."):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    result = CliRunner().invoke(cli, ["run"], env=BASE_ENV)

    assert result.exit_code != 0
    assert "requires the unified agentlens package" in result.output
    assert "Missing dependency: app.server_runtime" in result.output
    assert "Traceback" not in result.output


def test_schema_info_outputs_valid_json(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)

    result = CliRunner().invoke(cli, ["schema", "info"], env=BASE_ENV)

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["backend_version"] == "0.1.0"
    assert "agentlens data rows" in payload["recommended_workflow"]
    assert "agentlens context export" in payload["recommended_workflow"]


def test_data_rows_json_and_jsonl(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)
    runner = CliRunner()

    json_result = runner.invoke(
        cli,
        ["data", "rows", "--query", "1", "--format", "json"],
        env=BASE_ENV,
    )
    assert json_result.exit_code == 0
    envelope = json.loads(json_result.output)
    assert envelope["query_id"] == 1
    assert envelope["columns"][0]["name"] == "value"
    assert envelope["rows"][0]["_row_identity"] == "a"

    jsonl_result = runner.invoke(
        cli,
        ["data", "rows", "--query", "1", "--format", "jsonl"],
        env=BASE_ENV,
    )
    assert jsonl_result.exit_code == 0
    lines = [json.loads(line) for line in jsonl_result.output.splitlines()]
    assert lines == [{"_row_identity": "a", "value": 1}, {"_row_identity": "b", "value": 2}]


def test_query_exec_accepts_sql_file(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)
    sql_file = tmp_path / "query.sql"
    sql_file.write_text("SELECT 1", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "query",
            "exec",
            "--connection",
            "local",
            "--sql-file",
            str(sql_file),
            "--row-limit",
            "10",
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["query_id"] == EXPECTED_QUERY_ID
    assert payload["row_count"] == EXPECTED_ROW_COUNT
    assert FakeClient.last is not None
    assert FakeClient.last.executed == [{"connection": "local", "sql": "SELECT 1", "row_limit": 10}]


def test_annotation_write_back_and_batch_highlight(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)
    runner = CliRunner()

    annotate_result = runner.invoke(
        cli,
        [
            "annotate",
            "--query",
            "1",
            "--row",
            "abc",
            "--color",
            "red",
            "--text",
            "bad answer",
            "--author",
            "agent:codex",
        ],
        env=BASE_ENV,
    )
    assert annotate_result.exit_code == 0
    assert FakeClient.last is not None
    assert FakeClient.last.created_annotations[0]["author"] == "agent:codex"
    assert FakeClient.last.created_annotations[0]["row_identity"] == "abc"

    highlight_result = runner.invoke(
        cli,
        [
            "highlight",
            "--query",
            "1",
            "--rows",
            "a,b,c",
            "--color",
            "yellow",
            "--note",
            "review",
        ],
        env=BASE_ENV,
    )
    assert highlight_result.exit_code == 0
    assert FakeClient.last is not None
    assert len(FakeClient.last.batch_annotations) == 1
    assert [item["row_identity"] for item in FakeClient.last.batch_annotations[0]] == [
        "a",
        "b",
        "c",
    ]


def test_annotation_clear_requires_filter(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)
    runner = CliRunner()

    rejected = runner.invoke(cli, ["annotation", "clear", "--query", "1"], env=BASE_ENV)
    assert rejected.exit_code == EXIT_BACKEND_BUSINESS
    assert "Refusing to clear annotations" in rejected.output

    accepted = runner.invoke(
        cli,
        ["annotation", "clear", "--query", "1", "--author-prefix", "agent:"],
        env=BASE_ENV,
    )
    assert accepted.exit_code == 0
    assert FakeClient.last is not None
    assert FakeClient.last.clear_filters == [
        {
            "author": None,
            "author_prefix": "agent:",
            "color": None,
            "annotation_set": None,
        }
    ]


def test_data_selection_and_schema_subcommands(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)
    runner = CliRunner()

    selection_result = runner.invoke(
        cli,
        ["data", "selection", "--selection", "sel_x"],
        env=BASE_ENV,
    )
    assert selection_result.exit_code == 0
    assert json.loads(selection_result.output)["id"] == "sel_x"

    columns_result = runner.invoke(cli, ["schema", "columns", "--query", "1"], env=BASE_ENV)
    assert columns_result.exit_code == 0
    assert json.loads(columns_result.output)["columns"] == [{"name": "value"}]

    labels_result = runner.invoke(cli, ["schema", "labels", "--query", "1"], env=BASE_ENV)
    assert labels_result.exit_code == 0
    assert json.loads(labels_result.output)["fields"] == []


def test_context_export_selection_and_claude_target(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", FakeClient)

    result = CliRunner().invoke(
        cli,
        [
            "context",
            "export",
            "--query",
            "1",
            "--selection",
            "sel_x",
            "--output-dir",
            str(tmp_path),
            "--target",
            "claude-code",
        ],
        env=BASE_ENV,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["scope"] == "selection"
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "AGENTLENS_CONTEXT.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "selection.json").exists()
    rows = [
        json.loads(line)
        for line in (tmp_path / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [{"_row_identity": "b", "value": 2}]


def test_context_export_uses_backend_fallback_identity(tmp_path: Path) -> None:
    client = CollisionClient("http://testserver")

    result = export_context(
        client=client,
        query_id=1,
        selection_id="sel_collision",
        output_dir=tmp_path,
    )

    assert result["scope"] == "selection"
    rows = [
        json.loads(line)
        for line in (tmp_path / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    labels = [
        json.loads(line)
        for line in (tmp_path / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "_row_identity": "user-value-b",
            "_agent_lens_row_identity": "agentlens-b",
            "value": 2,
        }
    ]
    assert labels == [{"row_identity": "agentlens-b", "labels": {"quality": "good"}}]


def test_context_export_marks_missing_selection_rows(tmp_path: Path) -> None:
    client = MissingSelectionRowClient("http://testserver")

    export_context(
        client=client,
        query_id=1,
        selection_id="sel_missing",
        output_dir=tmp_path,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    selection_manifest = manifest["selection"]
    assert selection_manifest["requested_row_count"] == EXPECTED_MISSING_SELECTION_REQUESTED_COUNT
    assert selection_manifest["exported_row_count"] == 1
    assert selection_manifest["missing_row_count"] == 1
    assert selection_manifest["missing_row_identities"] == ["missing-row"]
    selection = json.loads((tmp_path / "selection.json").read_text(encoding="utf-8"))
    assert selection["row_identities"] == ["b", "missing-row"]


def test_context_export_fails_when_query_result_is_truncated(tmp_path: Path) -> None:
    client = TruncatedExportClient("http://testserver")

    with pytest.raises(BackendBusinessError) as exc_info:
        export_context(client=client, query_id=1, output_dir=tmp_path)

    assert exc_info.value.code == "CONTEXT_EXPORT_TRUNCATED"
    assert not (tmp_path / "manifest.json").exists()


def test_context_export_rejects_unwritable_output_path(tmp_path: Path) -> None:
    client = FakeClient("http://testserver")
    output_path = tmp_path / "context-file"
    output_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(BackendBusinessError) as exc_info:
        export_context(client=client, query_id=1, output_dir=output_path)

    assert exc_info.value.code == "CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE"
    assert output_path.read_text(encoding="utf-8") == "not a directory"


def test_sync_client_uses_fallback_identity_for_label_queries(monkeypatch: Any) -> None:
    captured_payloads: list[dict[str, Any] | None] = []

    def fake_post(
        _self: AgentLensSyncClient,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> Any:
        captured_payloads.append(json)
        if path == "/queries/1/execute":
            return {
                "query_id": 1,
                "execution": {"row_count": 2, "truncated": False},
                "columns": [
                    {"name": "_row_identity", "sql_type": "TEXT", "inferred_type": "text"},
                    {"name": "value", "sql_type": "INT", "inferred_type": "integer"},
                ],
                "rows": [
                    {
                        "_row_identity": "user-value-a",
                        "_agent_lens_row_identity": "agentlens-a",
                        "value": 1,
                    },
                    {
                        "_row_identity": "user-value-b",
                        "_agent_lens_row_identity": "agentlens-b",
                        "value": 2,
                    },
                ],
                "warnings": [
                    {
                        "code": "ROW_IDENTITY_KEY_COLLISION",
                        "detail": {"fallback_key": "_agent_lens_row_identity"},
                    }
                ],
                "fingerprints": {},
                "suggested_field_renders": {},
            }
        if path == "/queries/1/labels/query":
            return {"labels_by_row": {"agentlens-a": {"quality": "bad"}}}
        raise AssertionError(path)

    monkeypatch.setattr(AgentLensSyncClient, "post", fake_post)
    client = AgentLensSyncClient("http://testserver")

    labels = client.get_labels(1)

    assert captured_payloads[1] == {"row_identities": ["agentlens-a", "agentlens-b"]}
    assert labels == {"query_id": 1, "labels_by_row": {"agentlens-a": {"quality": "bad"}}}


def test_sync_client_does_not_report_truncated_page_size_as_total(monkeypatch: Any) -> None:
    def fake_post(
        _self: AgentLensSyncClient,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> Any:
        assert path == "/queries/1/execute"
        assert json == {"row_limit": TRUNCATED_PAGE_SIZE}
        return {
            "query_id": 1,
            "execution": {"row_count": TRUNCATED_PAGE_SIZE, "truncated": True},
            "columns": [{"name": "value"}],
            "rows": [
                {"_row_identity": str(index), "value": index}
                for index in range(TRUNCATED_PAGE_SIZE)
            ],
            "warnings": [{"code": "RESULT_TRUNCATED", "message": "truncated"}],
            "fingerprints": {},
            "suggested_field_renders": {},
        }

    monkeypatch.setattr(AgentLensSyncClient, "post", fake_post)
    client = AgentLensSyncClient("http://testserver")

    rows = client.get_rows(1, limit=TRUNCATED_PAGE_SIZE, offset=0)

    assert rows["total"] is None
    assert rows["returned_count"] == TRUNCATED_PAGE_SIZE
    assert rows["fetched_count"] == TRUNCATED_PAGE_SIZE
    assert rows["truncated"] is True


def test_backend_unavailable_maps_to_exit_code_3(monkeypatch: Any) -> None:
    monkeypatch.setattr("agentlens_cli.main.AgentLensSyncClient", UnavailableClient)

    result = CliRunner().invoke(cli, ["schema", "info"], env=BASE_ENV)

    assert result.exit_code == EXIT_BACKEND_UNAVAILABLE
    assert "Cannot connect to AgentLens backend" in result.output


def _execution_result(query_id: int) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "execution": {"row_count": 2},
        "columns": [{"name": "value"}],
        "rows": [{"value": 1}, {"value": 2}],
        "fingerprints": {"sql": "s", "schema": "c", "result": "r"},
        "warnings": [],
    }

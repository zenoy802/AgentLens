# Error Cases Manual Test Script

Run backend and frontend locally, then watch the backend log:

```bash
tail -f ~/.agentlens/logs/agentlens.log
```

## 1. SQL syntax error

- Steps: open `/query`, select a valid connection, run `SELECT FROM`.
- Expected UI: query area shows an API error and the page stays mounted.
- Expected log: `Query execution failed` with `SQL_SYNTAX_ERROR`.
- Recovery: fix the SQL and rerun.

## 2. Non-SELECT SQL

- Steps: run `DROP TABLE users` or `UPDATE users SET name='x'`.
- Expected UI: error toast/state with `SQL_NOT_ALLOWED`.
- Expected log: `SQL safety validation failed: code=SQL_NOT_ALLOWED`.
- Recovery: replace with a `SELECT` or `WITH ... SELECT` statement.

## 3. Database connection unavailable

- Steps: stop MySQL or change a saved connection host to an unreachable host, then test or run a query.
- Expected UI: connection test or query request fails clearly; no white screen.
- Expected log: `Connection test failed` or `Query execution failed`.
- Recovery: restore the database or saved connection settings.

## 4. SQL returns zero rows

- Steps: run `SELECT id FROM messages WHERE 1=0`.
- Expected UI: table empty state; labels, annotations, export, and Copy Agent Prompt remain usable.
- Expected log: `Query returned zero rows`.
- Recovery: none.

## 5. SQL returns bytes

- Steps: run `SELECT UNHEX('FF00') AS payload`.
- Expected UI: cell renders a JSON-safe bytes object with base64 content.
- Expected log: `Special SQL field serialization applied` with `bytes`.
- Recovery: none.

## 6. Deleted query URL

- Steps: open `/query/<id>`, delete that query in another tab or through API, refresh the original URL.
- Expected UI: 404-style query-not-found state with a link back to the query list.
- Expected log: `Application error: QUERY_NOT_FOUND`.
- Recovery: open an existing query or create a new query.

## 7. Label field removed in another tab

- Steps: open one query in two tabs; delete a label schema field in tab A; edit that field label in tab B.
- Expected UI: toast with `LABEL_FIELD_NOT_FOUND`; label schema refreshes on the next load.
- Expected log: `Label field not found`.
- Recovery: reload tab B and use the updated schema.

## 8. Invalid annotation color from agent

- Steps: call `POST /api/v1/queries/<id>/annotations` with `"color":"purple"`.
- Expected UI/API: `400 ANNOTATION_INVALID_COLOR`.
- Expected log: request validation failure for annotations.
- Recovery: retry with `red`, `yellow`, `green`, `blue`, or `gray`.

## 9. Clear annotations without filters

- Steps: call `DELETE /api/v1/queries/<id>/annotations` with no query parameters.
- Expected UI/API: `400 ANNOTATION_CLEAR_REQUIRES_FILTER`.
- Expected log: application validation error with allowed filters.
- Recovery: pass `author`, `author_prefix`, `color`, or `annotation_set`.

## 10. WebSocket disconnect and reconnect

- Steps: open a query, stop the backend or block the WS request, then restore it and click Retry in the annotation banner.
- Expected UI: red disconnected dot, yellow reconnecting dot, green connected dot after recovery.
- Expected log: `WebSocket disconnected`, `WebSocket ping/pong timeout`, or `WebSocket connected`.
- Recovery: restore backend/network and retry.

## 11. Copy Agent Prompt selection snapshot failure

- Steps: select rows, then make `POST /selection-snapshots` fail, for example by stopping the backend.
- Expected UI: prompt is not copied; toast shows the API error.
- Expected log: `Selection snapshot create failed` or backend unavailable at the client.
- Recovery: restore backend, reselect rows, copy again.

## 12. Expired selection_id through CLI/MCP

- Steps: create a selection, expire it in SQLite or wait past expiration, then run `agentlens data selection --selection <id>` or MCP `get_selection`.
- Expected UI/API: `SELECTION_EXPIRED`; agents can fall back to `get_rows`.
- Expected log: `Selection snapshot expired`.
- Recovery: create a fresh selection by copying a new Agent Prompt.

## 13. Context Export output directory not writable

- Steps: run `agentlens context export --query <id> --output-dir /root/agentlens-denied` as a normal user.
- Expected CLI: clear error with `CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE`; stdout has no data payload.
- Expected log: client-side error only unless the backend request was reached.
- Recovery: choose a writable directory.

## 14. MCP missing author

- Steps: run `agentlens-mcp --backend-url http://127.0.0.1:8000`.
- Expected process: exits with code `1`; error is printed to stderr; stdout stays reserved for MCP protocol.
- Expected log: no backend log.
- Recovery: add `--author agent:<client-name>`.

## 15. CLI backend unavailable

- Steps: stop backend and run `agentlens schema info`.
- Expected CLI: exit code `3`, clear stderr message, stdout empty for machine-readable commands.
- Expected log: no backend log because the request cannot connect.
- Recovery: start backend or correct `--backend-url`.

## 16. Frontend simulated API 500

- Steps: temporarily raise an unhandled exception in a backend route or use a mock returning `500 INTERNAL_ERROR`.
- Expected UI: toast/error state; ErrorBoundary prevents a white screen for render failures.
- Expected log: `Unhandled exception` and `INTERNAL_ERROR`; traceback only appears in responses when debug is enabled.
- Recovery: remove the temporary failure.

## 17. Trajectory missing role/content/group columns

- Steps: configure trajectory columns, then run SQL missing `role`, `content`, or `group_by`.
- Expected UI: trajectory still renders with fallback `unknown`, `null`, or fallback group and warning text.
- Expected log: `Trajectory aggregation missing roles`, `missing content`, or `group_by column missing`.
- Recovery: correct trajectory config or SQL aliases.

## 18. Annotation orphan and stale badges

- Steps: create an annotation, rerun the query so that row identity or result fingerprint changes.
- Expected UI: drawer/popover shows `Row not in current result` or `Created on previous result`.
- Expected log: annotation list/load succeeds; orphan is not treated as backend error.
- Recovery: none.

## Log Examples

```text
2026-05-24 10:02:11.123 | INFO     | app.core.logging:setup_logging:109 | Logging initialized: file=/Users/you/.agentlens/logs/agentlens.log rotation=10 MB retention=14 days compression=zip | {}
2026-05-24 10:02:15.456 | INFO     | app.services.query_service:create_temporary_query:75 | Temporary query created: query_id=42 connection_id=1 | {}
2026-05-24 10:02:15.489 | INFO     | app.services.query_executor:execute:135 | Query executed: query_id=42 connection_id=1 sql_fingerprint=9b1e... duration_ms=18 row_count=25 truncated=False | {}
2026-05-24 10:02:16.001 | WARNING  | app.services.query_service:execute_and_record:159 | Query execution failed: query_id=42 connection_id=1 sql_fingerprint=4c22... context={'error_type': 'SqlForbiddenError'} | {}
2026-05-24 10:02:17.221 | WARNING  | app.services.query_service:_compute_row_identities:528 | Row identity generation failed; using normalized row JSON hash: query_id=42 row_index=3 error=... | {}
2026-05-24 10:02:18.104 | INFO     | app.services.annotation_service:create:203 | Annotation created: query_id=42 annotation_id=88 author=agent:claude-code color=yellow | {}
```

Sensitive values must be masked:

```text
Authorization: *** password=*** api_key=*** database_url=***
```

## Error Code Inventory

- SQL/DB: `SQL_NOT_ALLOWED`, `SQL_PARSE_ERROR`, `SQL_DANGEROUS_FUNCTION`, `SQL_TIMEOUT`, `SQL_SYNTAX_ERROR`, `SQL_EXECUTION_ERROR`, `DB_INTEGRITY_ERROR`, `DB_OPERATIONAL_ERROR`, `MYSQL_OPERATIONAL_ERROR`, `MYSQL_QUERY_ERROR`.
- Query/View: `QUERY_NOT_FOUND`, `NOT_FOUND`, `ROW_IDENTITY_COLUMN_MISSING`, `ROW_IDENTITY_COLUMN_NULL`, `ROW_IDENTITY_DUPLICATE`.
- Label: `LABEL_FIELD_NOT_FOUND`, `LABEL_ROW_IDENTITY_INVALID`.
- Annotation: `ANNOTATION_INVALID_COLOR`, `ANNOTATION_INVALID_AUTHOR`, `ANNOTATION_NOT_FOUND`, `ANNOTATION_CLEAR_REQUIRES_FILTER`, `ANNOTATION_BATCH_TOO_LARGE`.
- Selection/Context: `SELECTION_NOT_FOUND`, `SELECTION_EXPIRED`, `SELECTION_EMPTY`, `SELECTION_TOO_LARGE`, `CONTEXT_SELECTION_REQUIRED`, `CONTEXT_SELECTION_QUERY_MISMATCH`, `CONTEXT_EXPORT_TRUNCATED`, `CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE`, `CONTEXT_EXPORT_OUTPUT_DIR_NOT_EMPTY`.
- HTTP client/fallback: `HTTP_CLIENT_TIMEOUT`, `HTTP_CLIENT_CONNECT_ERROR`, `INTERNAL_ERROR`.

## Graceful Shutdown Log Example

Stop a local server with `Ctrl+C` or `docker stop`, then confirm the log contains the shutdown sequence:

```text
2026-05-24 10:02:20.000 | INFO     | app.main:lifespan:103 | AgentLens shutdown starting | {}
2026-05-24 10:02:20.011 | INFO     | app.scheduler:shutdown:78 | Scheduler shutdown complete | {}
2026-05-24 10:02:20.018 | INFO     | app.services.query_executor:dispose_all:244 | Query executor engine cache disposed | {}
2026-05-24 10:02:20.022 | INFO     | app.main:lifespan:117 | AgentLens shutdown complete | {}
```

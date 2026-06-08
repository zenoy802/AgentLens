# AgentLens Performance Benchmark

Date: 2026-05-27

Environment:

- macOS, local development workspace
- Frontend production build: `pnpm build`
- Python wheel builds: `python -m build --wheel --no-isolation`
- Docker image: `agentlens:1.0.0`

## UI

| Scenario | Target | Measured |
| --- | ---: | ---: |
| 1000 row result first render | < 2s | Not remeasured in browser in this run |
| 10000 row RowTable scroll FPS | >= 30 FPS | Not remeasured in browser in this run |
| Markdown / JSON / Code preview scroll | No full renderer mount in table cells | Verified by code audit: table cells render plain text preview; full renderers mount only in detail/dialog |
| 200+ annotations RowTable scroll FPS | >= 30 FPS | Not remeasured in browser in this run |
| Batch label 100 rows | < 1s | Optimistic batched store update path verified by code audit; backend timing not remeasured |

Notes:

- `RowTable` uses `@tanstack/react-virtual` with fixed row heights and `overscan: 20`.
- Markdown, JSON, and Code cells no longer mount `MarkdownRenderer`, `JsonRenderer`, or `CodeRenderer` in table preview mode.
- Annotation lookup is indexed by `row_identity` and `row_identity + column_key`; cells do not filter the full annotations list.

## Agent Bridge

| Scenario | Target | Measured |
| --- | ---: | ---: |
| Copy Agent Prompt selection snapshot | < 500ms | 14.1ms direct backend POST for 500 row identities |
| WebSocket annotation visible latency | < 1s | Backend write+broadcast path verified; UI visible latency not remeasured in this run |
| context export 1000 rows | < 1s | 0.0019s median in-process file benchmark |
| context export 10000 rows | < 5s | 0.0134s median in-process file benchmark |
| MCP get_rows limit=100 | < 500ms | 0.001ms median in-process MCP benchmark |
| MCP get_rows limit=500 | < 1s | 0.001ms median in-process MCP benchmark |
| MCP export_context 1000 rows | < 2s | 0.0022s median in-process MCP benchmark |
| MCP add_annotation -> UI visible | < 1s | 11.5ms direct backend POST for one annotation; UI visible latency not remeasured |
| MCP highlight_rows 200 rows | < 1s | 19.2ms direct backend POST for 200-row batch annotation |

Context export verification:

- `agentlens --backend-url http://127.0.0.1:8013 context export --query 1 --output-dir /private/tmp/agentlens-p29-context-export` succeeded against a local smoke backend.
- `rows.jsonl` is written line by line; a 10,000-row smoke export produced exactly 10,000 lines.
- `labels.jsonl` and `annotations.jsonl` are created even when empty.
- `manifest.json` includes `fingerprints`.
- Label export reuses the already loaded row identities and requests labels in 1,000-row chunks.

## Packaging / Deploy

| Scenario | Target | Measured |
| --- | ---: | ---: |
| `pipx install dist/agentlens-1.0.0-py3-none-any.whl` | success | Passed |
| `agentlens run` after pipx install | usable | Passed; `/` and `/api/v1/health` returned 200 |
| `pipx install dist/agentlens_mcp-1.0.0-py3-none-any.whl` | success | Passed |
| `agentlens-mcp --help` after pipx install | usable | Passed |
| `agentlens-mcp --author agent:test` stdout | clean | Passed; no stdout output when stdin closed |
| Docker image size | < 500MB | 102,831,144 bytes (~98.1 MiB) |
| Docker cold start to first healthy check | < 10s | First healthy check completed in ~5.2s after container start |
| Docker non-root user | UID 1000 | Passed |
| Docker Web UI | browser reachable | `GET /` returned 200 on `127.0.0.1:8010` |
| `docker compose up -d` | browser reachable | Passed on `127.0.0.1:8011` with `AGENTLENS_PUBLISHED_PORT=8011`; `GET /` and `GET /api/v1/health` returned 200 |

Out-of-scope metrics for v1:

- External agent provider/model latency, which is controlled by the user's own CLI agent.
- External agent token usage, which AgentLens does not collect.
- Cloud API throughput outside the AgentLens process.

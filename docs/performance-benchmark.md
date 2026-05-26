# AgentLens Performance Benchmark

Date: 2026-05-24

Environment:

- macOS, local development workspace
- Frontend production build: `pnpm build`
- Python wheel builds: `python -m build --wheel --no-isolation`
- Docker image: `agentlens:1.0.0`

## UI

| Scenario | Target | Measured |
| --- | ---: | ---: |
| 1000 row result first render | < 2s | Not remeasured with real MySQL fixture in this run |
| 10000 row RowTable scroll FPS | >= 30 FPS | Not remeasured with real MySQL fixture in this run |
| Markdown / JSON / Code preview scroll | No full renderer mount in table cells | Verified by code audit: table cells render plain text preview; full renderers mount only in detail/dialog |
| 200+ annotations RowTable scroll FPS | >= 30 FPS | Not remeasured with real MySQL fixture in this run |
| Batch label 100 rows | < 1s | Store update path changed to one batched optimistic write; backend timing not remeasured |

Notes:

- `RowTable` uses `@tanstack/react-virtual` with fixed row heights and `overscan: 20`.
- Markdown, JSON, and Code cells no longer mount `MarkdownRenderer`, `JsonRenderer`, or `CodeRenderer` in table preview mode.
- Annotation lookup is indexed by `row_identity` and `row_identity + column_key`; cells do not filter the full annotations list.

## Agent Bridge

| Scenario | Target | Measured |
| --- | ---: | ---: |
| Copy Agent Prompt selection snapshot | < 500ms | API path verified; no real 10000-row browser fixture in this run |
| WebSocket annotation visible latency | < 1s | Debounced invalidate path verified by code audit |
| context export 1000 rows | < 1s | 0.003s synthetic client/file benchmark |
| context export 10000 rows | < 5s | 0.027s synthetic client/file benchmark |
| MCP get_rows limit=100 | < 500ms | 0.0ms synthetic in-process client benchmark |
| MCP get_rows limit=500 | < 1s | 0.1ms synthetic in-process client benchmark |
| MCP export_context 1000 rows | < 2s | 0.003s synthetic in-process client benchmark |
| MCP add_annotation -> UI visible | < 1s | 0.0ms synthetic write path; UI WebSocket latency not remeasured |
| MCP highlight_rows 200 rows | < 1s | 0.1ms synthetic write path |

Context export verification:

- `rows.jsonl` is written line by line.
- `labels.jsonl` and `annotations.jsonl` are created even when empty.
- `manifest.json` includes `fingerprints`.
- Label export reuses the already loaded row identities and no longer reruns the full query only to discover labels.

## Packaging / Deploy

| Scenario | Target | Measured |
| --- | ---: | ---: |
| `pipx install dist/agentlens-1.0.0-py3-none-any.whl` | success | Passed |
| `agentlens run` after pipx install | usable | Passed; `/` and `/api/v1/health` returned 200 |
| `pipx install dist/agentlens_mcp-1.0.0-py3-none-any.whl` | success | Passed |
| `agentlens-mcp --help` after pipx install | usable | Passed |
| `agentlens-mcp --author agent:test` stdout | clean | Passed; no stdout output when stdin closed |
| Docker image size | < 500MB | 417MB |
| Docker cold start to first healthy check | < 10s | First healthcheck at ~5.1s after container start |
| Docker non-root user | UID 1000 | Passed |
| Docker Web UI | browser reachable | `GET /` returned 200 on `127.0.0.1:8010` |
| `docker compose up -d` | browser reachable | Blocked locally by existing process already bound to `127.0.0.1:8000` |

Removed metrics:

- Built-in LLM analysis token latency
- LLM streaming first-token latency
- LLM provider analysis history throughput

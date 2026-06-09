# v0.1.0 Release Checklist

## Code quality

- [x] backend ruff check pass
- [x] backend mypy pass
- [x] backend pytest pass
- [x] frontend typecheck pass
- [x] frontend lint pass
- [x] frontend build pass
- [x] cli tests pass
- [x] mcp tests pass

## Manual QA

- [ ] Create MySQL connection
- [ ] Run SELECT query
- [ ] Render markdown/json/code cells
- [ ] Trajectory single view
- [ ] Trajectory compare view
- [ ] Create label schema
- [ ] Batch label rows
- [ ] Export CSV/Excel
- [ ] Create annotation manually
- [ ] Copy Agent Prompt without selection
- [ ] Copy Agent Prompt with selection
- [ ] CLI data rows
- [ ] CLI context export
- [ ] CLI annotate
- [ ] MCP get_rows
- [ ] MCP add_annotation
- [ ] WebSocket annotation update visible

## Error cases

- [ ] docs/error-cases.md tested
- [ ] SQL error handled
- [ ] DB disconnected handled
- [ ] Query deleted 404 handled
- [ ] Selection expired handled
- [ ] WebSocket reconnect handled
- [ ] CLI backend unavailable handled
- [ ] MCP missing author handled

## Performance

- [ ] 1000 rows render < 2s
- [ ] 10000 rows scroll >= 30 FPS
- [ ] 200+ annotations scroll >= 30 FPS
- [ ] batch label 100 rows < 1s
- [x] context export 10000 rows < 5s
- [x] Docker healthy < 10s
- [x] Docker image < 500MB

## Packaging

- [x] pipx install dist/agentlens-0.1.0-py3-none-any.whl
- [x] agentlens run works
- [x] agentlens --help works
- [x] pipx install dist/agentlens_mcp-0.1.0-py3-none-any.whl
- [x] agentlens-mcp --help works
- [x] docker build agentlens:0.1.0
- [x] docker compose up -d works

## Docs

- [x] README renders correctly
- [x] getting-started complete
- [x] agent-bridge doc complete
- [x] cli doc complete
- [x] mcp doc complete
- [x] faq updated
- [x] changelog updated
- [x] all docs links valid

## Release

- [x] version in pyproject.toml is 0.1.0
- [x] version in package.json is 0.1.0 if applicable
- [ ] git tag v0.1.0
- [ ] GitHub Release drafted
- [x] Docker image tagged agentlens:0.1.0 and agentlens:latest

## Recorded Data

- pytest coverage: backend 90%; CLI 79%; MCP 72%
- mypy clean: yes, `cd backend && mypy app`
- frontend typecheck clean: yes, `cd frontend && pnpm typecheck`
- Docker image size: 102,831,144 bytes, about 98.1 MiB
- Docker cold start time: app startup log 56 ms; first `/api/v1/health` check returned 200 within the manual verification window
- 10000 rows FPS: not remeasured in this release validation
- context export 10000 rows time: 0.0134s median from the recorded benchmark
- MCP get_rows latency: 0.001ms median in-process from the recorded benchmark

## Not Completed In This Pass

- Manual MySQL/UI QA remains unchecked because it requires an external MySQL trajectory dataset and browser walkthrough.
- Error cases remain unchecked because the full manual error script was not rerun in this pass.
- UI FPS metrics remain unchecked because browser performance recording was not rerun in this pass.
- `git tag v0.1.0` and GitHub Release draft remain unchecked pending code review and final release approval.

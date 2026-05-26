# AgentLens MCP Server

`agentlens-mcp` lets MCP clients such as Claude Code, Claude Desktop, and Cursor access
AgentLens query data through stdio. The server is a separate Python process and calls the
AgentLens backend over HTTP.

## Install

```bash
pipx install dist/agentlens_mcp-1.0.0-py3-none-any.whl
```

Development mode:

```bash
pip install -e packages/agentlens-client
pip install -e mcp_server
```

The server requires a fixed author:

```bash
agentlens-mcp --backend-url http://127.0.0.1:8000 --author agent:claude-code
```

## Claude Code

Project `.mcp.json`:

```json
{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": [
        "--backend-url", "http://127.0.0.1:8000",
        "--author", "agent:claude-code"
      ]
    }
  }
}
```

## Claude Desktop

```json
{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": [
        "--backend-url", "http://127.0.0.1:8000",
        "--author", "agent:claude-desktop"
      ]
    }
  }
}
```

## Cursor

```json
{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": [
        "--backend-url", "http://127.0.0.1:8000",
        "--author", "agent:cursor"
      ]
    }
  }
}
```

## Recommended Workflow

1. User queries data in the AgentLens UI.
2. User clicks Copy Agent Prompt.
3. If the prompt includes `selection_id`, the agent first calls `get_selection(selection_id)`.
4. For small data, the agent calls `get_rows`.
5. For large data, local processing, or repeatable analysis, the agent calls `export_context`.
6. After analysis, the agent writes findings back to the UI with `add_annotation` or
   `highlight_rows`.

## Tools

- `get_agent_guide`: static integration guide for agents.
- `get_backend_info`: backend version, limits, colors, and fixed author.
- `list_queries`: discover saved and temporary queries.
- `get_query`: query metadata, SQL, view config, labels schema, and column metadata when available.
- `get_rows`: bounded live row access with `limit` and `offset`.
- `get_trajectories`: bounded trajectory summaries or one trajectory by `session_id`.
- `get_labels`: read-only human labels.
- `get_annotations` / `list_annotations`: inspect existing visual annotations.
- `get_selection`: read a temporary UI selection snapshot.
- `export_context`: materialize query or selection context into `~/.agentlens/contexts/...`.
- `add_annotation`: add one row or cell annotation.
- `highlight_rows`: batch-create row annotations through the backend batch endpoint.
- `clear_annotations`: clear annotations with required filters.

## Notes

- stdout is reserved for MCP stdio protocol messages. Logs and startup validation errors go to
  stderr.
- The server does not call LLMs, open folders, sync workspaces, or expose a web terminal.
- `get_rows` is capped at 500 rows per call. Use `export_context` for large analysis.
- Annotation author is fixed by `--author`; tool callers cannot override it.

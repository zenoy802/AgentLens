# AgentLens MCP

`agentlens-mcp` 是 AgentLens 的 MCP stdio server。它让 Claude Code、Claude Desktop、Cursor 等支持 tool calling 的 agent 读取 AgentLens 数据并写回 annotations。

## 安装

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/zenoy802/AgentLens.git
cd AgentLens
pipx run --spec build pyproject-build --outdir dist mcp_server
pipx install dist/agentlens_mcp-0.1.0-py3-none-any.whl
agentlens-mcp --help
```

本地开发：

```bash
pip install -e packages/agentlens-client
pip install -e mcp_server
```

## backend-url 约定

默认 backend URL 是 `http://127.0.0.1:8000`。如果 AgentLens 运行在其他端口，需要显式传：

```bash
agentlens-mcp --backend-url http://127.0.0.1:8000 --author agent:claude-code
```

## author 约定

`--author` 必填，用于标识 annotation 来源：

- `agent:claude-code`
- `agent:claude-desktop`
- `agent:cursor`
- `agent:codex`
- `agent:aider`

author 必须匹配 `^[a-zA-Z0-9_:.-]+$`。MCP tool caller 不能覆盖 server 启动时指定的 author。

## Claude Code .mcp.json

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

## Claude Desktop config

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

## Cursor config

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

## Generic MCP config

```json
{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": [
        "--backend-url", "http://127.0.0.1:8000",
        "--author", "agent:<client-name>"
      ]
    }
  }
}
```

## Tools 列表

- `get_agent_guide`: 返回静态 agent 使用指南
- `get_backend_info`: backend version、限制、颜色和固定 author
- `list_queries`: 查询 saved / temporary queries
- `get_query`: 查询 metadata、SQL、view config、label schema 和可用 column 信息
- `get_rows`: 按 `limit` / `offset` 读取 query rows
- `get_trajectories`: 读取 trajectory summaries 或指定 session
- `get_labels`: 读取 human labels
- `get_annotations`: 读取 visual annotations
- `get_selection`: 读取 UI selection snapshot
- `export_context`: 导出 query 或 selection context 到本地文件
- `add_annotation`: 写入单条 row/cell annotation
- `highlight_rows`: 批量写入 row annotation
- `clear_annotations`: 按 filter 清理 annotations

## 推荐工作流

1. 用户在 UI 中运行 query。
2. 用户可选中 rows。
3. 用户点击 Copy Agent Prompt。
4. agent 从 prompt 中读取 `query_id` 和可选 `selection_id`。
5. 小数据用 `get_rows` 或 `get_selection`。
6. 大数据用 `export_context`。
7. 结论用 `add_annotation` 或 `highlight_rows` 写回。

## 常见错误

### Missing author

现象：

```text
agentlens-mcp: error: --author is required. Example: agentlens-mcp --author agent:claude-code
```

处理：在 MCP config 中添加 `--author agent:<client-name>`。

### Backend unavailable

现象：tool 调用返回连接错误。

处理：

- 确认 `agentlens run` 正在运行。
- 确认 `--backend-url` 端口正确。
- 浏览器打开 `http://127.0.0.1:8000/api/v1/health`。

### stdout 被污染

MCP stdio 的 stdout 只能用于协议消息。不要在 wrapper script 里 `echo` 日志到 stdout；日志应写 stderr。

### get_rows 数据太大

MCP live access 有单次返回限制。大数据分析使用：

```text
export_context(query_id=42, scope="all")
```

或带 selection：

```text
export_context(query_id=42, selection_id="sel_xxx", scope="selection")
```

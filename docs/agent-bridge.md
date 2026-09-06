# Agent Bridge

Agent Bridge 是 AgentLens 0.1.1 的 agent-assisted 分析方式。AgentLens 提供可视化、selection snapshot、CLI/MCP live access、context export 和 annotation write-back；推理与分析交给你自己的 CLI agent。

## 为什么没有内置 LLM 分析？

AgentLens 0.1.1 的选择是：

- 不绑架用户 LLM provider。
- 不绑架分析方式。
- 不在 AgentLens 内保存 provider key 或 prompt editor。
- 不承诺由 AgentLens 调用 OpenAI、Claude 或其他云 API。
- AgentLens 负责数据可视化与结构化写回。
- 用户自己的 CLI agent 负责推理和分析。

这让同一份 query data 可以被 Claude Code、Codex、aider、Cursor 或自定义 agent 用各自的配置处理。

## 核心工作流

1. 在 UI 中运行 query。
2. 可选：选中 rows。
3. 点击 Copy Agent Prompt。
4. 粘贴到 Claude Code / Codex / aider。
5. agent 通过 MCP/CLI 读取数据。
6. agent 使用 `add_annotation` / `highlight_rows` 写回。
7. UI 实时显示 annotation。

## Live Access vs Context Export

Live access 每次从后端读取当前数据：

```bash
agentlens data rows --query 42 --limit 100
```

适合：

- 小数据
- 分页查看
- 最新数据
- 快速 inspect columns、labels、annotations

Context Export 把当前 query 或 selection materialize 为本地文件：

```bash
agentlens context export --query 42 --selection sel_xxx
```

适合：

- 大数据
- 本地文件分析
- 可复现分析
- 使用 shell、Python、jq、grep 等工具处理 rows.jsonl

## Color conventions

- red: hard failures / errors
- yellow: suspicious / warnings
- green: verified-correct / success
- blue: informational
- gray: neutral

## Copy Agent Prompt 模板

UI 会根据当前语言生成 prompt。中文模板如下：

```text
AgentLens 数据上下文：
- query_id：<query_id>
- selection_id：<selection_id, optional>
- 已选择行数：<selected_count, optional>

请使用 AgentLens MCP 工具或 `agentlens` CLI 先自行查看这个查询的数据和字段。不要预设分析目标、分析模式或打标方式。
回答语言要求：请始终使用中文回复我，包括澄清问题、分析结论和标注说明。

建议的数据入口：
- MCP 查询信息：get_query(query_id=<query_id>)
- MCP 样例行：get_rows(query_id=<query_id>, limit=100, offset=0)
- CLI 查询信息：agentlens query show <query_id>
- CLI 字段信息：agentlens schema columns --query <query_id>
- CLI 样例行：agentlens data rows --query <query_id> --limit 100
- MCP 选中行：get_selection("<selection_id>")
- CLI 选中行：agentlens data selection --selection <selection_id>

数据量较大时：
- MCP：export_context(query_id=<query_id>, selection_id="<selection_id>", scope="selection")
- CLI：agentlens context export --query <query_id> --selection <selection_id>

查看数据结构和可用字段后，请先问我想分析、排查或标注什么问题，再继续。
```

没有 selection 时，prompt 会省略 selection 行，并推荐导出全量 query context：

```text
export_context(query_id=<query_id>, scope="all")
agentlens context export --query <query_id>
```

## CLI write-back 示例

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --color yellow \
  --severity warning \
  --text "Suspicious reasoning step"
```

```bash
agentlens highlight \
  --query 42 \
  --rows id1,id2,id3 \
  --color red \
  --note "Same failure mode"
```

## MCP write-back 示例

Agent 可调用：

- `add_annotation`
- `highlight_rows`
- `clear_annotations`

MCP server 启动时必须指定固定 author，例如 `agent:claude-code`。Tool caller 不能覆盖这个 author，便于 UI 区分来源。

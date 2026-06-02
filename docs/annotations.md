# Annotations

Annotation 是 AgentLens 的反向可视化机制。人类或外部 agent 可以把发现写回到某个 query 的某行或某个单元格，UI 会用颜色、高亮和 drawer 展示这些 finding。

## Annotation 是什么

Annotation 绑定 `query_id + row_identity`。它不是严格的 query execution artifact。如果 `row_identity` 稳定，annotation 可跨 query rerun 保留。如果 `row_identity` 不存在于当前结果，annotation 会成为 orphan。

Annotation 常用于：

- 标出 hard failure
- 标出 suspicious reasoning step
- 解释某个 tool call 结果异常
- 给外部 agent finding 加视觉提示
- 临时高亮一批相似 bad cases

## 与 Label 的区别

Label 是结构化人工标注。
Annotation 是人类或 agent 写入的视觉提示。
两者都基于 `query_id + row_identity`，但语义不同，不要混用。

对比：

- Label 适合统计、筛选、导出和长期 review schema。
- Annotation 适合 explain、高亮、agent finding 和实时协作。
- Label 通常字段稳定；annotation 可以更自由。
- Annotation 可按 author、color、annotation_set 清理。

## row-level annotation

只传 `row_identity`，不传 `column_key`：

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --color red \
  --text "This row is a hard failure"
```

UI 会在整行维度展示高亮和 annotation 入口。

## cell-level annotation

传 `column_key`：

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --column content \
  --color yellow \
  --text "The reasoning step is unsupported"
```

UI 会在对应单元格展示提示。

## author

author 标识来源：

- `human`
- `agent:claude-code`
- `agent:cursor`
- `agent:codex`
- `agent:aider`

MCP server 的 author 在启动时固定。CLI 可以用 `--author` 或 `AGENTLENS_AUTHOR` 指定。

## color

支持颜色：

- red: hard failures / errors
- yellow: suspicious / warnings
- green: verified-correct / success
- blue: informational
- gray: neutral

## severity

支持 severity：

- `info`
- `warning`
- `error`

severity 用于表达问题严重程度；color 用于视觉分组。两者可以同时使用。

## annotation_set

`annotation_set` 用于给一批 annotation 命名，例如：

- `nightly-review`
- `agent-pass-2026-06-01`
- `tool-error-audit`

清理时可以按 set 删除：

```bash
agentlens annotation clear --query 42 --set nightly-review
```

## stale / orphan

Annotation 写入时可以携带 fingerprints：

- `sql_fingerprint`
- `schema_fingerprint`
- `result_fingerprint`

当 query rerun 后：

- row_identity 仍存在，但 fingerprints 不同，UI 可提示 stale。
- row_identity 不存在于当前结果，UI 可提示 orphan。

orphan 不是错误。它通常表示 query 条件变化、数据变化或 row identity 不稳定。

## fingerprints

Fingerprints 用于判断 annotation 和当前结果是否属于同一次数据形态：

- SQL fingerprint: SQL 文本变化
- schema fingerprint: column/render shape 变化
- result fingerprint: row identity 集合变化

稳定 row identity 是 annotation 跨 rerun 保留的关键。

## WebSocket 实时刷新

Annotation WebSocket：

```text
/ws/queries/{query_id}/annotations
```

当 CLI/MCP/API 写入或删除 annotation 时，UI 会通过 WebSocket 收到事件并刷新。

## Clear agents

推荐通过 author prefix 清理 agent 写回内容：

```bash
agentlens annotation clear --query 42 --author-prefix agent:
```

也可以按颜色或 annotation_set 清理：

```bash
agentlens annotation clear --query 42 --color yellow
agentlens annotation clear --query 42 --set nightly-review
```

后端拒绝无 filter 的清理请求，避免误删。

## 人类手动 annotation

人类可在 UI 中添加 annotation，用于临时 review 或给 agent 提供线索。手动 annotation 建议 author 使用 `human` 或团队约定名称。

## agent annotation

Agent 通过 CLI/MCP 写回 annotation。推荐流程：

1. agent 先读取 rows、labels、annotations。
2. 分析后只写入与当前任务相关的 finding。
3. 使用 color convention。
4. text 写具体证据，不写泛泛判断。
5. 批量结果用 `highlight_rows`，单个解释用 `add_annotation`。

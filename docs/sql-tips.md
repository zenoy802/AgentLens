# SQL Tips for Agent Trajectory Analysis

AgentLens 不要求固定 schema。你可以用 SQL 把任意已有表整理成适合行级表格、trajectory 视图、打标和 agent-assisted 分析的结果集。

## 推荐 trajectory 表 schema

如果你还在设计 trajectory 存储表，推荐 message-level rows：

```sql
CREATE TABLE agent_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(128) NOT NULL,
  message_index INT NOT NULL,
  role VARCHAR(32) NOT NULL,
  content MEDIUMTEXT,
  tool_calls JSON,
  metadata JSON,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_session_message (session_id, message_index),
  KEY idx_session_order (session_id, message_index),
  KEY idx_created_at (created_at)
);
```

字段建议：

- `session_id`: Trajectory `group_by` 字段
- `message_index`: 会话内稳定排序字段
- `role`: system / user / assistant / tool
- `content`: 原始 markdown 或文本
- `tool_calls`: tool call 请求和结果
- `metadata`: model、latency、token、trace id、eval id 等扩展信息
- `created_at`: 时间排序和筛选字段

## 基础查询

```sql
SELECT
  CONCAT(session_id, ':', message_index) AS row_id,
  session_id,
  message_index,
  role,
  content,
  tool_calls,
  metadata,
  created_at
FROM agent_messages
WHERE created_at >= '2026-01-01'
ORDER BY session_id, message_index
LIMIT 1000;
```

Trajectory 视图通常配置为：

- Group By: `session_id`
- Role Column: `role`
- Content Column: `content`
- Tool Calls Column: `tool_calls`
- Order By: `message_index` 或 `created_at`

## row_identity 建议

如果你希望 labels / annotations 在 query rerun 后仍然稳定，请在 SQL 中返回稳定 identity 列，例如：

```sql
SELECT
  CONCAT(session_id, ':', message_index) AS row_id,
  session_id,
  message_index,
  role,
  content,
  created_at
FROM messages
ORDER BY session_id, message_index;
```

说明：

- 返回稳定 identity 列后，需要在 View Config 中把 Row Identity Column 设置为该列名，例如 `row_id`。
- 未设置 Row Identity Column 时，AgentLens 使用规范化 row JSON hash。
- 指定并保存稳定 Row Identity Column 后，label 和 annotation 更容易跨 rerun 保留。
- 推荐 identity 不依赖排序 offset，不使用随机值，不包含易变化的内容摘要。
- 对 message-level rows，`session_id + message_index` 通常比自增 id 更容易跨环境迁移。

## 关联 eval results

评测结果通常单独存储。可以在 SQL 中 JOIN，把失败原因和分数带入同一结果集：

```sql
SELECT
  CONCAT(m.session_id, ':', m.message_index) AS row_id,
  m.session_id,
  m.message_index,
  m.role,
  m.content,
  m.tool_calls,
  m.created_at,
  e.eval_name,
  e.score,
  e.pass,
  e.failure_reason
FROM agent_messages AS m
JOIN eval_results AS e
  ON e.session_id = m.session_id
WHERE e.pass = 0
ORDER BY m.session_id, m.message_index
LIMIT 2000;
```

这样可以在 Table 视图中筛选 bad cases，并在 Trajectory 视图中查看完整上下文。

## JSON_EXTRACT 示例

如果原始表把 message 存成 JSON，可以用 MySQL JSON 函数抽取渲染字段：

```sql
SELECT
  JSON_UNQUOTE(JSON_EXTRACT(payload, '$.session_id')) AS session_id,
  CAST(JSON_EXTRACT(payload, '$.message_index') AS UNSIGNED) AS message_index,
  JSON_UNQUOTE(JSON_EXTRACT(payload, '$.role')) AS role,
  JSON_UNQUOTE(JSON_EXTRACT(payload, '$.content')) AS content,
  JSON_EXTRACT(payload, '$.tool_calls') AS tool_calls,
  JSON_EXTRACT(payload, '$.metadata') AS metadata,
  created_at
FROM agent_events
WHERE JSON_UNQUOTE(JSON_EXTRACT(payload, '$.event_type')) = 'message'
ORDER BY session_id, message_index
LIMIT 1000;
```

保留完整 JSON 字段也有价值：

```sql
SELECT
  id AS row_id,
  session_id,
  event_type,
  payload,
  created_at
FROM agent_events
ORDER BY created_at DESC
LIMIT 500;
```

把 `payload` 配置成 JSON 渲染后，可以在 cell detail 中展开查看。

## LIMIT / ORDER BY / 索引建议

建议每条查询都显式写：

- `ORDER BY`: 保证 rerun 顺序稳定
- `LIMIT`: 保护 UI 和数据库
- 时间范围或 session 范围: 降低扫描量

索引建议：

```sql
CREATE INDEX idx_messages_session_order
  ON agent_messages (session_id, message_index);

CREATE INDEX idx_messages_created_at
  ON agent_messages (created_at);

CREATE INDEX idx_eval_session
  ON eval_results (session_id);
```

大结果集分析建议：

- UI 中先用 `LIMIT 1000` 做观察和渲染配置。
- 需要 10000 行级别分析时使用 Context Export。
- 更大规模先用 SQL 聚合、过滤或抽样，再导出给本地 agent 工具处理。

## 常见 anti-pattern

- 用 `SELECT *` 长期保存为命名查询，导致 schema 变化难以追踪。
- 不写 `ORDER BY`，导致 row_identity fallback hash 难以和人工判断对应。
- 把整条 trajectory 聚合成一个巨大 JSON 字段，导致打标只能落在整行，不能落到 message-level。
- 在 production 数据库上使用高权限账号。

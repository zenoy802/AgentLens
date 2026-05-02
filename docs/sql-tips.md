# SQL Tips for Agent Trajectory Analysis

## 构造 trajectory 友好的 SQL

优先让 SQL 返回“一行一条 message/step”的结构，并包含稳定的会话字段、角色字段、内容字段和排序字段：

```sql
SELECT
  session_id,
  message_id,
  role,
  content,
  tool_calls,
  created_at
FROM agent_messages
WHERE created_at >= '2026-01-01'
ORDER BY session_id, created_at, message_id;
```

建议：

- `session_id` 用于 Trajectory `group_by`。
- `role` 用于区分 system/user/assistant/tool。
- `content` 保留原始 markdown 或文本。
- `created_at` 或 `message_index` 用于稳定排序。
- `message_id` 可作为 row identity，便于后续打标稳定关联。

## JSON 字段处理

如果 MySQL 字段是 JSON，尽量在 SQL 中提取 AgentLens 需要直接渲染或聚合的字段：

```sql
SELECT
  session_id,
  JSON_UNQUOTE(JSON_EXTRACT(payload, '$.role')) AS role,
  JSON_UNQUOTE(JSON_EXTRACT(payload, '$.content')) AS content,
  JSON_EXTRACT(payload, '$.tool_calls') AS tool_calls,
  created_at
FROM agent_events
ORDER BY session_id, created_at;
```

保留完整 JSON 字段也有价值，可以在表格中设置为 JSON 渲染，方便展开查看：

```sql
SELECT
  session_id,
  event_type,
  payload,
  created_at
FROM agent_events
ORDER BY session_id, created_at;
```

## 关联评测结果表

评测 bad case 通常分散在 trajectory 表和 evaluation 表中。建议用 SQL join 提前把评测结论、分数和失败原因带到结果中：

```sql
SELECT
  m.session_id,
  m.message_id,
  m.role,
  m.content,
  m.created_at,
  e.eval_name,
  e.score,
  e.pass,
  e.failure_reason
FROM agent_messages AS m
JOIN eval_results AS e
  ON e.session_id = m.session_id
WHERE e.pass = 0
ORDER BY m.session_id, m.created_at;
```

这样可以在 Table 视图中筛选 bad case，在 Trajectory 视图中直接查看完整上下文。

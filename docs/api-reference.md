# API Reference

运行时完整 OpenAPI 可见于 `/docs`。AgentLens 0.1.0 无鉴权，设计为 localhost-only 使用。所有 API Base URL 为 `/api/v1`，错误响应统一为：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "detail": {}
  }
}
```

分页响应统一为：

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "total_pages": 0
  }
}
```

## health

- `GET /api/v1/health`: backend status、version、uptime

## connections

- `GET /api/v1/connections`
- `POST /api/v1/connections`
- `GET /api/v1/connections/{connection_id}`
- `PATCH /api/v1/connections/{connection_id}`
- `DELETE /api/v1/connections/{connection_id}`
- `POST /api/v1/connections/{connection_id}/test`

连接密码加密存储。业务数据库应使用只读账号。

## queries

- `GET /api/v1/queries`
- `POST /api/v1/queries`
- `GET /api/v1/queries/{query_id}`
- `PATCH /api/v1/queries/{query_id}`
- `DELETE /api/v1/queries/{query_id}`
- `POST /api/v1/queries/{query_id}/promote`
- `POST /api/v1/queries/{query_id}/execute`
- `POST /api/v1/execute`

`/execute` 用于创建临时 query 并执行。`/queries/{query_id}/execute` 用于 rerun 已有 query。

## view configs

- `GET /api/v1/queries/{query_id}/view-config`
- `PUT /api/v1/queries/{query_id}/view-config`

View config 包含 field renders、table config 和 trajectory config。

## labels

Label schema:

- `GET /api/v1/queries/{query_id}/label-schema`
- `PUT /api/v1/queries/{query_id}/label-schema`

Label records:

- `GET /api/v1/queries/{query_id}/labels`
- `POST /api/v1/queries/{query_id}/labels/query`
- `POST /api/v1/queries/{query_id}/labels`
- `POST /api/v1/queries/{query_id}/labels/batch`
- `DELETE /api/v1/queries/{query_id}/labels/{record_id}`

Label records 以 `query_id + row_identity + field_key` 唯一。

## annotations

- `POST /api/v1/queries/{query_id}/annotations`
- `POST /api/v1/queries/{query_id}/annotations/batch`
- `GET /api/v1/queries/{query_id}/annotations`
- `DELETE /api/v1/queries/{query_id}/annotations/{annotation_id}`
- `DELETE /api/v1/queries/{query_id}/annotations`

`DELETE /annotations` 支持 filter：

- `author`
- `author_prefix`
- `color`
- `annotation_set`

无 filter 的 clear 请求会被拒绝。

## selection snapshots

- `POST /api/v1/queries/{query_id}/selection-snapshots`
- `GET /api/v1/selections/{selection_id}`
- `DELETE /api/v1/selections/{selection_id}`

Selection snapshot 用于 Copy Agent Prompt，把 UI 当前选中行保存为短期可引用 id。

## WebSocket annotations

```text
/ws/queries/{query_id}/annotations
```

连接后服务端发送：

```json
{"type": "connected", "query_id": 42}
```

服务端会发送 ping，客户端应回复 pong。annotation 创建、批量创建、删除和清理会广播给当前 query 的订阅者。

## export endpoints

- `POST /api/v1/queries/{query_id}/export`

支持格式：

- `csv`
- `xlsx`

可选择是否包含 labels。Context Export 由 CLI/MCP client 基于 API 读取数据后在本地写 JSONL 文件。

## trajectories

- `POST /api/v1/queries/{query_id}/trajectories`

根据 view config 中的 trajectory config 聚合 rows。

## render rules

- `GET /api/v1/render-rules`
- `POST /api/v1/render-rules`
- `GET /api/v1/render-rules/{rule_id}`
- `PATCH /api/v1/render-rules/{rule_id}`
- `DELETE /api/v1/render-rules/{rule_id}`

全局字段渲染规则用于给新查询生成 render 和 trajectory 配置建议。

## query history

- `GET /api/v1/query-history`

查询执行历史用于审计和调试。

## admin

- `GET /api/v1/admin/info`
- `POST /api/v1/admin/cleanup`

Admin API 仍是 localhost-only 工具接口。

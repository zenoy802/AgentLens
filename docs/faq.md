# FAQ

## 1. 支持哪些数据库？

v1 支持 MySQL。未来可扩展 PostgreSQL / SQLite / ClickHouse。

## 2. 数据会上传到云服务吗？

不会。AgentLens 本身只连接本地或用户指定数据库，并把 metadata 存在本地 SQLite。

外部 agent 是否调用云 LLM 取决于你自己的 Claude Code / Codex / aider / Cursor 配置，不由 AgentLens 控制。

## 3. 为什么没有内置 LLM 分析？

v1 选择 Agent Bridge，让用户使用自己的 CLI agent 和 provider。AgentLens 负责 SQL 查询、可视化、打标、context export 和 annotation 写回。

## 4. Copy Agent Prompt 是什么？

它会把当前 `query_id`、可选 `selection_id`、推荐 MCP/CLI 调用复制到剪贴板。你把它粘贴给外部 agent，agent 再读取数据并写回 annotations。

## 5. CLI 和 MCP 有什么区别？

CLI 面向 shell 和脚本，例如 `agentlens data rows --query 42`。

MCP 面向支持 tool calling 的 agent，例如 Claude Code、Claude Desktop 和 Cursor。

## 6. Live access 和 Context Export 有什么区别？

Live access 每次读后端当前数据，是 read by reference。

Context Export 生成本地文件快照，是 read by value，适合大数据和可复现分析。

## 7. Annotation 和 Label 有什么区别？

Label 是结构化标注，用于筛选、统计和导出。

Annotation 是视觉提示和 agent finding，用于高亮、解释和反向可视化。

## 8. Annotation 重跑 query 后还在吗？

取决于 `row_identity` 是否稳定。稳定 row identity 可以跨 rerun 保留 annotation。不匹配时 annotation 可能 stale 或 orphan。

## 9. Docker 版能用 Claude Code 吗？

Docker 适合启动 AgentLens 服务和浏览器 UI。高级 agent 分析建议 pipx 本机安装 CLI/MCP，因为 Claude Code 通常需要在本机直接调用 `agentlens-mcp`。

## 10. 能分析超过 1 万行吗？

UI 目标支持 1 万行。更大规模建议 SQL `LIMIT`、筛选、聚合，或 context export 后用本地工具处理。

## 11. 打标数据怎么备份？

备份 metadata 数据目录中的 `metadata.db`，或使用：

```bash
agentlens export-config --output agentlens-config.json
```

导出配置不会包含 plaintext secrets。

## 12. 支持多人协作吗？

v1 是单用户 localhost-only。多人、权限和团队协作属于后续规划。

## 13. 能嵌入到我的产品吗？

v1 架构预留嵌入能力，但不提供正式嵌入 SDK。v2 规划 iframe / SDK / 嵌入模式。

## 14. MCP author 是什么？

author 用于区分 annotation 来源，例如 `agent:claude-code`、`agent:cursor`、`agent:codex`。MCP server 启动时必须指定固定 author。

## 15. Agent 写错 annotation 怎么办？

可以在 UI 中删除，也可以用 CLI/MCP clear：

```bash
agentlens annotation clear --query 42 --author-prefix agent:
```

更精确的做法是按 `annotation_set`、`author` 或 `color` 清理。

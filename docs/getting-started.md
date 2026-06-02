# Getting Started

本教程帮助新用户从一个已有 MySQL trajectory 表开始，完成一次 SQL 查询、渲染、打标、Copy Agent Prompt、agent annotation 写回和导出流程。

## 1. AgentLens 是什么

AgentLens 是一个 SQL-first LLM trajectory 可视化与打标工作台。它只读连接你的 MySQL 数据库，不要求修改 Agent 代码。你用 SQL 取出任意 schema 的 trajectory 数据，再在 UI 中切换行级表格、单 trajectory 视图和多 trajectory 对比视图。

AgentLens v1 不内置 provider 配置、prompt editor 或托管式分析流水线。推理分析通过 Agent Bridge 交给你自己的 CLI agent，例如 Claude Code、Codex、aider 或 Cursor。AgentLens 负责数据展示、context export、selection snapshot 和 annotation 写回。

## 2. 准备 MySQL 只读账号

建议为 AgentLens 单独创建只读账号：

```sql
CREATE USER 'agentlens_ro'@'%' IDENTIFIED BY 'change-me';
GRANT SELECT ON your_database.* TO 'agentlens_ro'@'%';
FLUSH PRIVILEGES;
```

不要使用有写权限的生产账号。AgentLens 后端会拦截非 SELECT/WITH SQL，但数据库账号仍应遵循最小权限原则。

推荐 trajectory 表至少包含：

- `session_id`: 一次 agent run 或对话的稳定 id
- `message_index`: 会话内稳定顺序
- `role`: system / user / assistant / tool
- `content`: 文本或 markdown 内容
- `tool_calls`: JSON tool call 信息
- `metadata`: JSON 额外上下文
- `created_at`: 事件时间

## 3. Docker 启动

从源码目录构建本地镜像：

```bash
docker build -t agentlens:1.0.0 .
```

启动 AgentLens：

```bash
docker run -d \
  -p 127.0.0.1:8000:8000 \
  -v agentlens-data:/data \
  --name agentlens \
  agentlens:1.0.0
```

打开 http://127.0.0.1:8000。

如果你使用的是已发布到 registry 的镜像，请把 `agentlens:1.0.0` 替换为实际发布镜像名。Docker 适合快速体验、只用浏览器查询和查看数据。高级 Agent Bridge 工作流建议使用 pipx 本机安装 CLI/MCP，因为 Claude Code、Codex、aider 或 Cursor 通常需要直接启动本机 `agentlens` / `agentlens-mcp` 命令。

## 4. pipx 启动

```bash
pipx install agentlens
agentlens run
```

打开 http://127.0.0.1:8000。默认 metadata、日志和 context export 文件写入 `~/.agentlens`。如需指定目录：

```bash
agentlens run --data-dir ~/.agentlens-dev
```

## 5. 创建连接并测试

进入 Connections 页面，点击新建连接，填写：

- name: 连接名，例如 `local-mysql`
- host / port: MySQL 地址和端口
- database: trajectory 数据库名
- username / password: 只读账号
- default timeout / row limit: 默认查询超时和行数上限

保存后点击测试。连接密码会加密存储在本地 metadata SQLite 中。

## 6. 执行第一条 SQL

进入 Query 页面，选择连接并执行：

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
ORDER BY session_id, message_index
LIMIT 1000;
```

结果会显示在 Table 视图。`row_id` 是可用作稳定 row identity 的列，后续 labels 和 annotations 可以基于它关联。
注意：只在 SQL 中返回 `row_id` 还不够。你还需要在 View Config 中把 Row Identity Column 设置为 `row_id` 并保存视图配置。未设置时，AgentLens 会使用规范化 row JSON hash；如果 `content`、`metadata` 等字段变化，rerun 后 labels 和 annotations 可能无法继续匹配。

## 7. 配置字段渲染与 Row Identity

在列头菜单中为字段设置渲染类型：

- `content`: Markdown
- `tool_calls`: JSON
- `metadata`: JSON
- `created_at`: Timestamp
- SQL、Python、JSON 字符串字段: Code

全局字段渲染规则可以在 Settings 中配置，新查询会自动应用建议，单个查询仍可覆盖。

如果 SQL 返回了稳定 identity 列，例如上一步的 `row_id`，同时在 View Config 中设置：

- Row Identity Column: `row_id`

保存 view config 后，labels、selection snapshots 和 annotations 才会使用这列作为稳定行身份。

## 8. 保存命名查询

执行 SQL 后点击保存或 promote，把临时查询保存为命名查询。命名查询会保留：

- SQL
- 连接关系
- view config
- label schema
- labels
- annotations

保存后 URL 中的 query id 可被 CLI/MCP 使用。

## 9. 切换到 Trajectory 视图

打开 View Config，配置：

- Group By: `session_id`
- Role Column: `role`
- Content Column: `content`
- Tool Calls Column: `tool_calls`
- Order By: `message_index` 或 `created_at`

保存后切换到 Trajectory tab。单条 trajectory 会显示气泡视图；多条 trajectory 可进入对比视图。

## 10. 创建 label schema

打开 Labeling 面板，创建结构化字段。例如：

```json
{
  "fields": [
    {
      "key": "case_quality",
      "label": "Case Quality",
      "type": "single_select",
      "options": [
        { "value": "good", "label": "Good" },
        { "value": "bad", "label": "Bad" },
        { "value": "unclear", "label": "Unclear" }
      ]
    },
    {
      "key": "failure_modes",
      "label": "Failure Modes",
      "type": "multi_select",
      "options": [
        { "value": "tool_error", "label": "Tool error" },
        { "value": "hallucination", "label": "Hallucination" },
        { "value": "missed_instruction", "label": "Missed instruction" },
        { "value": "timeout", "label": "Timeout" }
      ]
    },
    {
      "key": "review_note",
      "label": "Review Note",
      "type": "text"
    }
  ]
}
```

## 11. 标注 bad cases

在结果表格中逐行标注：

- `case_quality = bad`
- `failure_modes = hallucination`
- `review_note = assistant cited a tool result that did not exist`

Label 是结构化人工标注，适合后续筛选、统计和导出。

## 12. 批量打标

勾选多行后使用 Batch Label，把同一个字段值写入所有选中行。常见用法：

- 一次性标注一批 `case_quality = bad`
- 给同一失败模式打 `failure_modes = tool_error`
- 对抽样数据添加同一 review batch 标记

## 13. 使用 Copy Agent Prompt

用户操作：

- 选中 3 行
- 点击 Copy Agent Prompt
- 粘贴到 Claude Code

AgentLens 会在后端创建 selection snapshot，并把 `query_id`、可选 `selection_id`、推荐 MCP/CLI 调用一起放进 prompt。

agent 可能使用：

- `get_selection(selection_id)`
- `get_rows(query_id)`
- `export_context(query_id, selection_id)`
- `highlight_rows(...)`
- `add_annotation(...)`

## 14. 在 Claude Code 中调用 AgentLens MCP/CLI

安装 CLI 和 MCP：

```bash
pipx install agentlens
pipx install agentlens-mcp
```

Claude Code 项目 `.mcp.json`：

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

CLI 等价读取：

```bash
agentlens data rows --query 42 --limit 100
agentlens data selection --selection sel_xxx
agentlens context export --query 42 --selection sel_xxx
```

## 15. 查看 agent 写回的 annotations

agent 可以写回行级或单元格 annotation：

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --column content \
  --color yellow \
  --severity warning \
  --text "Suspicious reasoning step"
```

也可以批量高亮：

```bash
agentlens highlight \
  --query 42 \
  --rows id1,id2,id3 \
  --color red \
  --note "Same failure mode"
```

UI 会通过 WebSocket 实时刷新 annotation。Annotation 是视觉提示和 finding，不等同于 label。

## 16. 导出 CSV/Excel

在 Query 页面打开 Export，选择 CSV 或 Excel，并选择是否包含 labels。导出文件适合：

- 离线 review
- 与团队共享 bad case
- 导入 notebook 或 BI 工具
- 保存 release 前评估结果

Context Export 与 CSV/Excel 不同：Context Export 面向本地 agent 分析，会输出 JSONL 文件和 `AGENTLENS_CONTEXT.md`。

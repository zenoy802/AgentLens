# AgentLens

> 面向 Agent 开发者的 SQL-first LLM trajectory 可视化、打标与 agent-assisted 分析工作台。
> 不侵入 Agent 代码，直连你的 SQL 数据库，并把分析自由交给你自己的 CLI agent。

[![Docker](https://img.shields.io/badge/docker-ready-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Version](https://img.shields.io/badge/version-0.1.0-orange)]()

## ✨ 核心特性

- 🔌 直连 SQL 数据库：无需修改 Agent 代码，MySQL 只读账号即可接入
- 🔍 SQL-first 查询：任意 schema 返回结果都能渲染与分析
- 📊 Trajectory 专用视图：行级表格、单 trajectory 气泡视图、多 trajectory 对比
- 🧩 专业化渲染：Markdown / JSON / 代码 / timestamp / tool calls
- 🏷️ 灵活打标：支持单选、多选、文本字段与批量打标
- 🤖 Agent Bridge：通过 CLI/MCP 连接 Claude Code、Codex、aider、Cursor 等外部 agent
- 🎯 反向可视化：外部 agent 可把发现写回为行/单元格 annotation
- 📦 Context Export：大数据分析时导出 rows.jsonl / labels.jsonl / annotations.jsonl 给本地 agent 使用
- 📤 导出无忧：CSV/Excel 导出含打标结果
- 🐳 本地优先：localhost-only，Docker + pipx 双分发

## 📸 截图

### SQL 查询与行级表格
<!-- TODO: add screenshot: docs/screenshots/sql-table.png -->

### Trajectory 气泡视图
<!-- TODO: add screenshot: docs/screenshots/trajectory-view.png -->

### 打标与批量打标
<!-- TODO: add screenshot: docs/screenshots/labeling.png -->

### Agent annotation 反向可视化
<!-- TODO: add screenshot: docs/screenshots/agent-annotations.png -->

### Copy Agent Prompt
<!-- TODO: add screenshot: docs/screenshots/copy-agent-prompt.png -->

## 🚀 快速开始

### Docker

从源码目录构建本地镜像：

```bash
docker build -t agentlens:0.1.0 .
```

启动 AgentLens：

```bash
docker run -d \
  -p 127.0.0.1:8000:8000 \
  -v agentlens-data:/data \
  --name agentlens \
  agentlens:0.1.0
```

浏览器访问 http://127.0.0.1:8000。

如果你使用的是已发布到 registry 的镜像，请把 `agentlens:0.1.0` 替换为实际发布镜像名。Docker 适合快速体验和本地 viewer mode。高级 Agent Bridge 工作流建议使用 pipx 本机安装，因为 CLI/MCP 需要作为本机进程被 Claude Code、Codex、aider 或 Cursor 调用。

### pipx 安装

```bash
python -m build
pipx install dist/agentlens-0.1.0-py3-none-any.whl
agentlens run
```

浏览器访问 http://127.0.0.1:8000。

注意：PyPI 上的 `agentlens` 包名已被其他项目占用，当前不要使用 `pipx install agentlens`。公开发布到新的 PyPI 包名后，再把上面的 wheel 路径替换为实际包名。

### MCP Server 安装

```bash
python -m build --outdir dist mcp_server
pipx install dist/agentlens_mcp-0.1.0-py3-none-any.whl
agentlens-mcp --help
```

### 本地开发

```bash
# 后端 + CLI
pip install -e "backend[dev]"
pip install -e .
```

```bash
# 前端
cd frontend
pnpm install
pnpm dev
```

## 🤖 Agent Bridge 快速示例

1. 在 AgentLens 中运行 SQL。
2. 选中几行 bad cases。
3. 点击 Copy Agent Prompt。
4. 粘贴到 Claude Code / Codex / aider。
5. Agent 使用 MCP/CLI 读取数据并写回 annotations。
6. 在 AgentLens 表格中查看高亮和解释。

CLI 示例：

```bash
agentlens data rows --query 42 --limit 100
agentlens context export --query 42
agentlens annotate --query 42 --row <row_identity> --color yellow --text "Suspicious reasoning step"
```

MCP 示例：

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

## 🏗️ 架构概览

```text
┌────────────┐
│  Browser   │
│  React UI  │
└─────┬──────┘
      │ HTTP / WebSocket
      ▼
┌──────────────┐       SQL        ┌────────────┐
│ FastAPI      │ ───────────────> │ 用户 MySQL │
│ Metadata DB  │   read-only      └────────────┘
│ SQLite       │
└─────┬────────┘
      │
      │ Local HTTP
      ▼
┌──────────────┐
│ agentlens CLI│
└─────┬────────┘
      │
      │ MCP stdio
      ▼
┌──────────────┐
│ agentlens-mcp│
└─────┬────────┘
      │
      ▼
┌──────────────────────────────┐
│ Claude Code / Codex / aider  │
│ 用户自己的 CLI agent         │
└──────────────────────────────┘
```

## 📖 文档

- 快速上手教程：[docs/getting-started.md](docs/getting-started.md)
- SQL 编写最佳实践：[docs/sql-tips.md](docs/sql-tips.md)
- 打标使用指南：[docs/labeling-guide.md](docs/labeling-guide.md)
- Agent Bridge 使用指南：[docs/agent-bridge.md](docs/agent-bridge.md)
- CLI 使用指南：[docs/cli.md](docs/cli.md)
- MCP 配置指南：[docs/mcp.md](docs/mcp.md)
- Annotation 与反向可视化：[docs/annotations.md](docs/annotations.md)
- API 参考：[docs/api-reference.md](docs/api-reference.md)
- 性能基准：[docs/performance-benchmark.md](docs/performance-benchmark.md)
- 常见问题：[docs/faq.md](docs/faq.md)

## 🛠️ 技术栈

- Backend: Python 3.11 · FastAPI · SQLAlchemy 2.0 · Pydantic v2
- Frontend: React 18 · Vite · TypeScript · shadcn/ui · TanStack Table · TanStack Query
- Storage: SQLite metadata · 用户 MySQL trajectory data
- Agent Bridge: CLI · MCP · JSONL Context Export · WebSocket annotation updates

## 🤝 贡献

欢迎提 Issue 和 PR。贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 License

MIT

# AgentLens

## LLM Trajectory Analyzer

AgentLens is a local-first SQL query and visualization tool for Agent developers. It connects to an existing MySQL database with read-only access, runs SELECT-only SQL, and renders the result as a row table or a trajectory view without requiring any Agent code changes.

## 核心特性

- 只读连接已有 MySQL 数据库，不侵入 Agent 运行时代码。
- SQL 查询任意 trajectory schema，并自动保存临时查询历史。
- 行级表格支持 text、markdown、JSON、code、timestamp 等字段渲染。
- ViewConfig 可保存列渲染、表格配置和 Trajectory 聚合配置。
- Trajectory 视图按 group/role/content/order 字段聚合并渲染对话流。

## 截图

> TODO: 添加连接管理页面截图。

> TODO: 添加 SQL 查询 + 表格视图截图。

> TODO: 添加 Trajectory 单视图截图。

## 快速开始

### Docker 方式

```bash
docker compose up -d
```

打开 http://localhost:8000。

数据会保存在 Docker volume `agentlens-data` 中，容器内路径为 `/data`。

### 本地开发方式

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
AGENTLENS_DATA_DIR="$HOME/.agentlens" python -m uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

本地开发时后端默认 http://127.0.0.1:8000，前端默认 http://localhost:5173。

## 数据源准备

建议为 AgentLens 单独创建只读 MySQL 账号：

```sql
CREATE USER 'agentlens_ro'@'%' IDENTIFIED BY 'change-me';
GRANT SELECT ON your_database.* TO 'agentlens_ro'@'%';
FLUSH PRIVILEGES;
```

不要使用有写权限的生产账号。AgentLens 后端也会拦截非 SELECT/WITH SQL，但数据库账号仍应遵循最小权限原则。

Windows 用户本地数据目录可使用 `%USERPROFILE%\.agentlens`；macOS/Linux 可使用 `$HOME/.agentlens`。

## FAQ

**AgentLens 会修改我的业务数据库吗？**
不会。它只保存连接、查询、视图配置等 metadata 到本地 SQLite；对业务数据库只执行 SELECT-only 查询。

**目前支持哪些数据库？**
MVP 只支持 MySQL。PostgreSQL、SQLite、ClickHouse 属于后续扩展。

**为什么 Trajectory 视图需要配置字段？**
Agent trajectory 的 schema 不固定，需要指定 `group_by`、`role_column`、`content_column` 和可选排序字段，AgentLens 才能把 SQL 行聚合成对话流。

## 更多文档

- [Getting Started](docs/getting-started.md)
- [SQL Tips](docs/sql-tips.md)
- [MVP Manual Checklist](docs/mvp-checklist.md)
- [贡献指南](docs/contributing.md)

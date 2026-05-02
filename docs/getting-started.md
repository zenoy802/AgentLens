# Getting Started

本教程从一个已有 MySQL trajectory 表开始，走通 AgentLens MVP 的基本链路。

## 1. 准备只读 MySQL 账号

在 MySQL 中创建只读账号，并只授予目标库的 SELECT 权限：

```sql
CREATE USER 'agentlens_ro'@'%' IDENTIFIED BY 'change-me';
GRANT SELECT ON your_database.* TO 'agentlens_ro'@'%';
FLUSH PRIVILEGES;
```

> 截图 TODO: MySQL 账号和权限准备。

## 2. 启动 AgentLens

Docker:

```bash
docker compose up -d
```

本地开发:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
AGENTLENS_DATA_DIR="$HOME/.agentlens" python -m uvicorn app.main:app --reload
```

```bash
cd frontend
pnpm install
pnpm dev
```

打开 http://localhost:8000（Docker）或 http://localhost:5173（本地开发）。

> 截图 TODO: AgentLens 首页。

## 3. 创建连接并测试

进入 Connections 页面，点击“新建你的第一个连接”，填写 host、port、database、username、password。保存后点击“测试”，确认连接成功。

> 截图 TODO: 新建连接表单。

## 4. 写第一条 SQL

进入 Query 页面，选择连接，编写 SELECT SQL：

```sql
SELECT
  session_id,
  role,
  content,
  created_at
FROM agent_messages
ORDER BY session_id, created_at;
```

点击 Run，结果会显示在 Table 视图。

> 截图 TODO: SQL 编辑器和表格结果。

## 5. 配置字段渲染

在表格列头菜单中把长文本列切换为 markdown、JSON 或 code 渲染。修改会立即作用于当前结果，并让 ViewConfigBar 显示 dirty 状态。

> 截图 TODO: 列渲染菜单。

## 6. 保存为命名查询

执行 SQL 后点击“另存为”，填写查询名称和描述。命名查询会保留 SQL、视图配置和后续打标数据。

> 截图 TODO: 保存临时查询 Dialog。

## 7. 切换到 Trajectory 视图

点击 ViewConfigBar 中的 Trajectory 配置，选择：

- Group By: `session_id`
- Role Column: `role`
- Content Column: `content`
- Order By: `created_at`

保存视图后切换到 Trajectory tab。如果查询结果聚合为单条 trajectory，会展示对话气泡流。

> 截图 TODO: Trajectory 配置和单视图。

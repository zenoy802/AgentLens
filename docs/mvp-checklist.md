# MVP Manual Test Checklist

在 Docker 容器和本地开发环境各跑一遍关键路径。没有真实 MySQL 时，先准备一个只读测试库。

- [ ] Docker 执行 `docker compose up -d` 后容器正常启动。
- [ ] 浏览器访问 http://localhost:8000 能看到 AgentLens 前端。
- [ ] `/api/v1/health` 返回 `status=ok`。
- [ ] `/api/v1/admin/info` 返回 data_dir、db_path、uptime、scheduler_jobs、connections_count、named_queries_count。
- [ ] 创建 MySQL 连接并保存成功。
- [ ] 测试连接成功，页面显示连接状态。
- [ ] `/connections` 无连接时显示“新建你的第一个连接”空状态。
- [ ] 写 SELECT SQL 执行成功，并显示行级表格。
- [ ] 危险 SQL（UPDATE/DROP/DELETE）被拒绝并显示统一错误状态。
- [ ] `/query` 未执行时显示空状态，并可点击“从模板开始”插入示例 SQL 注释。
- [ ] Cmd/Ctrl+Enter 可以执行 SQL。
- [ ] 修改列渲染为 markdown 后立即生效。
- [ ] 点击行打开详情抽屉，Esc 能关闭抽屉。
- [ ] 保存视图后刷新页面，列渲染和表格配置能恢复。
- [ ] Cmd/Ctrl+S 可以保存视图，并显示“视图已保存” toast。
- [ ] SQL 编辑器 Collapse/Expand 可用，刷新后折叠状态保持。
- [ ] 配置 trajectory_config 后切换到 Trajectory 视图，单条 trajectory 正常渲染。
- [ ] `/queries` 无查询时显示“去写第一条 SQL”空状态。
- [ ] 大结果集（>=5000 行）表格滚动流畅，无明显卡顿。
- [ ] 删除连接后，其关联查询、视图配置和打标数据被级联清理。

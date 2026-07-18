# 长轨迹对比视图性能优化记录

日期：2026-07-18

## 开发背景

AgentLens 的 Trajectory 对比视图需要同时展示多条 trajectory 及其 messages。本次使用一组专门构造的本地 MySQL 性能数据验证极端场景：

- 10 条 trajectory；
- 每条 trajectory 包含 21 条 message，共 210 条；
- 每条 message 的正文为 10,000 个 `cl100k_base` token；
- 数据表为 `agentlens_trajectory_performance_mock`；
- 本地 AgentLens 命名查询为 `/query/21`。

性能数据由 `backend/scripts/seed_trajectory_performance.py` 生成并写入本机 MySQL，不依赖 Docker。测试查询和 trajectory 字段配置见 [performance-benchmark.md](./performance-benchmark.md#large-trajectory-fixture)。

优化前，Trajectory 对比页面存在明显的主线程阻塞：

- 选择或取消一条 trajectory 约需 16.6 秒；
- 打开全屏约需 23.8 秒；
- 页面滚动测试超过 30 秒仍无法完成；
- 浏览器 DOM 节点约 734,534 个，全屏后约 1,321,928 个；
- 页面文本约 9.2 MB。

在这个状态下，全选、反选、逐条勾选、全屏和纵向滚动均难以正常交互。

## 定位过程

### 1. 建立可重复的真实基准

首先启动本机 MySQL 和源码版本的 AgentLens，并通过 Playwright 对 `/query/21` 的以下操作分别计时：

- 全选、反选；
- 左侧列表和列头的逐条选择；
- 打开、关闭全屏；
- trajectory 列纵向滚动。

同时记录 DOM 节点数、Markdown renderer 数量、文本体积和 Long Task，以区分数据库查询耗时与浏览器渲染耗时。MySQL 查询本身仅需十几毫秒，主要瓶颈位于前端渲染和 React 更新后的浏览器布局、绘制阶段。

### 2. 找到折叠态仍完整渲染的问题

消息虽然在 UI 上显示为折叠状态，但折叠容器内仍挂载完整 Markdown 或 JSON renderer，只通过固定高度和渐变遮罩隐藏超出内容。每次选择状态或全屏状态变化都会让浏览器处理所有长正文产生的大量 DOM。

此外，lazy renderer 的 `Suspense` fallback 也会暂时输出完整正文，无法降低首次挂载成本。

### 3. 优化折叠消息的渲染路径

Trajectory viewer 调整为：

- 默认内置渲染路径的折叠消息仅渲染最多 1,200 字符的纯文本预览；
- 只有展开消息时才挂载 Markdown、JSON 和 tool calls 的完整 renderer；
- `Suspense` fallback 同样使用有界预览；
- 对对象和数组使用可提前终止的流式预览生成逻辑，避免先执行完整 `JSON.stringify`；
- 自动折叠判断使用有界估算，达到阈值后立即停止遍历；
- 通过 `content-visibility: auto` 跳过视口外 message 的布局和绘制工作；
- 保留自定义 renderer 的兼容性，并增加独立的 `renderCollapsedContent` 扩展点，防止折叠预览绕过调用方的脱敏或内容处理逻辑。

如果调用方只提供 `renderContent` 而未提供 `renderCollapsedContent`，折叠态仍沿用自定义 renderer。这是为了保持兼容性和脱敏语义；需要轻量折叠路径的自定义调用方应同时提供 `renderCollapsedContent`。

### 4. 发现浏览器仍在运行旧构建

首次优化后，带 cache-busting 参数的页面已经达到低延迟，但用户直接访问 `/query/21` 时仍观察到约 10 秒延迟。截图显示折叠 message 中仍是完整 Markdown 排版，而不是新实现的纯文本预览。

Playwright 进一步确认：

- 直接 URL 实际加载旧入口包 `index-e0ekk1_-.js`；
- 当前构建入口应为 `index-Btewgdbq.js`；
- 后端返回 SPA `index.html` 时未声明缓存策略，浏览器复用了旧入口 HTML；
- 带 hash 的新静态资源已存在，但旧 HTML 仍引用旧 hash，因此前端修复没有进入用户当前页面。

这也解释了为什么自动化基准与用户浏览器体验一度不一致：两者实际运行的不是同一份前端构建。

### 5. 修复 SPA 入口缓存策略

后端现在对以下所有 SPA HTML 入口统一返回：

```text
Cache-Control: no-cache, no-store, must-revalidate
```

覆盖路径包括：

- `/`；
- `/index.html`；
- `/query/21` 等 SPA fallback 路径。

普通静态文件和带内容 hash 的 `/assets/*` 保持原有行为。这样部署新构建后，浏览器不会继续使用引用旧资源 hash 的入口 HTML。

此前已经缓存旧 HTML 的浏览器需要执行一次强制刷新；收到新响应头后，后续直接访问原始 URL 会加载当前入口包。

## 优化结果

清除一次旧缓存后，通过原始 URL `http://127.0.0.1:8000/query/21` 加载当前生产构建，页面状态为：

- 210 个有界正文预览；
- 折叠态 Markdown renderer 数量为 0；
- DOM 节点约 3,922 个；
- 数据库仍返回完整 210 条数据，不减少 trajectory 或 message 数量。

针对用户截图中标出的控件，Playwright 实测如下：

| 操作 | 优化后延迟 |
| --- | ---: |
| 逐条取消 trajectory | 40 ms |
| 逐条选择 trajectory | 41 ms |
| 反选 | 43 ms |
| 全选 | 58 ms |
| 打开全屏 | 66 ms |
| 关闭全屏 | 25 ms |

滚动基准的最大帧间隔约 9.2 ms。与优化前十几至二十几秒的阻塞相比，选择、全屏和滚动已恢复为可即时响应的交互。

## 验证与审查

完成的自动化检查包括：

- 前端 TypeScript typecheck；
- 前端 ESLint，包括 trajectory viewer package 源码；
- 前端 production build；
- 后端静态前端路由测试；
- 后端 Ruff；
- 后端 mypy strict；
- Playwright 原始 URL、选择、全屏和滚动回归测试；
- `curl` 验证 SPA fallback 的缓存响应头；
- 独立 code review，多轮修复自定义 renderer、超大对象预览、自动折叠估算和 JSON 转义问题，最终无 P1/P2 遗留问题。

相关提交：

- `e869601 test: add large trajectory performance fixture`
- `4292524 fix: optimize long trajectory interactions`
- `e78c386 fix: prevent stale SPA entry caching`

## 后续回归要点

后续修改 Trajectory viewer 或静态资源服务时，应至少验证：

1. 折叠的长 message 不挂载完整 Markdown、JSON 或 tool calls renderer；
2. 展开单条 message 后仍能显示完整富文本内容；
3. 自定义 renderer 可以单独提供安全的折叠渲染逻辑；
4. 10 条 trajectory 全选、反选、逐条选择和全屏操作不出现秒级 Long Task；
5. SPA HTML 不复用陈旧入口，带 hash 的静态资源仍能正常加载。

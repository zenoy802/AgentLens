# AgentLens CLI

`agentlens` CLI 用于本机 live access、context export、annotation write-back 和启动 AgentLens 服务。

## 安装

```bash
pipx install agentlens
agentlens --help
```

本地开发：

```bash
pip install -e packages/agentlens-client
pip install -e cli
```

统一包开发：

```bash
pip install -e .
pip install -e "backend[dev]"
pip install -e packages/agentlens-client
pip install -e "cli[dev]"
```

根目录 `agentlens` 包用于验证统一 wheel 的运行时组合；lint/test 依赖仍由各组件的 `dev` extra 提供。

## backend URL 配置

默认后端地址是 `http://127.0.0.1:8000`。可通过三种方式配置：

```bash
agentlens --backend-url http://127.0.0.1:8000 schema info
```

```bash
export AGENTLENS_BACKEND_URL=http://127.0.0.1:8000
```

`~/.agentlens/cli.toml`：

```toml
[backend]
url = "http://127.0.0.1:8000"
timeout = 30
```

## author 配置

Annotation write-back 需要 author。CLI 默认 author 是 `human`，agent 推荐显式传：

```bash
agentlens --author agent:codex annotate --query 42 --row <row_identity> --color yellow --text "Suspicious"
```

也可以使用：

```bash
export AGENTLENS_AUTHOR=agent:codex
```

author 必须匹配 `^[a-zA-Z0-9_:.-]+$`。

## live access commands

data commands = live read by reference。每次命令都会读取后端当前状态。

```bash
agentlens schema info
agentlens schema columns --query 42
agentlens schema labels --query 42
```

```bash
agentlens query list
agentlens query show 42
agentlens query exec --connection local-mysql --sql "SELECT * FROM traces LIMIT 10"
agentlens query rerun 42
```

```bash
agentlens data rows --query 42 --limit 100
agentlens data rows --query 42 --format jsonl --output rows.jsonl
agentlens data rows --query 42 --format jsonl --output rows.jsonl --metadata-output rows.meta.json
agentlens data trajectories --query 42
agentlens data trajectories --query 42 --session session-1
agentlens data labels --query 42
agentlens data annotations --query 42 --author-prefix agent:
agentlens data selection --selection sel_xxx
```

Connection 只读查看：

```bash
agentlens connection list
agentlens connection show local-mysql
```

## context export commands

context export = snapshot read by value。它会把当前 query 或 selection 写成可复现的本地文件集。

```bash
agentlens context export --query 42
agentlens context export --query 42 --selection sel_xxx
agentlens context export --query 42 --selection sel_xxx --scope selection
agentlens context export --query 42 --target claude-code
agentlens context export --query 42 --output-dir ./agentlens-context
```

典型输出：

- `AGENTLENS_CONTEXT.md`
- `manifest.json`
- `columns.json`
- `rows.jsonl`
- `labels.jsonl`
- `annotations.jsonl`

## annotation write-back

创建单个 annotation：

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --color yellow \
  --text "Suspicious"
```

单元格级 annotation：

```bash
agentlens annotate \
  --query 42 \
  --row <row_identity> \
  --column content \
  --color red \
  --severity error \
  --title "Unsupported claim" \
  --text "The claim is not supported by tool output"
```

批量高亮：

```bash
agentlens highlight \
  --query 42 \
  --rows id1,id2,id3 \
  --color red \
  --note "Same failure mode"
```

读取和清理：

```bash
agentlens annotation list --query 42
agentlens annotation clear --query 42 --author-prefix agent:
agentlens annotation clear --query 42 --set nightly-review
```

clear 至少需要一个 filter，避免误删整批 annotation。

## schema info

```bash
agentlens schema info
```

返回：

- backend version
- CLI version
- annotation colors
- severity values
- author pattern
- recommended workflow

## 服务与配置备份

统一 `agentlens` 包包含服务命令：

```bash
agentlens run
agentlens run --host 127.0.0.1 --port 8000 --data-dir ~/.agentlens
agentlens cleanup --dry-run
agentlens export-config --output agentlens-config.json
```

`import-config` 在 v1 中是预留命令。

## output formats

全局或单命令可指定：

```bash
agentlens --format pretty query list
agentlens data rows --query 42 --format json
agentlens data rows --query 42 --format jsonl --output rows.jsonl
agentlens data rows --query 42 --format csv --output rows.csv
```

支持格式：

- `json`: 默认，输出完整 envelope
- `jsonl`: 输出 records，每行一条
- `csv`: 输出 records CSV
- `pretty`: 面向人工阅读

## stdout/stderr 约定

- 成功的数据 payload 输出到 stdout，或 `--output` 指定文件。
- 错误信息输出到 stderr。
- JSON/JSONL/CSV 模式下，stdout 尽量保持机器可解析。
- `agentlens-mcp` 的 stdout 保留给 MCP stdio 协议，不要混用 CLI 输出约定。

## exit codes

- `0`: 成功
- `1`: 通用 CLI/client 错误
- `2`: Click 参数错误
- `3`: backend unavailable
- `4`: backend business error 或 CLI 防误操作错误
- `5`: backend server error

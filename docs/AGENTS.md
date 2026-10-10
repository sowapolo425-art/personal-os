# 接入不同 Agent

只需连接 MCP 服务，不需要把模型 API 密钥交给 Personal OS。
先安装 Python 包并初始化资料库，再在 Agent 中配置绝对路径。
所有配置仅为示例；项目不会修改你的现有 Agent 设置。

## Codex

官方 MCP 页面支持 CLI 添加 stdio 服务，以及 `mcp_servers` 配置。

```powershell
codex mcp add personal-os -- D:\tools\personal-os\.venv\Scripts\python.exe -m personal_os.cli --vault D:\PersonalData\my-vault serve
```

或在你当前使用的 Codex 配置中加入：

```toml
[mcp_servers.personal-os]
command = 'D:\tools\personal-os\.venv\Scripts\python.exe'
args = ['-m', 'personal_os.cli', '--vault', 'D:\PersonalData\my-vault', 'serve']
```

请用 Codex 的 MCP 列表检查连接，确认出现十一个工具（四个原有工具与七个提取/分析工具）。
来源：[OpenAI 官方 MCP 文档](https://developers.openai.com/codex/mcp/)，2026-10-10 已读取。
本文档示例已按官方格式编写，并核对了本机 `codex mcp add --help`，尚未在实际 Codex 客户端注册或调用。

## Claude Code

在当前版本确认 `claude mcp add --help` 支持的语法后，添加 stdio 服务：

```powershell
claude mcp add --transport stdio personal-os -- D:\tools\personal-os\.venv\Scripts\python.exe -m personal_os.cli --vault D:\PersonalData\my-vault serve
```

使用 `/mcp` 或该版本的 MCP 管理界面检查服务。已核对本机 `claude mcp add --help` 的 stdio 参数，此命令仍是配置示例，尚未做客户端实测。
官方入口：[Claude Code MCP](https://code.claude.com/docs/en/mcp)。本次抓取该页面失败，安装前请对照当前版本帮助。

## ZCode / WorkBuddy / 其他 Agent

在 MCP 管理界面选择**本地 / stdio**，填写：

| 字段 | 示例 |
|---|---|
| 名称 | personal-os |
| 启动程序 / command | Python 虚拟环境中的 python.exe 绝对路径 |
| 参数 / args | `-m`, `personal_os.cli`, `--vault`, 资料库绝对路径, `serve` |
| 传输方式 | stdio |

若客户端接受 `mcpServers` JSON，使用 README 示例。若只有 URL/SSE/HTTP 接入，首版无法直接使用，不能填一个虚构 localhost 地址。本地适配桥接列在路线图中。

ZCode 与 WorkBuddy 的当前版本、具体配置页面和 stdio 支持尚未验证，不声明品牌级兼容通过。它们是目标接入工具。

## 通用验收

1. 客户端能列出 `capture_record`、`search_records`、`read_record`、`propose_record`、`ingest_conversation`、`list_conversations`、`mark_conversation_processed`、`propose_insight`、`prepare_analysis`、`list_extraction_sources`、`mark_source_processed`。
2. 用虚构内容写入一条记录，再搜索并读取同一 ID。
3. 提交个人档案草稿，确认正式档案还未变化。
4. 用户在本地审核草稿，批准后再读取正式档案。
5. 重启客户端，仍能检索到原记录。

macOS/Linux 将 Python 路径改为 `.venv/bin/python`；参数保持一致。路径有空格时，JSON 参数中保留为一个字符串，命令行中加引号。启动服务前关闭同一资料库的其他测试进程。

排错：找不到工具时先检查 Python 路径与安装环境；提示 init first 时核对资料库路径；不要给 stdio 服务添加 stdout 日志；stdio 服务被 Agent 启动后通常一直等待输入，这是正常状态。

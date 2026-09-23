# MCP 客户端、容器与 Agent Harness 配置

[English](client-setup.md)

本项目支持本地 MCP stdio 传输。安装一次后，让客户端启动 `am-mcp` 即可。服务端只在
stdout 输出协议消息，统一使用 UTF-8，运行时零第三方依赖，并为每个工具声明只读、写入或
破坏性提示。

## 从描述到歌单

推荐的使用方式是直接描述结果，例如：

> 做一张 20 首的周日清晨歌单：温暖的灵魂乐、民谣和安静爵士，以 1970 年代至今为主，
> 不要现场版，能量缓慢上升，最后柔和落地。

MCP 客户端中的模型把描述转成充足的候选池，并直接对照用户原话比较候选；
stdio 服务通过 `am_status` 和 `am_resolve_candidates` 把候选落到 Apple Music 真实元数据，
再以 `am_create_playlist` dry-run 校验最终匹配后写入。服务端不调用另一家模型，
也不需要额外的 LLM API key。

支持 MCP Prompts 的客户端可选择 `create_playlist_from_description`，填写描述以及可选的
歌单名、曲目数和回复语言。没有 Prompt UI 也不影响核心能力：直接在聊天中发送相同描述，
服务端 instructions 和工具说明包含同一套工作流。

CLI 是配套的登录、诊断、脚本、体检和手动维护入口；正常 MCP 使用不应要求用户自己整理
`"歌名 - 艺人"` 数组。

## 1. 安装与登录

```bash
pip install apple-music-playlists
am-playlist status
am-playlist login
```

如果已安装 `uv`，也可以直接运行同一个 PyPI 正式版，无需永久安装：

```bash
uvx --from apple-music-playlists am-playlist status
uvx --from apple-music-playlists am-playlist login
```

`login` 只需交互一次。不同系统用户、WSL、远程主机和容器不会自动共享宿主机配置；配置
路径和三种登录方式见 [SETUP.md](../SETUP.md)。注册后重启客户端，先让它调用 `am_status`，
不要用“创建歌单”来测试连接。

## 2. 通用 JSON 配置

Claude Desktop、Cursor、Windsurf、Gemini CLI 和许多 Agent Harness 都接受下面的结构：

```json
{
  "mcpServers": {
    "applemusic": {
      "command": "am-mcp",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

如果希望由 `uvx` 按需解析并缓存已发布的包，可使用官方 MCP Registry 中的安装配置：

```json
{
  "mcpServers": {
    "applemusic": {
      "command": "uvx",
      "args": ["--from", "apple-music-playlists", "am-mcp"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

如果 GUI 客户端找不到命令，填 `where am-mcp` / `which am-mcp` 返回的绝对路径。从源码运行
时，`command` 用 Python 的绝对路径，`args` 填 `am_mcp_server.py` 的绝对路径。

## 3. 各客户端

### Codex CLI、Codex 桌面端与 IDE 扩展

```bash
codex mcp add applemusic --env PYTHONIOENCODING=utf-8 -- am-mcp
codex mcp list
```

等价的 `~/.codex/config.toml`（也可使用受信任项目内的 `.codex/config.toml`）：

```toml
[mcp_servers.applemusic]
command = "am-mcp"

[mcp_servers.applemusic.env]
PYTHONIOENCODING = "utf-8"
```

同一台 Codex host 上，桌面端、CLI 和 IDE 扩展共享这份配置。官方说明：
[OpenAI — Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)。

### Claude Code / Claude Desktop

```bash
claude mcp add --scope user applemusic --env PYTHONIOENCODING=utf-8 -- am-mcp
claude mcp get applemusic
```

Claude Desktop 使用上面的通用 `mcpServers` JSON；修改后要完全退出并重开。官方说明：
[Anthropic — Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp)。

### Cursor

项目级放在 `.cursor/mcp.json`，全局放在 `~/.cursor/mcp.json`，然后到 **Settings > MCP** 启用。
官方说明：[Cursor — MCP](https://docs.cursor.com/context/model-context-protocol)。

### VS Code / GitHub Copilot

VS Code 顶层键是 `servers`，不是 `mcpServers`：

```json
{
  "servers": {
    "applemusic": {
      "type": "stdio",
      "command": "am-mcp",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

工作区配置写到 `.vscode/mcp.json`。需要被 Agent Host / Copilot CLI 直接发现时，按 VS Code
说明使用工作区 `.mcp.json` 或用户 `~/.copilot/mcp-config.json`。接受信任提示后运行
**MCP: List Servers**。官方说明：[VS Code — MCP 配置参考](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)。

### Gemini CLI

把通用 JSON 放进项目 `.gemini/settings.json` 或用户 `~/.gemini/settings.json`，也可运行：

```bash
gemini mcp add -s user applemusic am-mcp
gemini mcp list
```

不要把 `trust` 强行设为 `true`，让写操作保留确认。官方说明：
[Gemini CLI — MCP servers](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)。

### Windsurf 与其他客户端

Windsurf 把通用 `mcpServers` 对象放到 `~/.codeium/windsurf/mcp_config.json`。其他本地 MCP
客户端或 Agent Harness 只需启动 `am-mcp`、保持 stdin/stdout 打开，并按
`initialize` → `notifications/initialized` → `tools/list` 完成握手。

### Cordis / DSH Agent Harness

[`preset/`](../preset/) 内有可直接复制的预设：挂载全部 13 个工具、加载配套 skill，并为较慢的
音频特征分析设置两分钟超时。安装步骤见 [`preset/README.md`](../preset/README.md)。

### Harness Platform

这里要区分两种场景：

- Harness CI/CD 步骤可以直接运行 `am-playlist`，也可以运行本仓库构建的容器镜像。
- Harness AI Worker Agent 的 MCP Connector 要求网络 URL 和 API key。本项目是本地优先的
  stdio 服务，不能冒充远程 Connector；若部署 Streamable HTTP，还必须同时配置认证和 TLS，
  本仓库不会提供一个默认无认证的公网桥接层。

官方说明：[Harness — Worker Agent reference](https://developer.harness.io/docs/platform/harness-ai/core-capabilities/in-your-pipelines/harness-agents-references/)。

## 4. Docker

```bash
docker build -t apple-music-playlists:1.4.0 .
```

Linux 镜像默认使用 UID/GID 1000。如果宿主用户不是 1000，构建时加
`--build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)`，否则容器可能无法把刷新后的 token
写回挂载配置。Windows/macOS 的 Docker Desktop 会处理宿主挂载权限。

先在宿主机完成登录，再只挂载该应用的配置目录。这个目录需要可写，因为服务会刷新并保存公开
developer token；缓存目录也保持可写。Windows PowerShell：

```powershell
docker run --rm -i `
  -v "${env:APPDATA}\am-playlist:/home/app/.config/am-playlist" `
  -v "am-playlist-cache:/home/app/.cache/am-playlist" `
  apple-music-playlists:1.4.0
```

macOS / Linux：

```bash
docker run --rm -i \
  -v "$HOME/.config/am-playlist:/home/app/.config/am-playlist" \
  -v am-playlist-cache:/home/app/.cache/am-playlist \
  apple-music-playlists:1.4.0
```

不要加 `-d`：stdio MCP 必须前台连接客户端的 stdin/stdout。客户端使用容器时，`command`
填 `docker`，`args` 填上面的 `run --rm -i ...` 参数。永远不要把 `config.json` 烘焙进镜像。

Compose 用法：设置 `AM_PLAYLIST_CONFIG_DIR` 为宿主机配置目录，再运行
`docker compose run --rm applemusic-mcp`。仓库的 `compose.yaml` 只挂载应用专用配置目录，并把缓存
放进具名 volume。Linux 用户如果 ID 不是 1000，构建前还要设置 `APP_UID` 和 `APP_GID`。

## 5. 验证与排错

向 `am-mcp` 发送一行初始化请求，响应应包含 `apple-music-playlists` 和 `1.4.0`：

```text
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}
```

| 现象 | 处理 |
|---|---|
| 找不到可执行文件 | 使用 `where am-mcp` / `which am-mcp` 返回的绝对路径。 |
| Windows 连接立即关闭 | 设置 `PYTHONIOENCODING=utf-8`，使用 `am-mcp.exe` 或 Python 绝对路径。 |
| 手工 PowerShell 管道把中文或重音字符变乱 | 管道前设置 `$OutputEncoding = [Text.UTF8Encoding]::new($false)`，或在冒烟 JSON 中使用 `\u` 转义。 |
| 终端能跑、GUI 不行 | GUI 的 PATH 不同；改用绝对路径并重启客户端。 |
| 未登录 | 在运行服务的同一系统用户/环境里执行 `am-playlist login`。 |
| 容器看不到登录 | 把宿主配置目录挂载到 `/home/app/.config/am-playlist`。 |
| 工具列表还是旧的 | 重启客户端；VS Code 可运行 **MCP: Reset Cached Tools**。 |

## 6. Agent 安全约定

- 任何写操作前先调用 `am_status`。
- 大批量创建或追加前先 `dry_run: true`。
- 删除前展示目标歌单并取得用户确认；协议层还必须传 `confirm: true`。
- 把 `config.json`、`.p8`、收听历史和生成的歌单视为私密数据。
- 工具 annotations 只是提示，不能代替客户端确认机制。

# 安装这个预设

这个目录是一份 **Cordis agent preset 模板**，它把一个 MCP 服务挂到某个 Agent 上，
让该会话直接获得 13 个 Apple Music 工具（`mcp__applemusic__am_*`）。

模板里的两处占位符需要替换：

| 占位符 | 换成 |
|---|---|
| `<PYTHON>` | 你本机 python 可执行文件的**绝对路径**（Windows 例：`C:\Python312\python.exe`） |
| `<PROJECT_ROOT>` | 本仓库克隆到本地的**绝对路径** |

---

## 安装步骤

### 1. 克隆并确认能跑

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
```

### 2. 复制到预设目录

预设的**用户级根目录**是 `${DSH_HOME:-~/.dsh}/.agent-presets/`，一个预设一个子目录：

```powershell
# Windows
$dst = "$env:USERPROFILE\.dsh\.agent-presets\music"
New-Item -ItemType Directory -Force -Path $dst
Copy-Item .\preset\agent.cordis.yml, .\preset\preset.yml $dst
```

```bash
# macOS / Linux
dst="$HOME/.dsh/.agent-presets/music"
mkdir -p "$dst" && cp preset/agent.cordis.yml preset/preset.yml "$dst/"
```

### 3. 替换占位符

```powershell
$root = (Get-Location).Path
$py   = (Get-Command python).Source
$f    = "$env:USERPROFILE\.dsh\.agent-presets\music\agent.cordis.yml"
(Get-Content $f -Raw) -replace '<PYTHON>', $py -replace '<PROJECT_ROOT>', $root |
  Set-Content $f -Encoding UTF8
```

```bash
sed -i "s|<PYTHON>|$(command -v python)|g; s|<PROJECT_ROOT>|$PWD|g" \
  "$HOME/.dsh/.agent-presets/music/agent.cordis.yml"
```

> ⚠️ YAML 里是单引号包裹的 Windows 路径，**反斜杠不需要转义**（单引号内是字面量）。
> 替换后不要引入双引号，否则反斜杠会被当作转义符。

### 4. 安装 skill（可选但推荐）

`skill/` 里是一个 Agent 技能，记录了完整工作流和一批实测踩过的坑。
放到**用户级** skill 根目录即可被所有会话发现：

```powershell
Copy-Item -Recurse .\skill "$env:USERPROFILE\.dsh\skills\apple-music-playlists"
```

```bash
mkdir -p "$HOME/.dsh/skills" && cp -r skill "$HOME/.dsh/skills/apple-music-playlists"
```

### 5. 一次性登录 + 验证

```bash
python am_playlist.py login          # 见仓库 SETUP.md 的三种方式
```

然后新开一个会话、选择预设「音乐歌单」，问它 "我的 Apple Music 登录状态如何"。
它应该调用 `am_status` 并回报 storefront。

---

## 这个预设里有什么

| 行 | 作用 |
|---|---|
| `mcp-apple-music` | `@deepseek-ai/dsh-mcp-client`，stdio 连到 `am_mcp_server.py` |
| `skill-filesystem` + `tool-skill` | 让本预设的 Agent 能发现并加载上面的 skill（**两行都要**，缺一个技能目录就是空的） |
| `persona` | 简短的人设 + Apple Music 工具使用规则 |
| shell / fs / web / ask-user / goals / present / compaction | 基础能力（本模板基于轻量预设，可按需增删） |

`failOnStartupError: false` 是刻意的：Python 路径写错时预设仍能挂载，
错误以工具报错的形式暴露，而不是让整个 Agent 起不来。

---

## 只想要 MCP、不想要预设？

`am_mcp_server.py` 是标准 MCP stdio 服务，任何 MCP 客户端都能接。

### 推荐：先装成包，注册只剩一行

装完之后模块进了 site-packages，**不再需要绝对脚本路径，也不依赖 cwd**：

```bash
pip install apple-music-playlists
# 或者已经在仓库里：  pip install -e .
```

```json
{ "mcpServers": { "applemusic": {
    "command": "am-mcp",
    "env": { "PYTHONIOENCODING": "utf-8" } } } }
```

`am-mcp` 是打包时声明的 console script（等价于 `python -m am_mcp_server`）。

### 不装包也行：写脚本绝对路径

```json
{ "mcpServers": { "applemusic": {
    "command": "python",
    "args": ["/abs/path/to/am_mcp_server.py"],
    "env": { "PYTHONIOENCODING": "utf-8" } } } }
```

> ⚠️ 不装包时 `python -m am_mcp_server` **只在仓库目录里能用**——从别处调用会
> `No module named am_mcp_server`（实测）。所以这条路必须给脚本绝对路径。

> `PYTHONIOENCODING=utf-8` 不是可选的：服务端用
> `json.dumps(..., ensure_ascii=False)` 输出，**中文是裸 UTF-8 字节**，
> Windows 上 stdout 默认 GBK 会直接崩。

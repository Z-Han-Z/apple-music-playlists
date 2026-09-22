# Apple Music 歌单工具箱

[English](README.md) | 简体中文 | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | [Français](README_FR.md)

**从命令行或支持 MCP 的 Agent 创建、体检和重排 Apple Music 歌单。**

Python 3.10+，运行时只用标准库，支持 Windows / macOS / Linux。默认使用
Apple 网页播放器的公开 developer token，不需要 Apple Developer Program。本项目不内置
艺人清单、主题或成品歌单，曲目由你提供。

```text
创建 → 元数据体检 → 抓取音频特征 → 优化曲序 → 重建
```

## 快速开始

直接克隆（无需安装依赖）：

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "我的歌单" --tracks "歌名 A - 艺人 X, 歌名 B - 艺人 Y"
```

或安装为命令：

```bash
pip install "apple-music-playlists @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist status
am-playlist login
```

安装后可用 `am-playlist` CLI 和 `am-mcp` MCP stdio 服务。开发时在克隆目录执行
`pip install -e .`。

## 凭证

首次运行会自动获取 developer token。读写个人音乐库还需要一次 Apple ID 登录：

```bash
am-playlist login
```

可以从 Windows Apple Music 应用读取、用 Playwright 登录，或手动复制
`media-user-token`。完整步骤、安全说明和排错见 **[SETUP.md](SETUP.md)**。

## 常用命令

```bash
am-playlist search "晴天 周杰伦"
am-playlist playlists
am-playlist show "歌单名"
am-playlist create --name "歌单名" --tracks "歌名 - 艺人, ..."
am-playlist add "歌单名" --tracks "歌名 - 艺人"
am-playlist library

python playlist_audit.py "歌单名"
python playlist_flow.py "歌单名"
python playlist_optimize.py 清单.json -o 曲序.json --arc cinderella
python listening_stats.py top --kind songs --year 2026
```

曲序引擎会检查慢歌连续、轻微降速、速度与调性同时过于相似、无理由的大幅跳变，
并可选六种叙事弧：`rags-to-riches`、`tragedy`、`man-in-a-hole`、`icarus`、
`cinderella`、`oedipus`。优化器可保留原有分组，只在组内排序。

## MCP 与 Agent

通用配置：

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

服务提供 11 个工具：状态、搜索、列出/查看歌单、创建、追加、删除、元数据体检、
听感分析、最近播放和播放次数排行。工具描述为英文/中文，并声明只读与破坏性标记。

Codex、Claude、Cursor、VS Code/Copilot、Gemini CLI、Windsurf、Docker、Cordis/DSH 和 Harness
配置见 **[docs/client-setup.zh-CN.md](docs/client-setup.zh-CN.md)**。

## Docker

```bash
docker build -t apple-music-playlists:1.2.0 .
```

容器使用 stdio，必须保留 `-i`，不要加 `-d`。先在宿主机登录，再把应用专用配置目录挂载到
`/home/app/.config/am-playlist`，并保持可写以便刷新 token；缓存挂载到 `/home/app/.cache/am-playlist`。
不要把令牌写进镜像。

## 数据、安全与限制

- 配置在 `%APPDATA%\am-playlist\config.json` 或 `~/.config/am-playlist/config.json`；缓存在用户缓存目录，不写仓库。
- `music-user-token`、`.p8`、收听历史和生成的歌单都是私密数据，不要提交或记入 CI 日志。
- 写操作前先调用 `am_status`，大批量操作前先 `dry_run`。
- 删除歌单必须明确确认，MCP 层还强制 `confirm=true`。
- Apple 限制：只有创建某歌单的 API 客户端才能继续修改它。
- 创建歌单会把曲目加入音乐库；删除歌单不会移除这些曲目。

## 测试与文档

```bash
python -m unittest discover -s tests -v
```

测试全部离线，不需要 Apple 凭证。策展方法、API 实测、平台适配边界和发布记录见
[`docs/`](docs/)、[`skill/`](skill/) 和 [CHANGELOG.md](CHANGELOG.md)。

MIT License。非 Apple 官方项目，请用自己的 Apple Music 账号并遵守 Apple 服务条款。

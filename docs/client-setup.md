# MCP clients, containers, and agent harnesses

[简体中文](client-setup.zh-CN.md)

The supported transport is local MCP over standard input/output. Install the project once, then
point the client at `am-mcp`. The server writes protocol messages only to stdout, uses UTF-8, has
no runtime dependencies, and exposes explicit read-only/destructive tool annotations.

## Description-to-playlist workflow

The intended interaction is a natural-language request such as:

> Make a 20-track Sunday-morning playlist: warm soul, folk, and quiet jazz; mostly 1970s to
> present; no live recordings; gently increase the energy and end softly.

The LLM in the MCP client turns that brief into candidates. The stdio server then grounds the work
in Apple Music through `am_status`, `am_search_songs`, and a dry run of `am_create_playlist` before
the final write. It does not call a separate model provider and needs no LLM API key of its own.

Clients that expose MCP Prompts can select `create_playlist_from_description` and fill in the
brief, optional name, track count, and response language. A client without Prompt UI support loses
nothing essential: send the request in ordinary chat, because the same workflow is also present in
the server instructions and tool descriptions.

The CLI is the companion interface for authentication, diagnostics, automation scripts, audits,
and manual maintenance; users should not have to assemble a `"Title - Artist"` array for the normal
MCP flow.

## 1. Install and authenticate

```bash
pip install "apple-music-playlists @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist status
am-playlist login
```

`login` is a one-time interactive step. Clients launched as another OS user, in WSL, on a remote
host, or in a container do not automatically share the host user's config. See [SETUP.en.md](../SETUP.en.md)
for config paths and all login methods.

After registration, restart the client and ask it to call `am_status`. Do not test by creating a
playlist first.

## 2. Portable JSON configuration

Claude Desktop, Cursor, Windsurf, Gemini CLI, and many agent harnesses accept this shape:

```json
{
  "mcpServers": {
    "applemusic": {
      "command": "am-mcp",
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

If the console script is not on the client's PATH, use an absolute executable path. From a clone,
use an absolute script path instead:

```json
{
  "mcpServers": {
    "applemusic": {
      "command": "python",
      "args": ["/absolute/path/apple-music-playlists/am_mcp_server.py"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

On Windows, prefer the absolute path to `am-mcp.exe` returned by `where am-mcp` when a GUI client
does not inherit the same PATH as the terminal.

## 3. Client-specific setup

### Codex CLI, Codex app, and the IDE extension

```bash
codex mcp add applemusic --env PYTHONIOENCODING=utf-8 -- am-mcp
codex mcp list
```

Equivalent `~/.codex/config.toml` (or trusted project `.codex/config.toml`):

```toml
[mcp_servers.applemusic]
command = "am-mcp"

[mcp_servers.applemusic.env]
PYTHONIOENCODING = "utf-8"
```

The desktop app, CLI, and IDE extension share this configuration on the same Codex host. In the
desktop settings UI, choose a local STDIO server and use `am-mcp` as the command.

Official reference: [OpenAI — Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp).

### Claude Code and Claude Desktop

Claude Code:

```bash
claude mcp add --scope user applemusic --env PYTHONIOENCODING=utf-8 -- am-mcp
claude mcp get applemusic
```

Claude Desktop uses the portable `mcpServers` JSON above. Fully quit and reopen the app after
editing its configuration.

Official reference: [Anthropic — Connect Claude Code to tools via MCP](https://docs.anthropic.com/en/docs/claude-code/mcp).

### Cursor

Put the portable JSON in `.cursor/mcp.json` for a project or `~/.cursor/mcp.json` globally, then
enable the server in **Settings > MCP**.

Official reference: [Cursor — Model Context Protocol](https://docs.cursor.com/context/model-context-protocol).

### VS Code and GitHub Copilot

VS Code uses `servers`, not `mcpServers`:

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

Save it as `.vscode/mcp.json` for the workspace. For portable Agent Host / Copilot CLI discovery,
use workspace `.mcp.json` or user `~/.copilot/mcp-config.json` as documented by VS Code. Accept the
trust prompt, then run **MCP: List Servers**.

Official reference: [VS Code — MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

### Gemini CLI

Put the portable JSON in project `.gemini/settings.json` or user `~/.gemini/settings.json`, or run:

```bash
gemini mcp add -s user applemusic am-mcp
gemini mcp list
```

Keep `trust` at its default so writes still require confirmation.

Official reference: [Gemini CLI — MCP servers](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html).

### Windsurf and other JSON clients

Windsurf uses the portable `mcpServers` object in `~/.codeium/windsurf/mcp_config.json`. Other
local MCP clients and agent harnesses should spawn `am-mcp`, keep stdin/stdout open, and send the
normal `initialize` → `notifications/initialized` → `tools/list` sequence.

### Cordis / DSH agent harness

The ready-to-copy preset in [`preset/`](../preset/) mounts the stdio server, exposes all 11 tools,
loads the companion skill, and sets a two-minute tool timeout for slower feature analysis. Follow
[`preset/README.md`](../preset/README.md).

### Harness Platform

There are two distinct integrations:

- A Harness CI/CD step can run `am-playlist` directly or run the image built from this repository.
- Harness AI Worker Agent MCP connectors require a network URL and API key. This project is a
  local-first stdio server, so it must not be entered as a remote Harness MCP connector. Deploying
  it behind Streamable HTTP also requires authentication and TLS; this repository intentionally
  does not ship an unauthenticated bridge.

Official reference: [Harness — Worker Agent reference](https://developer.harness.io/docs/platform/harness-ai/core-capabilities/in-your-pipelines/harness-agents-references/).

## 4. Docker

Build the local image:

```bash
docker build -t apple-music-playlists:1.2.0 .
```

On Linux, the default container user is UID/GID 1000. If your host user differs, build with
`--build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)` so the container can refresh the token
in the bind-mounted config directory. Docker Desktop handles host mounts on Windows/macOS.

Generate the user config on the host first, then mount that exact directory. It must remain
writable because the server refreshes and persists the public developer token. Linux/macOS example:

```bash
docker run --rm -i \
  -v "$HOME/.config/am-playlist:/home/app/.config/am-playlist" \
  -v am-playlist-cache:/home/app/.cache/am-playlist \
  apple-music-playlists:1.2.0
```

Windows PowerShell example:

```powershell
docker run --rm -i `
  -v "${env:APPDATA}\am-playlist:/home/app/.config/am-playlist" `
  -v "am-playlist-cache:/home/app/.cache/am-playlist" `
  apple-music-playlists:1.2.0
```

Do not add `-d`: an MCP stdio server must remain attached to the client's stdin/stdout. A client's
Docker configuration uses `docker` as its command and the arguments above (including `-i`). Never
bake `config.json` into an image.

For Compose, set `AM_PLAYLIST_CONFIG_DIR` to the host config directory and run
`docker compose run --rm applemusic-mcp`. `compose.yaml` mounts only the app-specific config
directory and keeps cache in a named volume. Linux users with a non-1000 ID should also set
`APP_UID` and `APP_GID` before building.

## 5. Verification and troubleshooting

Minimal protocol smoke test:

```text
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}
```

Send that as one line to `am-mcp`; the response should name `apple-music-playlists` and version
`1.2.0`. Then use the client to call `am_status`.

| Symptom | Fix |
|---|---|
| Executable not found | Use the absolute path from `where am-mcp` / `which am-mcp`. |
| Connection closes on Windows | Set `PYTHONIOENCODING=utf-8`; use `am-mcp.exe` or an absolute Python path. |
| Works in terminal, not GUI | GUI PATH differs; use an absolute command and restart the client. |
| Not logged in | Run `am-playlist login` as the same OS user/environment that runs the server. |
| Container cannot see login | Mount the host config directory at `/home/app/.config/am-playlist`. |
| Tools changed but client shows old list | Restart the server/client; VS Code also has **MCP: Reset Cached Tools**. |

## 6. Safety contract for agents

- Call `am_status` before any write.
- Use `dry_run: true` before large creates or additions.
- Display the selected playlist before deletion and ask the user; deletion also requires
  `confirm: true` on the wire.
- Treat `config.json`, `.p8` keys, listening history, and generated playlists as private data.
- Do not disable client confirmations merely because the server exposes tool annotations.

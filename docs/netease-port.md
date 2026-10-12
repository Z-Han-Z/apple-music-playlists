# 网易云公开预览 / NetEase public preview — 1.6.0

**1.6.0 正式包中的实验性公开预览。** `nc-mcp` / `nc-login` 与默认 Apple 服务分离。
不是网易云官方项目，接口可能因风控、版权、地区或接口变化失效。不播放、下载或转发音频，
不提供解灰、会员或 DRM 绕过。

**Experimental public preview in the 1.6.0 stable package.** Undocumented web
APIs are not guaranteed across accounts/regions. No audio downloads, playback or DRM bypass.
The default Apple server and existing tool names stay unchanged.

由宿主 LLM 直接理解原始需求、策划候选和顺序；服务端提供事实、版本校验和用户确认后的
写入。没有数值主题评分、不需要额外 LLM API key。方向标签只是原始需求的定性补充。
The host LLM curates linguistically; tools ground identities and preserve the original brief.

## 1. 安装 / Install

面向普通 Windows x64 用户分发[完整 ZIP](https://github.com/Z-Han-Z/apple-music-playlists/releases/download/v1.6.0/NetEase-Curator-1.6.0-Windows-Preview.zip)，而不是只发 wheel。**这是 MCP，不是应用：所有引导
在宿主对话中完成。** 解压后让有本地工具的 Agent 阅读说明、运行 install.cmd 并协助合并配置；
没有本地执行工具时可自己运行 install.cmd。服务必须先接入宿主，不能自行配置未连接的客户端。
接入后说“帮我开始使用网易云 MCP”：Agent 调用 `nc_setup` / `nc_status`，解释缺口并征得登录同意。
本包不捆绑 Python，但包含私有 Node 24.19.0 和锁定的 API Enhanced 4.41.1 扫码组件：
不需要用户安装 Node、部署网关或复制 Cookie。没有独立窗口、固定菜单或选曲问卷。
The complete Windows x64 ZIP is conversation-first MCP distribution, not a standalone application.
Python is not bundled. Installation is offline; approved `nc_login` starts a temporary loopback-only
login helper, opens QR only in the local browser, closes on completion/cancellation, and verifies
gateway-free login. Poll status in the conversation; QR images/keys/URLs/cookies never enter MCP replies.
No global PATH/package edits. Optional `getting_started` Prompt, ordinary chat works without a menu.
Copy the readonly config into the host without overwriting other servers; client connection still
requires an actual `nc_status` tool call. The wheel also ships standalone guides.

Maintainer build: `python scripts/build_beta_bundle.py` fetches SHA256-pinned official Node bytes
and installs registry-integrity-locked npm dependencies with lifecycle scripts disabled. Licenses,
dependency lock and provenance ship inside `qr-runtime`. `--light` omits QR runtime and is an
advanced import-only distribution, not the recommended ordinary-user package. Same-version wheel
updates are detected by SHA256 and installed into a fresh environment without deleting the old one.

Python 3.10+，零运行时依赖。在本地源码根目录 / From a local beta checkout:

```bash
python -m pip install .
nc-login --help
```

或安装 PyPI 包 / Or install the public PyPI package:

```bash
python -m pip install apple-music-playlists==1.6.0
```

The public PyPI package now includes the NetEase tools. Advanced users may run
`uvx --from apple-music-playlists==1.6.0 nc-mcp`; its wheel does **not** include the QR runtime.
Use the complete Windows ZIP for bundled, host-approved QR, or follow the standalone CLI
import/external-gateway instructions below. If scripts are not on PATH, use an absolute path.

## 2. 本地登录 / Local login

```bash
nc-login import --save
nc-login status --verify
```

在交互终端隐藏粘贴用户自行从官方站点获取的 `MUSIC_U` 或 Cookie header；不要发到聊天、
命令参数、截图或 Git。只提取认证字段，不导入分析/设备 Cookie。
登录与 CSRF 校验成功后才保存；不加 `--save` 只验证、不持久化。
Paste into the hidden interactive prompt only. Validation precedes explicitly requested storage.
No passwords, browser-cookie harvesting, credential URLs or raw response logging.

Windows 使用当前用户 DPAPI 加密，存于用户配置目录 `am-playlist/netease/session.bin`。
同一 Windows 用户的 MCP 客户端自动读取；不是跨机器/账号/容器可移植的会话文件。
macOS/Linux 无系统密钥库集成：须增加 `--allow-plaintext` 才能保存，文件限制为当前用户
所有、0600。若不愿明文保存，使用环境变量且不要把值写到仓库内配置。

Windows storage uses current-user DPAPI. POSIX storage is explicitly consented **plaintext**,
owner-only mode 0600, not encryption. `NETEASE_COOKIE` overrides saved state; optional
`NETEASE_CSRF` overrides CSRF. Otherwise CSRF comes from server-issued Set-Cookie, never a
fabricated value. `login-expired` requires local re-import; requests do not auto-retry.

```bash
nc-login forget --confirm
```

只删除本地会话，不撤销网易云服务器令牌。已暴露的会话应在官方账号中退出/撤销。
Local deletion does not revoke the session at NetEase; revoke exposed sessions separately.

### 可选扫码 / Optional QR

```bash
nc-login qr --save
```

以上是独立 wheel/源码 CLI 的进阶用法；完整 Windows ZIP 的 `nc_login` 在用户同意后
管理随包临时网关，不需要填写地址；login-qr.cmd 只是本机备用授权入口。独立 CLI 需安装并信任
[API Enhanced 本地网关](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)，
设置 `NETEASE_API_URL=http://127.0.0.1:3000`。隐藏粘贴和直连读取不需要 Node 或网关。
只允许 loopback HTTP(S) origin，拒绝远程代理、URL 凭据和跨 origin 重定向。
网关是可以读取令牌的受信任进程，不要公开部署或启用解灰功能。

Standalone CLI QR requires a user-managed trusted loopback gateway; the complete Windows ZIP
manages its bundled gateway automatically. Open the local QR page, scan and
authorize in the official app. It polls for at most two minutes, never prints the returned cookie,
and removes the temporary page afterwards. Windows authorization/storage/subsequent direct login
have been smoke-tested with a login-only loopback API Enhanced 4.41.1 gateway; other environments
remain unverified.

## 3. MCP 客户端与 Harness / Clients and harnesses

本地 stdio，不提供远程 HTTP/SSE，不另开模型。支持可启动 MCP 子进程的客户端/Harness；
Prompts UI 可选，普通聊天加工具调用即可。
Local stdio works with MCP process-launching clients/harnesses. Prompts UI is optional.

```json
{
  "mcpServers": {
    "netease-curator-beta": {
      "command": "nc-mcp"
    }
  }
}
```

PATH 不可用时用绝对路径；源码方式（替换占位符） / Source configuration:

```json
{
  "mcpServers": {
    "netease-curator-beta": {
      "command": "<PYTHON_ABSOLUTE_PATH>",
      "args": ["<PROJECT_ROOT>/netease_mcp_server.py"]
    }
  }
}
```

先调用 `nc_status`，再描述需求，例如：

> 做一张从午夜便利店出发、逐渐走到清晨海边的 12 首歌单。以城市流行的空间感为起点，
> 逐渐转到更有机的乐器；包含几首我最近爱听的歌，但不要把热榜当成主题答案。先给预览。

The host gathers relevant pages, proposes a generous candidate pool, resolves versions, offers
qualitative direction edits, and reconsiders the selection against the unchanged original brief.
Outputs have compact text fallback plus bounded `structuredContent`, not two full library dumps.

### 容器 / Containers

现有 Dockerfile 从 v1.6.0 源码构建，默认仍启动 Apple；没有发布预构建镜像。
Build from the v1.6.0 source and override the entrypoint. The Windows QR bundle is not a Linux
container login runtime. Session environment values are not passed as command arguments:

```bash
docker build -t am-curator-preview:1.6.0 .
docker run --rm -i --entrypoint python --env NETEASE_COOKIE am-curator-preview:1.6.0 /app/netease_mcp_server.py
```

Windows DPAPI 文件不能交给 Linux 容器解密。用独立的用户配置/缓存卷、正确的非 root
所有权。容器的 localhost 不是宿主机：网关仅支持同一网络命名空间的 loopback，
不要通过远程代理绕过令牌限制。MCP stdio 不使用 `-t`。
Container builds/runs and cross-OS session setups are documented, not live-tested here.

## 4. 20 个工具 / Tools and bounded reads

| Tools | Contract |
|---|---|
| `nc_setup` | Offline onboarding facts; saved session ≠ verified login; host explains next steps |
| `nc_login` | Consent-gated local QR start, opaque progress job and cancellation; no credentials/QR in chat |
| `nc_status` | Login/session source/capabilities and conversational next step; network failure ≠ expired session |
| `nc_search_songs`, `nc_resolve_candidates` | Unicode identity/version grounding; metadata ≠ playability |
| `nc_list_playlists`, `nc_show_playlist` | Bounded account summaries/song pages; default 20, max 100 |
| `nc_liked_songs` | Liked membership, numeric ID order; not listening/liking date |
| `nc_collected_albums`, `nc_followed_artists` | Paginated membership, not song plays |
| `nc_get_songs` | Up to 100 explicit IDs; preserve order/duplicates/missing positions |
| `nc_recently_played` | Recent-event window (max 100), Unix millisecond timestamps; not lifetime history |
| `nc_top_played` | week/all-time; play_count and ranking_score distinct, absent counts null |
| `nc_tag_directions` | Qualitative edits, provider-specific declared source chains; not verified tag meanings |
| `nc_create_playlist`, `nc_add_tracks`, `nc_delete_playlist` | Preview by default, write opt-in, confirmation, owner/readback checks |
| `nc_audit_playlist`, `nc_analyze_flow`, `nc_optimize_order` | Factual/shared physical rules; missing measurements stay unknown |

按 `has_more/next_offset` 翻页，不能把一页当全部。歌单汇总、曲目和红心下一页传回
`snapshot`：成员/顺序变化返回 `snapshot-changed`，需从零重读。专辑、艺人、榜单、
近期窗口没有可靠服务端快照，跨页可能变动，不能拼成某一时刻的全历史。
缺元数据保留 ID/位置和缺失列表；默认不把完整用户库塞进上下文。

Follow page markers. Internal full reads remain for audits/write verification. For playlist
summaries, direct endpoints may ignore requested page size: enumerate all IDs safely, then return
only the requested bounded page. Liking/following alone never proves play count or listening dates.
all-time ranking is not annual Replay or a dated lifetime history.

## 5. 写入与特征边界 / Write and feature safety

1. Ground candidates, inspect ambiguous versions, preview with `dry_run=true`.
2. Obtain user approval; enable `NETEASE_ENABLE_WRITES=1` locally.
3. Actual calls require `dry_run=false, confirm=true`; creation defaults private.
4. Inspect `verified`, `status` and MCP `isError`; accepted requests ≠ verified outcomes.

创建是多步操作，可能部分成功；保留已知歌单 ID，**不自动重试、删除或回滚**。
追加核对原曲/曲序/owner，前插或并发变化返回 needs-review，不擅自重排。
重复已有歌曲阻止写入；创建核对曲序、owner、隐私及请求的描述。
删除只限本工具记录创建且当前用户拥有的歌单；接受删除不是独立删除后核验。

Partial writes return `partial-or-unknown` and the known ID. Inspect in the official client
before retrying. The creation journal stores only ID→owner ID under the user cache, not song
names/history/tokens. Clearing it intentionally removes this tool's delete eligibility.

没有可靠网易云原生 ISRC→音频特征链，不虚构 BPM/key、不做同名跨平台猜测。
`features` 必须显式提供、注明来源的测量值（服务端不独立核实来源）。
缺特征报告覆盖率及未评估相邻对；不完整则保持原序、不输出误导 cost。
No feature coverage means unknown transitions, not perfect zero-cost sequencing.

## 验证状态 / Verification status

用户明确授权下已验证登录、CSRF、账号歌单、红心、收藏专辑、关注艺人、周榜、历史榜。
此前真实创建一个隐私单曲测试歌单并读回核对；本轮只读，不继续改账号。
不把个人数量、账号 ID、Cookie、选曲或听歌记录写入发布文档/测试。
最近播放的有界读取、时间字段和两页读取也已完成只读实测。不把单一账号验证说成通用认证。

All offline tests mock network/library writes. Windows DPAPI uses synthetic tokens in tests.
Append/delete/multi-song ordering/description, other gateway/OS variants and containers still
need explicitly authorized external validation; a one-song smoke does not certify those paths.

```bash
python -m unittest discover -s tests -v
git diff --check
```

`mcp_common.py` and `catalog_matching.py` are standard-library/platform-neutral; existing
Apple exports remain compatible. `playlist_core.check_pair` remains the single physical-rule
definition with no new platform imports.

# 怎么全自动创建 Apple Music 歌单 —— 研究报告

> 调研 + 实测环境：Windows 11 家庭版（中文）、Python 3.12.10、Node 24.19、Microsoft Edge 153
> 实测日期：2026-09-21
> 所有 HTTP 结论都是在本机真实请求得到的，不是抄文档。

---

## 0. 结论摘要（先看这段）

**一句话：Apple 不给你"零登录"的口子，但登录一次之后，建歌单可以 100% 全自动。**

| 问题 | 结论 |
|---|---|
| 能不能完全不登录就建歌单？ | **不能**。建歌单 = 写用户的音乐库，必须有 `music-user-token`（用户级令牌），只能由 Apple ID 登录 + 双重认证换来。这是 Apple 的设计，没有任何绕过方式。 |
| 需不需要每年 ¥688 的 Apple Developer Program？ | **不需要**。网页播放器 `music.apple.com` 把它的 developer token 直接内嵌在前端 JS 里，脚本可以自动抓取。 |
| 登录一次之后能全自动多久？ | 约 **6 个月**（`music-user-token` 的寿命）。过期后重跑一次 `login`；developer token 由脚本自动续抓，无需干预。 |
| 本机最佳路径 | 网页播放器内部 API `amp-api.music.apple.com`，脚本已实现并**端到端跑通**。 |
| 当前状态 | ✅ **已跑通**。登录已完成，实测建成歌单「演示歌单」（8 首，顺序正确），删除也已验证。 |
| 已经交付了什么 | `am_playlist.py`（命令行工具，纯标准库）、`am_mcp_server.py`（MCP 服务，7 个工具）、DSH 新预设「音乐歌单」。 |

---

## 1. 先理解令牌模型：三把钥匙，一把锁

Apple Music 的 API 有两层认证，很多人卡在这里，所以先讲清楚：

| 令牌 | 它证明什么 | 从哪来 | 有效期 | 能否自动拿到 |
|---|---|---|---|---|
| **developer token**（ES256 JWT） | "我是可信客户端" —— **每个请求**都要带 | ① 自己 Apple 开发者账号的 MusicKit 私钥 `.p8`<br>② **网页播放器内嵌的公开 token** | 自己签：最长 6 个月<br>网页版：约 **70 天** | ✅ **完全自动**（脚本从 bundle 抓，过期自动重抓） |
| **music-user-token** | "我是这个用户" —— **读写音乐库必需** | 登录 `music.apple.com` 后浏览器里的 `media-user-token` cookie | 约 **6 个月** | ⚠️ **需要一次性登录**（Apple ID + 2FA） |
| （可选）`.p8` 私钥 | 生成自己的 developer token，配额独享 | Apple Developer Program，¥688/年 | 长期 | ❌ 要付费账号 |

**锁**就是 `music-user-token`：拿不到它，`/v1/me/...` 全部 403。这是唯一的、不可绕过的人工环节。

### 1.1 实测证据：公开 developer token 确实可用

在 `https://music.apple.com/us/browse` 引用的 `/assets/index~8bc3c631ba.js`（3.3 MB）里，
正则扫出 3 个 JWT，其中两个是 developer token。解出第一个：

```json
{"iss":"AMPWebPlay","iat":1789146906,"exp":1795194906,"root_https_origin":["apple.com"]}
```

- `exp = 1795194906` → **2026-11-20 17:15:06 UTC**（相对测试时刻还剩 60.4 天）
- `root_https_origin: ["apple.com"]` → 请求必须带 `Origin: https://music.apple.com`

同一份 bundle 里还能读到它自己怎么拼请求头（这是 Apple 自己的前端代码）：

```js
{headers: { ...(a ? {authorization: `Bearer ${a}`} : {}),
            ...(l ? {"media-user-token": l} : {}),
            ...(!u ? {"x-apple-client-version": i} : {}), ... }}
```

以及 `media-user-token` 是**从 cookie 读的**：`function nr(){return hm("media-user-token")}`。

### 1.2 实测证据：端点存在性对照

用抓到的 token 直接打接口（**故意不带** user token）：

| 方法 | 路径 | HTTP | 响应 |
|---|---|---|---|
| POST | `/v1/me/library/playlists` | **403** | `Authentication required for request` / code 40300 |
| POST | `/v1/me/library/playlists/p.abc123/tracks` | **403** | 同上 |
| GET | `/v1/me/library/playlists?limit=1` | **403** | 同上 |
| GET | `/v1/me/storefront` | **403** | 同上 |
| POST | `/v1/me/library/playlistz`（故意写错） | **405** | `Method Not Allowed`（对照组） |
| GET | `/v1/catalog/us/search?term=...&types=songs` | **200** | 正常返回曲目 JSON |

**403 而不是 404 = 端点路径正确、只是缺用户授权。** 405 的对照组说明路径错了会有明显不同的反应。
`amp-api.music.apple.com` 和官方 `api.music.apple.com` 表现完全一致——**同一个后端，两个域名**。

---

## 2. Apple 的硬限制与坑（全部实测踩过）

1. **只有"创建该歌单的那个客户端"才能修改它。**
   用本工具建的歌单，只有本工具能加曲目；你在 iPhone 上手动建的歌单，API 写入会 **403**。
   （官方 API 里返回的 `canEdit` 字段就是这个意思。）
   实务建议：**要自动化的歌单，从一开始就用工具建。**

2. **响应可能是 gzip 压缩的——即使你没请求压缩。**
   这个坑很隐蔽，也是本报告初版一个**错误诊断的根因**：`POST /v1/me/library/playlists`
   返回 `201`，但 body 看起来是"空的"或"乱码"。真相是响应头带了
   `Content-Encoding: gzip`（**而请求里根本没有 `Accept-Encoding`**），
   把 gzip 字节按 UTF-8 解码自然得到乱码。解压后是完整的 JSON，**歌单 ID 一直在里面**：

   ```
   Content-Type: application/json;charset=utf-8
   Content-Encoding: gzip
   前 16 字节 = 1f 8b 08 00 00 00 00 00 00 00 75 52 dd 6e d3 30   ← gzip magic
   解压后: {"data":[{"id":"p.XMrmpXOcvXJvqKM",...,"canEdit":true,...
   ```

   用 `urllib` 时必须自己处理 `Content-Encoding`（本工具已修，见 `http()`）。

3. **新歌单有 iCloud 传播延迟。**
   实测：刚创建的歌单不会立刻出现在 `/v1/me/library/playlists` 里，要等几秒到几十秒。
   所以：**创建时必须带曲目**（`relationships.tracks`，一次搞定），不要"先建空单再加"；
   脚本另有回查 + 最长 30 秒重试兜底。

4. **⚠️ 两个主机不等价：`DELETE` 在官方主机上固定 401。**
   这是本次调研最意外的发现，实测数据：

   | 请求 | `api.music.apple.com`（官方文档写的） | `amp-api.music.apple.com`（网页播放器用的） |
   |---|---|---|
   | `DELETE /v1/me/library/playlists/{id}` | **401** ❌ | **204** ✅ 成功 |

   加上 `x-apple-client-version` 头也不能救活官方主机（仍 401），
   而同一个头加到 amp-api 上反而变成 **500 Upstream Service Error**——所以别发这个头。
   这与 Apple 开发者论坛上那篇
   ["playlist create/delete works but DELETE returns 401"](https://developer.apple.com/forums/thread/813068)
   的报告一致：**创建可以走官方主机，删除必须走 amp-api**。本工具的 `delete` 已按此实现。

5. **429 限流：网页 token 的配额是"公共"的，不是你的。**
   交互式用完全够；**几百首的批量导入会撞上 429**。Apple 在这个路径上不返回 `Retry-After`，
   窗口是滚动的大约 60 分钟——所以短时间重试不但没用，还会延长限流。
   批量场景应该换成自己的 `.p8`（配额独享），或者改用 ISRC 精确匹配（25 首/请求，比"一首一次模糊搜索"省 25 倍请求）。

6. **搜索词里不要带 `" - "` 分隔符（这个坑很隐蔽）。**
   实测：拿 `"Hotel California - Eagles"` 整串去搜，Apple 返回的前 5 条**全是各种 Live 版**，
   录音室版根本不出现；改成空格分隔的 `"Hotel California Eagles"` 就正常了。
   本工具已在 `resolve_tracks()` 里做了这个转换，同时给"查询里没提到的版本后缀"
   （Live / Remastered / Demo / 现场 / 伴奏…）加了扣分，避免匹配到现场版。
   **这也是为什么一定要先 `--dry-run` 看一眼匹配结果再写入。**

---

## 3. 路径全集与决策矩阵

| # | 路径 | 平台 | 要开发者账号 | 自动化程度 | 评价 |
|---|---|---|---|---|---|
| **A** | **网页播放器 API**（`amp-api` + 抓取的 bundle token） | Win/mac/Linux | **不要** | 登录一次后 100% 自动 | ⭐ **本项目采用**。本机实测通过 |
| B | 官方 API + 自己的 `.p8` | 任意 | 要（¥688/年） | 100% 自动 | 批量导入/长期产品用；配额独享，最"正规" |
| C | 浏览器自动化点 UI（Playwright 驱动 music.apple.com） | 任意 | 不要 | 自动化但脆弱 | 兜底方案。UI 改版就崩，且有反自动化风控 |
| D | macOS Music.app + AppleScript | 仅 macOS | 不要 | 完全自动 | 有 Mac 的话**最省事**：本机应用、无令牌、无网络 |
| E | iOS/macOS 快捷指令「创建播放列表」 | Apple 平台 | 不要 | 需手动触发/有限自动 | 适合手机上"一键建单"，不适合批量化 |
| F | 第三方搬运服务（Soundiiz / TuneMyMusic / SongShift / FreeYourMusic） | 任意 | 不要 | 服务端自动 | 从 Spotify 等**搬家**很香；有订阅费，且是黑盒 |
| G | Windows「Apple Music」商店版客户端自动化 | 仅 Windows | — | **不可行** | 实测：该客户端不暴露任何脚本/自动化接口；只能靠 UI 自动化点像素，极脆弱 |

**验证状态（哪些是我实测的，哪些只是文档层面的）**

- **实测通过（本机）**：A（网页 API 抓 token + 搜索 + 端点存在性）、G（客户端无自动化接口、
  cookie 库为空、WebView2 加密方案）。
- **文档/社区层面，未在本机验证**（本机是 Windows，没有 Mac/iPhone 可测）：
  B（需要付费开发者账号，本机无账号）、D（macOS `Music.app` 的 AppleScript
  `make new user playlist`，属于 macOS 标准脚本接口）、E（iOS 快捷指令的「创建播放列表」动作）、
  F（Soundiiz 等第三方服务的 API——其文档站被 Cloudflare 拦住，本报告无法核实具体定价与端点，
  需要的话请以官网为准）。**这些行请在对应平台上自行验证后再依赖。**

### 为什么本报告选 A 而不是 D/E

D（macOS AppleScript）在 Mac 上确实更省事——本机应用、不需要任何令牌、不走网络。
但这台机器是 Windows，没有 Mac；而在 Windows 上唯一可行且可编程的入口就是 HTTP API。
换句话说：**A 是这台机器上的最优解，D 是"如果你有 Mac"时的更优解。**

### 为什么不走 G（本机特别确认过）

本机**装了** `AppleInc.AppleMusicWin 1.1540.23042.0`（商店版 Apple Music），但：

- 它是 WinUI/WebView2 应用，**不暴露任何自动化接口**；
- 它的 cookie 库（WebView2 的 Chromium cookie DB）实测**存在但 0 条记录** —— 说明从没登录过，
  所以连"复用客户端登录态"这条捷径也走不通；
- 结论：想在 Windows 上自动化建歌单，**只能走 HTTP API（路径 A/B）**；客户端本身不可驱动。

> 但客户端还有一个附带用途：如果哪天你在那个客户端里登录了，它的 WebView2 cookie 库里就会出现
> `media-user-token`，而那个库是 DPAPI 加密（非 App-Bound），本工具的 `login` 能自动去读
> （见 `harvest_from_windows_app()`）——这样连浏览器都不用开。

---

## 4. 已交付的东西

```
<PROJECT_ROOT>\
├── am_playlist.py       # 命令行工具（纯标准库，零依赖）
├── am_mcp_server.py     # MCP stdio 服务，把同样的能力暴露成 6 个工具
├── refs\                # 调研过程抓下来的 Apple 官方文档 JSON / bundle 证据
└── tools\               # 调研用的小脚本（文档解析、cookie 列举）

~\.dsh\.agent-presets\music\
├── agent.cordis.yml     # DSH 预设「音乐歌单」：闲聊模式 + Apple Music MCP
└── preset.yml
```

### 4.1 命令行工具

```powershell
cd "<PROJECT_ROOT>"

python am_playlist.py status                       # 看令牌状态
python am_playlist.py search "晴天 周杰伦" -storefront cn   # 搜曲目
python am_playlist.py list                          # 列出我的歌单
python am_playlist.py create --name "通勤" --tracks "晴天 - 周杰伦, Bohemian Rhapsody - Queen"
python am_playlist.py create --name "通勤" --json tracks.json     # 批量/脚本化（LLM 直接生成 JSON）
python am_playlist.py create --name "预演" --tracks "..." --dry-run  # 只预览匹配结果，不写入
python am_playlist.py add --playlist "通勤" --tracks "..."          # 追加
```

实测输出（无需登录的部分已跑通）：

```
> python am_playlist.py search "周杰伦 晴天" --limit 2 --storefront cn
=== songs ===
  535824738      晴天  —  周杰伦
  1485220317     晴天 (Live)  —  周杰伦

> python am_playlist.py status
developer token: 有效 (iss=AMPWebPlay, 剩余 60.4 天)
music-user-token: 无 —— 请先运行 login
```

### 4.2 MCP 服务（让 DSH 里的 Agent 直接会建歌单）

`am_mcp_server.py` 是手写的 JSON-RPC 2.0 over stdio（MCP 的传输格式），**零第三方依赖**。
实测握手成功：

```
> echo initialize | python am_mcp_server.py
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",
 "capabilities":{"tools":{"listChanged":false}},
 "serverInfo":{"name":"apple-music-playlists","version":"1.0.0"}}}
```

暴露 6 个工具：`am_status`、`am_search_songs`、`am_list_playlists`、`am_show_playlist`、
`am_create_playlist`（主入口）、`am_add_tracks`。

### 4.3 DSH 预设「音乐歌单」

新建了一个预设（**没有动你原有的 `chat` / `fe-work`**），在闲聊模式基础上挂一行 `mcp-client`：

```yaml
- id: mcp-apple-music
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    transport: stdio
    serverName: applemusic
    command: '<PYTHON>'
    args: ['<PROJECT_ROOT>\am_mcp_server.py']
    env: { PYTHONIOENCODING: utf-8 }
    cwd: '<PROJECT_ROOT>'
    toolCallTimeoutMs: 120000
    failOnStartupError: false
```

已用 `agentPresets.standingKeyFor('music')` 做过**真实挂载校验**：`MOUNT OK`。
挂载后工具名会带命名空间：`mcp__applemusic__am_create_playlist` 等。
想删掉这个预设，直接删除 `~\.dsh\.agent-presets\music\` 目录即可。

---

## 5. 上手步骤（本机三步已全部完成 ✅）

### 第 1 步（唯一需要人工的一步）：登录一次 —— ✅ 已完成

> 2026-09-21 实际执行结果：`✓ token 校验通过，storefront = cn`，
> `music-user-token` 已存入 `%APPDATA%\am-playlist\config.json`。
> 该令牌约 6 个月有效，到期后重跑一次本步即可。

```powershell
cd "<PROJECT_ROOT>"
python am_playlist.py login
```

三条获取 `music-user-token` 的路，脚本按顺序自动尝试：

1. **从 Apple Music Windows 客户端的 cookie 库读**（若你登录过那个客户端）——**登录后完全自动**；
2. **用 Playwright 开一个浏览器**，你在窗口里登录 Apple ID（含 2FA），脚本自动读 cookie 并保存
   ——需要装一次：`pip install playwright`（用系统 Edge，不额外下载 Chromium）；
3. **手动粘贴**（最稳，30 秒，零依赖）：
   浏览器打开 <https://music.apple.com> 并登录 → `F12` → Application → Cookies →
   `https://music.apple.com` → 双击 **`media-user-token`** 的 Value 全选复制 →
   ```powershell
   python am_playlist.py login --from-clipboard   # 直接从剪贴板读，不用粘贴到命令行
   # 或： python am_playlist.py login --token <值>
   ```
   `--from-clipboard` 会自动容错：多带了 `media-user-token=` 前缀、引号、或整行 cookie 都能处理。

> ⚠️ 注意：`media-user-token` 只有在**你已登录** music.apple.com 时才会存在。
> 如果 Cookies 列表里找不到它，说明当前浏览器没有登录 Apple Music，先去登录。
> 另外，`devToken`（那个 iframe URL 里的那串）**不是**它——那是开发者令牌，实测对 `/v1/me/*` 一律 403。

#### 关于"能不能直接读我浏览器里的 cookie"——实测结论

- **Edge / Chrome 本体：不行。** 实测本机 Edge 的 `Local State` 里同时存在
  `app_bound_encrypted_key` 和 `encrypted_key`，即已启用 **App-Bound Encryption（Chromium 127+）**。
  普通 Python 进程无法解密它——这是微软/Google 专门用来防这种读取的设计。
- **Apple Music Windows 客户端（WebView2）：可以。** 实测它的 `Local State` 里**只有** `encrypted_key`，
  没有 `app_bound_encrypted_key`，也就是仍是老的 **v10 + DPAPI** 方案：密钥由当前用户的 DPAPI 保护，
  同一用户下的脚本能解开。所以"**在商店版 Apple Music 应用里登录一次 → 之后脚本自动读 token**"
  是这台机器上最省事的全自动路线（AES-GCM 解密那一步需要 `pip install cryptography`）。
- 实测该客户端的 cookie 库当前是 **0 条记录**（从没登录过），所以第 1 条路现在走不通，
  需要你先在那个应用里登录一次。

成功后 token 存在 `%APPDATA%\am-playlist\config.json`（脚本会把它设成仅本人可读）。

### 第 2 步：全自动建歌单

```powershell
python am_playlist.py create --name "我的通勤歌单" --tracks "晴天 - 周杰伦, Bohemian Rhapsody - Queen"
```

### 第 3 步（可选）：在 DSH 里用

新建会话时选择预设 **「音乐歌单」**，然后直接说：

> 帮我建一个叫「深夜驾驶」的歌单，放 20 首 synthwave

Agent 会自己搜索、匹配、创建。工具不可用/未登录时它会明确告诉你先跑 `login`。

---

## 6. 想更进一步：全自动的几种"触发方式"

| 想要的效果 | 怎么做 |
|---|---|
| **每周自动生成一张歌单** | Windows 任务计划程序定时跑 `python am_playlist.py create --name "周推 $(Get-Date -f yyyyMMdd)" --json weekly.json`；`weekly.json` 由一个脚本/LLM 提前生成 |
| **按一句话生成整张歌单** | 让 LLM 输出 `[{"name":"歌名","artist":"艺人"}, ...]` 的 JSON → `create --json`（本工具已支持这种格式） |
| **从 Spotify / 网易云搬歌单** | 导出成 CSV，取 `歌名 + 艺人` 或 **ISRC**；有 ISRC 就用 `--isrcs`（精确匹配，25 首/请求，最不容易被限流） |
| **在 DSH 里随口让 Agent 建** | 用预设「音乐歌单」（§4.3） |
| **像 cron 一样无人值守** | 登录态约 6 个月有效；脚本在开发者 token 过期前会自动重抓。只要每半年重跑一次 `login` 即可 |

---

## 7. 已验证的 API 契约（可直接抄）

根地址：`https://api.music.apple.com/v1`（或 `https://amp-api.music.apple.com/v1`，等价）
必备请求头：
```
Authorization: Bearer <developer token>
Music-User-Token: <music-user-token>     # 只有 /me/* 需要
Origin: https://music.apple.com
```

**建歌单（含曲目，一次搞定）** —— `POST /v1/me/library/playlists` → `201`：
```json
{
  "attributes": { "name": "My Playlist", "description": "可选", "isPublic": false },
  "relationships": {
    "tracks": { "data": [ { "id": "1440857781", "type": "songs" } ] }
  }
}
```
`type` 用 `songs`（catalog 曲目）或 `library-songs`（已在音乐库里的曲目）。
成功响应里能拿到新歌单 ID（形如 `p.RB1AAkGsv74Zkl`）和 `canEdit: true`。

**追加曲目** —— `POST /v1/me/library/playlists/{id}/tracks` → `204`：
```json
{ "data": [ { "id": "1440857781", "type": "songs" } ] }
```

**搜索曲目** —— `GET /v1/catalog/{storefront}/search?term=...&types=songs&limit=5`

**按 ISRC 精确查** —— `GET /v1/catalog/{storefront}/songs?filter[isrc]=USRC17607839,...`（一次最多 25 个）

**校验登录态是否还有效** —— `GET /v1/me/storefront` → 200 表示 OK，403 表示要重新登录

---

### 7.1 四个很实用的技巧（建歌单时实测出来）

**① 艺人搜不到 ≠ 歌不在这个曲库——用 ISRC 反查。**
实测某个日本企划在 cn 曲库的**艺人检索里完全没有**（搜日文、英文、假名都返回空），
看起来像"该地区没有版权"。但拿 us 曲库的 ISRC 去反查，**cn 曲库命中 9 首**：

```
GET /v1/catalog/cn/songs?filter[isrc]=JPU901900411,JPU901804326,...
→ 1828863586 青春なんていらないわ / 1828863415 街路、ライトの灯りだけ / 1828863572 青に水底 ...
```

结论：**判断某首歌在不在某地区，要按 ISRC 查，不要按艺人名搜。** 这直接决定了能不能建歌单。

**② 跨区 ID 可以直接写进你的歌单（实测可行）。**
拿 us 曲库的 song id（如 `1538286504`）直接 POST 到 cn 账号的歌单里，
返回 201，回查确认曲目已进库（并变成了音乐库曲目 id `i.qQdG5E4TAqgAzve`）。
但这不代表它一定能播放——**优先用本区（cn）的等价 ID**，跨区 ID 只作为兜底。

**③ `composerName` 字段能用来核实"谁写的"。**
拉某艺人的歌时，`attributes.composerName` 会给出作曲者。
本轮就是靠它逐首筛，确认**某位作曲者给某个企划供曲的完整清单**：

| 曲目 | cn 曲库 ID |
|---|---|
| 青春なんていらないわ | 1828863586 |
| 街路、ライトの灯りだけ | 1828863415 |
| 青に水底 | 1828863572 |
| 恋を落とす | 1538286282 |
| 花に夕景 | 1828863576 |

（注意：该字段可能只列一位作曲者，不保证完整，所以"没列出来"不等于"不是他写的"。）

**④ `/catalog/{sf}/artists/{id}/songs` 的 `limit` 上限是 20。**
传 `limit=100` 会直接 400：`Value must be an integer less than or equal to 20`。
想拉全量要跟着响应里的 `next` 翻页；注意 `next` 已经带 `/v1` 前缀，别再拼一次根路径。

---

### 7.2 怎么做出"策展"而不是"聚合"（本项目踩过的弯路）

第一版歌单是「每位艺人取搜索结果前 20 首」——那是**聚合**，不是品味。改进的做法：

1. **拉全量再挑，别用前 N 首。** `artists/{id}/songs` 分页能拿到全部
   （实测某位艺人在 cn 有 **160 首 / 58 张专辑**，而搜索接口只喂给你最热的那几首单曲）。
   按 `albumName` 分组，就能看到"哪些是单曲、哪些是专辑曲"——**专辑曲才是深挖的地方**。
2. **必须校验时长。** 这一步救了大命：`だから僕は音楽を辞めた` 里的 `8/31`、`7/13`、
   `負け犬にアンコールはいらない` 里的 `前世`、`落下`、`盗作` 里的 `Adolescent, Burglar`、
   以及 `朝靄、雨が止む` —— 全是 **1:14 ~ 1:38 的间奏**，不是歌。靠 `durationInMillis` 一次筛掉：
   ```python
   sec = attrs["durationInMillis"] // 1000
   if sec < 120: skip   # 间奏 / 前奏曲
   ```
3. **用一条线索串起来，而不是按艺人分块。** 本项目用的线索是**作曲者血脉**：
   某位制作人的ボカロ原点 → 他自己的乐队 → 他写给别人的歌 → 同气质的另外两组艺人。
   这条线索完全来自数据（`composerName` 字段），不是硬编的。
4. **善用 `composerName` 做交叉发现。** 例如拉某个企划的 120 首，按作曲者分组后发现
   它其实是个**制作人展示企划**：40mp、Jin、BuzzG、Scop、mikitoP、Harumakigohan、Iyowa、
   Nayutanseijin、MIMI、yashikin…… 每位ネット系制作人各供一曲。
   想扩到"同一位制作人写过的其他歌手"，这就是现成的入口。
5. **正式版本 vs 现场/重录/伴奏版**：`VERSION_NOISE` 那套扣分逻辑（§2 第 6 条）在策展时同样适用。
6. **"间奏也要"是一种风格选择，但要自觉。** 如果确实想保留 1 分钟的氛围曲，放在乐章交界处当过渡，
   别散落在歌单中段。

---

## 8. 风险与注意事项（请认真看）

1. **这是"社区路径"，不是 Apple 官方支持的用法。**
   抓网页 token 的做法与 Cider、Music Assistant 等开源客户端一致，属于个人自用范畴。
   Apple 改了前端结构，抓取就会失败（脚本会明确报错，更新一下即可）。
   **不要拿去做商业分发**，也不要违反 Apple 的服务条款。
2. **`config.json` 里的 `music-user-token` 等同于你音乐库的读写凭证**（约 6 个月有效）。
   不要提交到 Git、不要发给别人、不要放在共享目录。脚本已把它保存在你自己的用户配置目录并设权限。
3. **别高频轮询。** 尤其别用网页 token 做大规模批量搜索——429 之后整个 60 分钟窗口都会受影响。
4. **只能改"自己建的"歌单**（§2 第 1 条），这是 Apple 的服务端限制，不是本工具的缺陷。
5. 本工具只做**歌单**相关的读写，不碰播放、下载、DRM 内容。

---

## 9. 参考来源

- Apple 官方文档（本报告中的契约均从官方 docc JSON 提取）：
  [Create a New Library Playlist](https://developer.apple.com/documentation/applemusicapi/create-a-new-library-playlist)、
  [Add Tracks to a Library Playlist](https://developer.apple.com/documentation/applemusicapi/add-tracks-to-a-library-playlist)、
  [Generating Developer Tokens](https://developer.apple.com/documentation/applemusicapi/generating-developer-tokens)、
  [User Authentication for MusicKit](https://developer.apple.com/documentation/applemusicapi/user-authentication-for-musickit)、
  [Handling Requests and Responses](https://developer.apple.com/documentation/applemusicapi/handling-requests-and-responses)
- 同类开源项目（佐证"网页 token"路径是成熟做法）：
  [epheterson/applemusic-mcp](https://github.com/epheterson/applemusic-mcp)（跨平台 MCP 服务，
  明确说明 Windows/Linux 走 Chrome 登录抓取 web token；并指出批量操作要换开发者 token 否则 429）、
  [Cider](https://github.com/ciderapp/Cider-2)、
  [Music Assistant](https://www.music-assistant.io/music-providers/apple-music/)
- 本机实测证据留在 `apple-music-auto\refs\`（Apple 文档 JSON、网页 bundle、请求响应样本）

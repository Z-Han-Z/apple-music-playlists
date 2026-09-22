---
name: apple-music-playlists
description: Use when creating, curating, auditing, or reordering Apple Music playlists — anything involving the am_* MCP tools or the am_playlist.py / playlist_flow.py / playlist_audit.py / playlist_optimize.py scripts, fetching playback credentials, looking up a track's BPM/key/energy/valence, choosing a track order, or diagnosing an Apple Music API 401/403/429. Also use when asked to build a themed playlist, judge whether a playlist flows, or clean up playlists and test artifacts.
---

# Apple Music 歌单：创建、体检、排序

一套通用工具链。**本项目不含任何艺人清单或主题**——内容由使用者提供。

**代码位置**：本 skill 所在仓库的根目录。若已按 `preset/` 的说明挂载了 MCP，工具名形如
`mcp__applemusic__am_create_playlist`。

**凭证**：`%APPDATA%\am-playlist\config.json`（Windows）/ `~/.config/am-playlist/config.json`。
登录一次约 6 个月有效。详见仓库的 `SETUP.md`。

---

## 一、什么时候用哪一层

| 用户想要 | 用什么 |
|---|---|
| 建歌单 / 加歌 / 查曲目 | MCP 工具（`am_*`）或 `am_playlist.py` |
| "这张歌单怎么样" | `am_audit_playlist`（元数据层）+ `am_analyze_flow`（听感层） |
| "帮我排一下顺序" | `playlist_optimize.py`（见 §三） |
| 排查 API 报错 | 先看 §四 |

**MCP 工具（11 个）**

```
am_status            先查这个：token 是否有效、是否已登录
am_search_songs      catalog 搜索，返回 song id
am_list_playlists    列出音乐库歌单
am_show_playlist     看某歌单的曲目
am_create_playlist   主入口：建歌单 + 一次性写入曲目
am_add_tracks        向已有歌单追加
am_delete_playlist   删除（必须 confirm=true）
am_audit_playlist    元数据层体检
am_analyze_flow      听感体检（BPM/调性/响度/能量/情绪 + 相邻衔接 + 弧线形状）
am_recently_played   最近播放（曲目 / 歌单 / 电台 / 最近入库）
am_top_played        播放次数排行（songs / albums / artists × 年份或 all-time）
```

**动手前先 `am_status`。** 未登录时不要反复重试——直接让用户跑一次 `python am_playlist.py login`。

---

## 二、命令行

```bash
python am_playlist.py status                 # token 状态
python am_playlist.py login                  # 一次性获取 user token
python am_playlist.py login --from-clipboard # 从剪贴板读（先在 DevTools 复制 cookie）
python am_playlist.py logout [--keep-developer]
python am_playlist.py search "关键词" --storefront us
python am_playlist.py list
python am_playlist.py show "歌单名"
python am_playlist.py create --name "X" --tracks "歌名 - 艺人, ..." [--dry-run]
python am_playlist.py create --name "X" --json tracks.json     # 批量/脚本化
python am_playlist.py add --playlist "X" --tracks "..."
python am_playlist.py delete "X" --yes

python playlist_audit.py     "歌单名"              # 元数据层体检
python playlist_flow.py      "歌单名" [--refresh]  # 听感层体检（联网抓特征）
python playlist_optimize.py  清单.json [-o 输出.json] [--features 缓存.json]
```

**`--json` 输入格式**（顺序保留；三种写法可混用）：

```json
{"tracks": ["1440857781", "Song Title - Artist Name", {"id": "1440857782", "name": "optional label"}]}
```
- 纯数字字符串 / `{"id": ...}` = **钉死 catalog id**，跳过搜索（要精确版本时用）
- `"歌名 - 艺人"` = 走搜索匹配
- 也接受 `tracks_in_order` / `items` / `songs` 作键名

---

## 三、排序：怎么排出一个「好听又有意思」的顺序

完整依据见仓库 `docs/how-to-build-a-good-playlist.md`（含 PLOS ONE 2025 的实证数据表）。

### 3.1 先选一个形状

六种叙事弧（Reagan et al. 2016 实证）：`rags to riches`（持续升）、`tragedy`（持续降）、
**`man in a hole`（先落再起）**、`icarus`（先起再落）、`cinderella`（起落起）、`oedipus`（落起落）。

**专业音乐人排专辑时偏向 `man in a hole`。** 30 首以上建议用"两个连续的 man-in-a-hole"——
一个 40 分钟的大弧太难撑。**先选形状并写下来**，它是后面所有决定的裁判。

### 3.2 四条硬性相邻规则

1. **不要两首慢歌相邻**
2. **不要"只慢一点"**——降幅 0–12% 会让那首慢歌听起来像在拖。要降就一次降够，或者中间插过渡
3. **相邻不该在 tempo 和 key 上「同时」相似**——节奏相近就拉开调性，反之亦然
   （Camelot：同码 / ±1 同字母 / 同号 A↔B 互换 = 兼容）
4. **不要 BPM 无理由大跳（>40%）**；能量骤变 + 调性不兼容 = 突兀

> **⚠️ 规则 1 有一个数学边界，那不是排列失败。**
> 在一段**刻意安静**的段落里（"深夜""前奏""夜明け前"），如果慢歌比快歌多出 1 首以上，
> **无论怎么排都必然剩下相邻的慢歌对**——2 首快歌最多把 5 首慢歌切成 3 段，
> 最少剩 `5 − 2 − 1 = 2` 对。
> 实测：把 `W_TWO_SLOW` 从 6 提到 16，违规数**一模一样还是 2 处**，只是惩罚被放大，
> 总 cost 反而从 15.93 涨到 35.92。**遇到这种情况不要继续加权重**——
> 那是段落选曲的问题（接受它，或往这段补几首快歌），不是排序问题。

### 3.3 整体弧线

```
valence  → U 型（两端高）      ← man in a hole
energy   → U 型
loudness → U 型
tempo    → 倒 U 型（两端慢、中段快）
```
**第一首是专业人共识最高、最该单独打磨的位置。** 开场情绪按 ISO 原则：
**先匹配听众当下状态，再引导**，而不是一上来就最炸。

### 3.4 用优化器算，而不是手排

`playlist_optimize.py` 用模拟退火，在**保留分组顺序**的约束下只做组内重排，
最小化「4 项相邻惩罚 + 4 项弧线形状偏差」。

输入清单两种格式：

```json
// ① 分组（推荐：保留主题/叙事结构，只在组内重排）
{"blocks": [ {"id":"A","title":"起","tracks":["...","..."]},
             {"id":"B","title":"承","tracks":["..."]} ]}

// ② 平铺（整张自由重排）
{"tracks": ["...", "..."]}
```

特征数据来自 `playlist_flow.py` 生成的缓存（按 catalog id 索引，自动匹配）。

**权重在文件顶部**（`W_TWO_SLOW` / `W_ARC` 等）。想让形状优先就调大 `W_ARC`；想更顺耳就调大相邻那几项。
**这两个目标会打架，得明确取舍**——实测同一份 39 首清单：保留分组时 cost 降到 19.41，
完全自由重排能降到 1.28（相邻惩罚归零）。**分组本身是有代价的。**

### 3.5 "有意思"那一层（最容易做丢）

- **材料要够杂，气质要统一**——全是同一流派同一时期的歌，再顺也不会"有意思"
- **找一条线索**，让顺序本身成为论证。可自动化的线索来源：
  `composerName`（作曲者血脉）、`albumName` + `trackNumber`（专辑深挖曲）、`releaseDate`（时间线）
- **避开单曲**。搜索接口只给你最热的那几首；`/catalog/{sf}/artists/{id}/songs` 分页能拉全量
  （实测某位艺人在 cn 有 160 首 / 58 张专辑），按 `albumName` 分组才能看到专辑曲

### 3.6 最后一步只能靠耳朵

整张按顺序听一遍，记录**第几首想按跳过**。想跳的位置就是问题位置。
工具能保证你不犯已知的物理错误，但"好听"的最终裁判仍是耳朵。

> ⚠️ 别把排序规则当物理定律：PLOS 自己承认**效应量很小**，并引用了一项
> "把贝多芬乐章随机打乱既不影响愉悦度也不影响情绪冲击力"的研究。

---

## 四、坑（全部实测踩过）

### 4.1 数据获取

| 坑 | 事实 |
|---|---|
| **Apple API 没有音频特征** | catalog 只返回 `albumName artistName artwork composerName discNumber durationInMillis genreNames hasLyrics isrc name playParams previews releaseDate trackNumber url`。**没有** tempo/key/loudness/energy/valence/mood |
| **Spotify `audio-features` 已死** | 2024-11-27 对新应用关闭（同日还下线了 `audio_analysis` / `recommendations` / related artists）。无官方替代 |
| **AcousticBrainz 已关闭** | 2022 年关站，数据以一次性 dump 冻结（7.5M 曲目；有 MBID 的约 60% 覆盖） |
| **可行链路** | `Apple → ISRC → api.reccobeats.com/v1/track?ids=<ISRC> → UUID → /v1/audio-features?ids=<UUID>`。**免费、无需密钥**，返回 Spotify 那 11 项 |
| **Apple 的 `include=audio-analysis`** | 返回 **400 Insufficient Permissions**——关系存在，只是网页 token 权限不够。**用自己的 MusicKit 密钥可能能拿到（未验证）** |
| **试听片段** | `previews[0].url` 可下载（`audio/x-m4p`，约 1MB，m4a/AAC）。要本地分析得先装解码器（ffmpeg / librosa） |

### 4.2 API 行为

| 坑 | 事实 |
|---|---|
| **响应可能是 gzip** | 即使请求里**没有** `Accept-Encoding`，Apple 也会返回 `Content-Encoding: gzip`。不解压会误判成"响应体空" |
| **两个主机不等价** | `DELETE /me/library/playlists/{id}` 与 `DELETE /me/library/songs/{id}` 在 `api.music.apple.com` **固定 401**，在 `amp-api.music.apple.com` **正常**（204）。**删除必须走 amp-api** |
| **别发 `x-apple-client-version`** | 加到 amp-api 上会变成 500 Upstream Service Error |
| **只有创建者能改** | Apple 限制：只有创建该歌单的那个客户端能写它。手机上手动建的歌单，API 写入 403 |
| **建歌单会污染音乐库** | 创建时曲目会被**顺带加进音乐库**（歌单内曲目带 `i.` 前缀且 `isLibrary: true`）。删歌单**不会**移除库内曲目 |
| **iCloud 传播延迟** | 新建的歌单要等几秒到几十秒才出现在 `/me/library/playlists`。**所以创建时要一次性带上曲目** |
| **429 限流** | 网页 token 的配额**共享**，窗口约 60 分钟且滚动，无 `Retry-After`。批量导入要换自己的 `.p8` |
| **`/artists/{id}/songs` 的 limit 上限是 20** | 传 100 会 400。翻页时 `next` 已带 `/v1` 前缀，别再拼根路径 |

### 4.3 匹配与排序

| 坑 | 事实 |
|---|---|
| **搜索词不要带 `" - "`** | 拿 `"Title - Artist"` 整串去搜，前几条**全是 Live/Remastered**；用空格分隔才正常。`resolve_tracks()` 已做转换 |
| **版本后缀要扣分** | Live / Remastered / Demo / 现场 / 伴奏——查询里没提到却在曲名里出现就扣分（`VERSION_NOISE`） |
| **BPM 有倍频歧义** | 同一首可能被估成 90 或 180。**比较前把 BPM 折进 [70,160)**，否则"两首慢歌相邻"会误报约 4 倍 |
| **时长能筛掉间奏** | `durationInMillis < 120000` 的基本是间奏/前奏曲，不是歌 |
| **艺人搜不到 ≠ 歌不在本区** | 某日本企划在 cn 的**艺人检索为空**，但用 ISRC 反查 **cn 曲库命中 9 首**。判断某歌在不在某区要按 ISRC 查 |

### 4.4 收听历史（最近播放 / 播放次数）

**这两样在完全不同的接口里，别找错地方。**

| 想要 | 端点 | 有播放次数吗 |
|---|---|---|
| 最近播放的**曲目** | `/v1/me/recent/played/tracks`（默认 30 条） | ❌ |
| 最近播放的**歌单/专辑** | `/v1/me/recent/played` | ❌ |
| 最近听的电台 | `/v1/me/recent/radio-stations` | ❌ |
| 最近加入音乐库 | `/v1/me/library/recently-added` | ❌ |
| **播放次数** | `/v1/me/music-summaries/...` ← **只在这里** | ✅ |

**播放次数（Apple Music Replay / 音乐回忆 后端）**——官方文档里**没有**，是从网页播放器的
Replay 组件 bundle（`/includes/music-replay/build/replay.esm.js`）里挖出来的：

```
GET /v1/me/music-summaries/search?period=year,all-time     → 有哪些期间可查
GET /v1/me/music-summaries/year-2026/view/top-songs        → song-period-summaries
GET /v1/me/music-summaries/year-2026/view/top-albums       → album-period-summaries
GET /v1/me/music-summaries/year-2026/view/top-artists      → artist-period-summaries
```

每条返回：

```json
{"id":"eWVhci0yMDI2LXNvbmctMTY1NzMxODg4NA","type":"song-period-summaries",
 "attributes":{"playCount":57,"firstPlayed":"2026-01-13T19:54:12Z",
               "lastPlayed":"2026-09-02T07:54:46Z","year":"2026"},
 "relationships":{"song":{"data":[{"id":"1657318884","type":"songs"}]}}}
```

- `id` 是 **base64**，解开就是可读的 `year-2026-song-1657318884`
- `relationships.song.data` 是**数组**，且只给 id —— 要曲名得再去 `/v1/catalog/{sf}/songs?ids=` 查
- 分页用 `offset`（`limit` 有上限，传 200 会 400）
- **只在 `amp-api.music.apple.com` 上稳定**；官方主机对部分期间返回 404
- **`all-time` 不一定存在**（实测某账号 404）——先跑 `search?period=year,all-time` 看有哪些
- Apple 返回的顺序与 `playCount` **并非严格一致**，展示前自己按次数重排

命令行封装在 `listening_stats.py`：

```bash
python listening_stats.py periods                                  # 有哪些期间
python listening_stats.py top --kind songs --year 2026 --limit 30  # 播放次数排行
python listening_stats.py recent --kind tracks --limit 30          # 最近播放
```

---

## 五、参考文件

- `reference.md`（同目录）—— API 契约速查：端点、请求体、Camelot 映射表、字段清单、错误码
- 仓库 `docs/how-to-build-a-good-playlist.md` —— 策展原则的完整依据与实证数据
- 仓库 `docs/apple-music-api-notes.md` —— 令牌模型与路径决策矩阵
- 仓库 `SETUP.md` —— 凭证配置

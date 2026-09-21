# Apple Music API 契约速查

所有条目都在本项目实测过（2026-09，Windows，python 3.12，网页 token）。
根地址：`https://api.music.apple.com/v1` 或 `https://amp-api.music.apple.com/v1`（**不等价，见 §5**）

---

## 1. 请求头

```
Authorization: Bearer <developer token>       # 所有请求都要
Music-User-Token: <music-user-token>          # 只有 /me/* 需要
Origin: https://music.apple.com               # 网页 token 的 root_https_origin 是 ["apple.com"]
Accept-Encoding: gzip
```

## 2. 端点

### 建歌单（创建时一次性带曲目）→ `201`
```
POST /v1/me/library/playlists
{
  "attributes": { "name": "My Playlist", "description": "可选", "isPublic": false },
  "relationships": { "tracks": { "data": [ { "id": "1440857781", "type": "songs" } ] } }
}
```
成功响应（**注意：响应体是 gzip 的**）：
```json
{"data":[{"id":"p.XMrmpXOcvXJvqKM","type":"library-playlists",
  "attributes":{"name":"...","canEdit":true,"dateAdded":"2026-09-21T07:52:32Z",
                "hasCatalog":false,"isPublic":false,"playParams":{"id":"p.XMrmpXOcvXJvqKM","isLibrary":true}}}]}
```
- `type` 用 `songs`（catalog 曲目）或 `library-songs`（已在库里的）
- 单次上限 100 首，超过要分批
- 歌单 ID 形如 `p.XXXXXXXXXXXXXXX`

### 追加曲目 → `204`
```
POST /v1/me/library/playlists/{id}/tracks
{ "data": [ { "id": "1440857781", "type": "songs" } ] }
```

### 删除歌单 → `204`（**必须走 amp-api**）
```
DELETE https://amp-api.music.apple.com/v1/me/library/playlists/{id}
```

### 曲目移出音乐库 → `204`（**必须走 amp-api**）
```
DELETE https://amp-api.music.apple.com/v1/me/library/songs/{librarySongId}
```
（`librarySongId` 形如 `i.LVk6LXgtlGDlpbW`，从歌单曲目的 `id` 或 `playParams.id` 拿）

### 读
```
GET /v1/me/library/playlists?limit=100
GET /v1/me/library/playlists/{id}/tracks?limit=100
GET /v1/me/storefront                                  # 校验登录态：200 = OK
GET /v1/catalog/{sf}/search?term=...&types=songs&limit=8
GET /v1/catalog/{sf}/songs?ids=a,b,c                   # 批量，每批 ≤100
GET /v1/catalog/{sf}/songs?filter[isrc]=A,B,C          # ISRC 精确匹配，每批 ≤25
GET /v1/catalog/{sf}/artists/{id}/songs?limit=20       # limit 上限 20！跟着 next 翻页
```
翻页注意：响应里的 `next` **已经带 `/v1` 前缀**，别再拼根路径（否则 `/v1/v1/...` → 404）。

### 艺术家页的 view
```
GET /v1/catalog/{sf}/artists/{id}/view/top-songs          # 200，10 首
GET /v1/catalog/{sf}/artists/{id}/view/featured-playlists # 200（不一定有）
GET /v1/catalog/{sf}/artists/{id}/view/similar-artists    # 404 No related ...（cn 无数据）
```

---

## 3. song 的属性字段（实测完整清单）

```
albumName  artistName  artwork  composerName  discNumber  durationInMillis
genreNames  hasLyrics  isAppleDigitalMaster  isrc  name  playParams
previews  releaseDate  trackNumber  url
```

**没有** tempo / key / mode / loudness / energy / valence / danceability / mood。
`artwork` 里带 `bgColor` / `textColor1..4`（六位色值），可用于封面配色统一。

`composerName` 是单值字符串，**可能只列一位作曲者，不保证完整**——"没列出来"不等于"不是他写的"。
用它筛供曲是可行的（实例：从三月のパンタシア 的 120 首里筛出 n-buna 的 9 条记录 → 去重 5 首）。

---

## 4. 音频特征：实测可用的链路

```
Apple song.isrc
  → GET https://api.reccobeats.com/v1/track?ids=<ISRC>       免费、无需密钥
      → {"content":[{"id":"<uuid>","trackTitle":...,"isrc":...}]}
  → GET https://api.reccobeats.com/v1/audio-features?ids=<uuid>
      → {"content":[{"tempo":71.068,"key":0,"mode":0,"loudness":-9.928,
                     "energy":0.404,"valence":0.226,"danceability":0.411,
                     "acousticness":0.271,"instrumentalness":0.0,
                     "liveness":0.3,"speechiness":0.0511}]}
```

也可 `GET /v1/track/<uuid>/audio-features`（返回单个对象）。
另有 `POST /v1/analysis/audio-features`（上传音频文件，≤5MB / ≤30 秒，支持 MP3/OGG/AIFF/WAV，
**不支持 m4a/AAC**）——需要 401 的部分要 API key。

**覆盖率**：日文曲目（ヨルシカ / あたらよ / 藍空と月 / 三月のパンタシア）实测 14/14；
一张 39 首歌单里 37 首命中（缺的是 2025/2026 新单曲）。**建议 sleep 0.3s 礼貌抓取。**

---

## 5. 两个主机不等价（重要）

| 操作 | `api.music.apple.com` | `amp-api.music.apple.com` |
|---|---|---|
| `GET /catalog/...` | ✅ | ✅ |
| `POST /me/library/playlists` | ✅ 201 | ✅ 201 |
| `POST .../{id}/tracks` | ✅ | ✅ |
| **`DELETE .../playlists/{id}`** | ❌ **401** | ✅ **204** |
| **`DELETE .../songs/{id}`** | ❌ **401** | ✅ **204** |
| 带 `x-apple-client-version` 头 | 仍 401 | ❌ **500 Upstream Service Error** |

（注：`DELETE` 在官方主机上 401 是 Apple 侧的已知问题，非本项目 bug。）

---

## 6. Camelot 映射表

Spotify 的 `key` 是 0–11 的半音序号，`mode` 0=小调 / 1=大调。

```
音名:    C   C#   D   D#   E    F   F#   G   G#   A   A#   B
小调(A): 5A  12A  7A  2A   9A   4A  11A  6A  1A   8A  3A   10A
大调(B): 8B  3B   10B 5B   12B  7B  2B   9B  4B   11B 6B   1B
```

**兼容的四种移动**：同码 / 编号 ±1（同字母）/ 同编号 A↔B / 环形相邻 `12A↔1A`、`12B↔1B`。

---

## 7. 错误码

| 码 | 含义与处理 |
|---|---|
| **401** | developer token 无效；或对 `api.music.apple.com` 做了 DELETE（换 amp-api） |
| **403** `Authentication required for request` (code 40300) | 缺 `Music-User-Token`，或该 token 已失效（约 6 个月），需重新 `login` |
| **403** 写入失败 | 该歌单不是本客户端创建的（Apple 限制只有创建者可写） |
| **429** | 限流。网页 token 配额共享，窗口约 60 分钟且滚动，**无 `Retry-After`**。短时间重试会延长限流 |
| **400** `Value must be an integer less than or equal to 20` | `/artists/{id}/songs` 的 limit 超了 |
| **400** `Insufficient Permissions` | 请求了 `include=audio-analysis`（网页 token 权限不够） |
| **404** | 路径拼错（常见：`next` 返回值又拼了一次 `/v1`） |
| **405** | 方法或路径不对（对照组：故意写错路径会得到这个而不是 403） |

---

## 8. Token

| | 来源 | 有效期 | 获取 |
|---|---|---|---|
| **developer token** | ① 网页 bundle 里内嵌的公开 token（`iss: AMPWebPlay`）② 自己的 MusicKit `.p8` | 网页版约 70 天；自己签 ≤6 个月 | 脚本自动从 `music.apple.com` 的前端 bundle 正则抓取；过期自动重抓 |
| **music-user-token** | 登录后的 `media-user-token` cookie | 约 6 个月 | `am_playlist.py login` |

抓取实现：取 `music.apple.com/us/browse` → 找 `/assets/index~*.js` → 正则 `eyJ...` → 解 JWT 取 `iss == AMPWebPlay`。

配置落在 `%APPDATA%\am-playlist\config.json`（脚本会设成仅本人可读）。
**这个文件等同于音乐库的读写凭证，别外传、别提交到 Git。**

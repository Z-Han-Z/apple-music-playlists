# Apple Music Playlist Toolkit

**Build, analyze, and sequence Apple Music playlists from the command line or an MCP-capable agent.**

Pure Python standard library — no `pip install` required to run, and **no Apple Developer Program
membership needed**. Works on Windows / macOS / Linux.

> This is a **general-purpose** playlist toolkit. It ships no artist lists, no themes, and no
> curated content — you bring the tracks.

```
  create  →  audit  →  fetch audio features  →  optimize order  →  rebuild
```

---

## Quick start

```bash
git clone https://github.com/<you>/apple-music-playlists.git
cd apple-music-playlists

python am_playlist.py status     # auto-fetches the developer token
python am_playlist.py login      # one-time Apple ID sign-in (~6 months validity)

python am_playlist.py create --name "My Playlist" \
    --tracks "Song A - Artist X, Song B - Artist Y"
```

See **[SETUP.md](SETUP.md)** for the credential walkthrough (three ways to get the user token,
including a zero-dependency one).

---

## What's in the box

| File | Purpose |
|---|---|
| `am_playlist.py` | Core: token management, catalog search, create / edit / delete playlists, track resolution |
| `am_mcp_server.py` | MCP (stdio) server exposing **11 tools** to any MCP client |
| `playlist_audit.py` | **Metadata audit**: length, artist concentration, genres, eras, durations, duplicates, interludes |
| `playlist_flow.py` | **Audio-feature audit**: BPM / key / loudness / energy / valence, adjacency checks, arc shape |
| `playlist_optimize.py` | Simulated-annealing **track ordering** against the measured rules |
| `listening_stats.py` | **Listening history**: recently played, and per-track/album/artist **play counts** (Apple Music Replay backend) |
| `profile_library.py` | **Taste profile**: what your most-played music actually sounds like (BPM / energy / valence spread, mood quadrants) |
| `am_library.py` | **Your library**: paged export of every catalog-backed song you own, enriched with ISRC / year / genre |
| `build_pool.py` | **Candidate pool**: pick a pool out of your library (most-played → favourite artists → variety filler) and fetch its features |

Supporting modules:

| File | Purpose |
|---|---|
| `playlist_core.py` | **Platform-neutral core**: Camelot, BPM folding, the four adjacency rules, the six narrative shapes. Imports nothing from this project and nothing third-party |
| `am_paths.py` | Platform-neutral paths and version — where config and cache live |
| `am_meta.py` | The single `catalog_meta` implementation (batched catalog lookups) |

All three analysis modules are importable as libraries:

```python
import playlist_flow, playlist_audit, playlist_optimize

print(playlist_flow.flow_report("My Playlist"))          # -> str
print(playlist_audit.audit_report("My Playlist"))        # -> str
ids, report = playlist_optimize.optimize("stack.json")   # -> (list[str], str)
```

### MCP tools

`am_status` · `am_search_songs` · `am_list_playlists` · `am_show_playlist` ·
`am_create_playlist` · `am_add_tracks` · `am_delete_playlist` ·
`am_audit_playlist` · `am_analyze_flow` · `am_recently_played` · `am_top_played`

Mount it in a Cordis agent preset with the template in [`preset/`](preset/), or wire it into
any other MCP client with:

```json
{ "mcpServers": { "applemusic": {
    "command": "python", "args": ["/abs/path/am_mcp_server.py"] } } }
```

---

## Tests

```bash
python -m unittest discover -s tests -v
```

104 tests, all **offline** — no network, no credentials. Two kinds:

- **Behaviour**: the pure math that decides what "sounds good" — Camelot mapping, BPM folding,
  arc classification, each adjacency penalty asserted in isolation, annealing determinism and the
  block-order constraint. All six narrative archetypes must classify as themselves.
- **Structural regressions**, each pinned to a bug that actually shipped: no hardcoded catalog
  region, exactly one `catalog_meta`, no non-`None` `--storefront` default, cache outside the
  repo, every MCP tool wired to a handler, and the optimizer free of platform imports.

They earn their keep immediately — the suite caught a syntax error in a file written minutes
earlier, before it was ever run.

---

## The interesting part: audio features

**Apple's catalog API exposes no audio features at all** — no tempo, key, loudness, energy, or
valence. Spotify's `audio-features` endpoint was shut off for new apps on 2024-11-27, and
AcousticBrainz retired in 2022.

`playlist_flow.py` bridges the gap with a free, key-less chain built on **ISRC**, which Apple *does*
return:

```
Apple Music track  ──►  ISRC
                          │
                          ├─► api.reccobeats.com/v1/track?ids=<ISRC>   → track UUID
                          │        └─► /v1/audio-features?ids=<UUID>
                          │                 → tempo, key, mode, loudness, energy, valence,
                          │                   danceability, acousticness, instrumentalness,
                          │                   liveness, speechiness
                          └─ (fallback) musicbrainz.org ISRC lookup
```

Results are cached locally, so the network cost is paid once per playlist.
Coverage measured: 37/39 on a recent-release test set; 14/14 on Japanese-language tracks.

---

## Sequencing rules the optimizer enforces

Derived from the research collected in [`docs/`](docs/) — including a PLOS ONE study in which
130 music professionals sequenced albums, and a randomized trial on mood-adaptive music ordering.

**Hard adjacency rules**
- No two slow tracks adjacent
- Avoid "only slightly slower" transitions (0–12% drop makes the slower track feel like it drags)
- Adjacent tracks must not be similar in **both** tempo and key
- No unjustified large BPM jumps (>40%); no jarring energy shifts under incompatible keys

These four have **exactly one definition**, in `playlist_core.check_pair()`, and both the audit and
the optimizer call it. They used to be implemented twice, and the copies disagreed: the audit
called a track "slow" below the tempo's 25th percentile while the optimizer used a fixed 100 BPM,
and the audit never checked the BPM-jump rule at all. That is a tool diagnosing against one
standard and repairing against another — so the count it reported could not be trusted.

> **Note on the "slow" threshold.** It is absolute (100 BPM), not data-driven, deliberately: the
> optimizer evaluates the same sequence thousands of times while annealing, and a percentile
> threshold would drift as the permutation changes, so the cost would never settle. The cost is
> that a uniformly slow playlist flags *every* adjacent pair — that is real, not a sequencing
> failure, and the report says so.

**Global arc** (matching the professional consensus)
- `valence`, `energy`, `loudness` → **U-shaped** (high at both ends, lower in the middle)
- `tempo` → **inverted U**
- overall shape defaults to **man-in-a-hole** (fall, then rise)

> **Known gap.** The report *classifies* your playlist against all six narrative shapes, but the
> optimizer only ever *targets* man-in-a-hole (a valence valley at 60%). Choosing a different target
> shape is not wired up, even though the curation doc presents shape selection as the first decision.

The optimizer preserves your grouping (movements / eras / moods) and only reorders *within*
groups, so thematic structure survives the loudness tuning. Drop the grouping and it reorders
freely — measurably "smoother", at the cost of your narrative.

Example from a real run: cost **104.46 → 19.41** with grouping preserved, **→ 1.28** ungrouped.

---

## Gotchas worth knowing before you debug

- **Responses can be gzip-compressed even when you never sent `Accept-Encoding`.** Decoding the
  raw bytes as UTF-8 yields garbage that looks like an empty body. (This is fixed in `am_playlist.py`.)
- **`DELETE` only works on `amp-api.music.apple.com`.** The documented host `api.music.apple.com`
  returns 401 for playlist and library-song deletion.
- **Do not send `x-apple-client-version`** to amp-api — it turns into a 500.
- **Creating a playlist also adds its tracks to the library.** Deleting the playlist does not
  remove them.
- **BPM estimates have octave ambiguity** (90 vs 180 for the same track). Fold into `[70,160)`
  before comparing, or "two slow tracks adjacent" over-reports by ~4×.
- **Never pass `"Title - Artist"` straight into catalog search** — you get live/remastered takes.
  Search on the space-separated form and score versions afterwards.
- **An artist missing from a storefront's search ≠ the song is unavailable there.** Look it up by ISRC.
- **Only the client that created a playlist can modify it** — Apple-side restriction.

More in [`docs/apple-music-api-notes.md`](docs/apple-music-api-notes.md) and
[`skill/reference.md`](skill/reference.md).

---

## Documentation

| Doc | Contents |
|---|---|
| [`SETUP.md`](SETUP.md) | Credentials: what tokens exist, how to get each one, security notes, troubleshooting |
| [`docs/apple-music-api-notes.md`](docs/apple-music-api-notes.md) | Token model, endpoint contracts, measured API behaviour, eval of 7 automation approaches |
| [`docs/how-to-build-a-good-playlist.md`](docs/how-to-build-a-good-playlist.md) | Curation methodology: adjacency physics, arc data, six narrative shapes, the ISO principle |
| [`docs/playlist-curation-survey.md`](docs/playlist-curation-survey.md) | Survey of published curation guidance (platform rules, DJ methods, academic findings) |
| [`docs/platform-adapters.md`](docs/platform-adapters.md) | The platform-adapter boundary: what is platform-neutral, what an adapter must provide, and what breaks on a service that exposes no ISRC |
| [`skill/`](skill/) | Agent skill: workflow + the accumulated gotcha list |
| [`preset/`](preset/) | Cordis agent preset template that mounts the MCP server |

---

## 中文说明

**通用 Apple Music 歌单工具链**：命令行创建 / 编辑歌单、抓音频特征、体检歌单、按听感规则重排曲序。
纯标准库，不需要 `pip install`，也不需要 Apple Developer Program（$99/年）。

**免责声明**：本项目不含任何艺人清单、主题或成品歌单——内容由你提供。

```bash
python am_playlist.py status                 # 自动抓取 developer token
python am_playlist.py login                  # 一次性登录（约 6 个月有效）
python am_playlist.py create --name "歌单名" --tracks "歌名 - 艺人, ..."

python am_playlist.py library                # 导出音乐库（含 ISRC；build_pool 的输入）
python build_pool.py --tag my-pool --cap 130 # 从自己库里挑候选池并抓音频特征
python playlist_audit.py  "歌单名"            # 元数据层体检
python playlist_flow.py   "歌单名"            # 听感层体检（BPM/调性/响度/能量/情绪）
python playlist_optimize.py 清单.json -o 曲序.json   # 按规则重排曲序
python listening_stats.py top --kind songs --year 2026   # 播放次数排行
python -m unittest discover -s tests         # 104 项测试，全部离线
```

**凭证配置见 [`SETUP.md`](SETUP.md)**；策展方法论见 [`docs/`](docs/)。
配置文件在 `%APPDATA%\am-playlist\config.json`，缓存在 `%LOCALAPPDATA%\am-playlist\`（POSIX 走
XDG）——**缓存不写进仓库**，所以克隆下来是干净的。
仓库内**不含任何令牌**，`.gitignore` 已挡住 `config.json` / `*.p8` / `.env`。

---

## License

MIT — see [LICENSE](LICENSE).

Unofficial community tooling. Not affiliated with or endorsed by Apple.
Uses your own Apple Music account for personal use; follow Apple's terms of service.

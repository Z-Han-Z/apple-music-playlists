# Apple Music MCP Curator

<!-- mcp-name: io.github.Z-Han-Z/apple-music-playlists -->

![Apple Music MCP — natural-language playlists grounded in Apple Music](https://raw.githubusercontent.com/Z-Han-Z/apple-music-playlists/main/.github/assets/social-preview.jpg)

[![Tests](https://github.com/Z-Han-Z/apple-music-playlists/actions/workflows/test.yml/badge.svg)](https://github.com/Z-Han-Z/apple-music-playlists/actions/workflows/test.yml)
[![Container](https://github.com/Z-Han-Z/apple-music-playlists/actions/workflows/container.yml/badge.svg)](https://github.com/Z-Han-Z/apple-music-playlists/actions/workflows/container.yml)
[![Release](https://img.shields.io/github/v/release/Z-Han-Z/apple-music-playlists)](https://github.com/Z-Han-Z/apple-music-playlists/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/apple-music-playlists)](https://pypi.org/project/apple-music-playlists/)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-listed-5A67D8)](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Z-Han-Z%2Fapple-music-playlists)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Glama quality score](https://glama.ai/mcp/servers/Z-Han-Z/apple-music-playlists/badges/score.svg)](https://glama.ai/mcp/servers/Z-Han-Z/apple-music-playlists)

English | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | [Français](README_FR.md)

**Deep playlist curation for Apple Music: describe a feeling, scene, era, tension, or narrative arc;
your agent turns it into a catalog-grounded selection whose versions, pacing, and transitions hold
together as a listening experience.**

Pure Python standard library — no `pip install` required to run, and **no Apple Developer Program
membership needed**. Requires Python 3.10+ and works on Windows / macOS / Linux.

The primary interface is the local `am-mcp` stdio server. The language model already running in
your MCP client interprets the brief and chooses candidates; this project searches the Apple Music
catalog, resolves exact tracks, and performs account operations. There is no bundled model, LLM
API key, artist list, or fixed theme. The CLI remains available for login, diagnostics, scripting,
audits, and advanced sequencing.

```
  understand  →  curate  →  ground  →  shape the arc  →  dry-run  →  create
```

## Why this project

- **The brief stays semantic.** The host LLM reasons directly about imagery, mood, lyrical angle,
  era, cultural context, contrast, and the role of each song. It is not reduced to a handful of
  user-supplied sliders or an opaque theme-fit number.
- **Selection and sequencing stay separate.** The model decides what belongs; measured BPM, key,
  energy, valence, and loudness can then diagnose transitions or refine order inside narrative
  blocks without overriding the musical idea.
- **Every candidate is grounded.** Catalog resolution catches missing tracks, duplicates, wrong
  artists, and suspicious live/remastered versions before the dry run and final create step.
- **Listening evidence remains evidence.** Replay history, recent plays, dates, and play counts can
  inform curation without silently becoming an algorithmic definition of the user's taste.
- **Local and private by design.** The server runs on your machine; credentials stay in the local
  app config, and there is no bundled model, telemetry service, or extra LLM API key.
- **Portable MCP stdio.** Works with Codex, Claude, Cursor, VS Code/Copilot, Gemini CLI, Windsurf,
  Cordis/DSH, Harness, and other clients that can launch a local stdio server.

---

## Quick start

**Recommended — install the MCP stdio service:**

```bash
pip install apple-music-playlists
am-playlist status
am-playlist login       # one-time Apple ID sign-in
```

Register `am-mcp` in the client. The common configuration shape is:

```json
{ "mcpServers": { "applemusic": { "command": "am-mcp",
    "env": { "PYTHONIOENCODING": "utf-8" } } } }
```

Then describe the result, not the implementation:

> Create a 25-track late-night driving playlist: atmospheric alternative R&B and electronic,
> mostly from the last ten years, no live versions, with a calm landing.

Clients with MCP Prompt support can select `create_playlist_from_description`. In every other
client, send the same request in chat: the server instructions and typed tools expose the same
status → candidate pool → catalog grounding → direct comparison → dry-run → create workflow.

**From a clone (nothing to install):**

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists

python am_playlist.py status     # auto-fetches the developer token
python am_playlist.py login      # one-time Apple ID sign-in (~6 months validity)

python am_mcp_server.py             # register this absolute script path in the MCP client
```

Installation also puts the CLI and MCP commands on your PATH:

```bash
am-playlist status      # the CLI
am-playlist login       # one-time Apple ID sign-in
am-mcp                  # the MCP stdio server
```

For development, `pip install -e .` from a clone makes edits take effect without reinstalling.

See **[SETUP.en.md](SETUP.en.md)** for the credential walkthrough (three ways to get the user token,
including a zero-dependency one).

---

## A real curation demo: *A Machine Dreams It Is Human*

This is deliberately harder than “make me a workout playlist.” The brief asks music to carry a
plot, and some of its constraints cannot be expressed as tempo or mood sliders:

> Build a 12-track, three-act story in which a machine wakes in a city, mistakes attention for
> intimacy, asks to be touched, becomes vulnerable, and sees dawn. Cross electronic music and art
> pop from the late 1970s to the present; use one track per artist, studio recordings only, and let
> the voices become progressively more human. The ending must feel quiet and earned, not merely
> low-energy.

The run below used the public US Apple Music catalog on 2026-09-23. It did not read or write a
private library.

```text
22 LLM-proposed candidates
└─ 22 catalog matches returned exact title, artist, album, date, ISRC, and version metadata
   ├─ rejected: “Open Eye Signal (Mixed)” — resolved to a 2025 DJ Mix, not the studio cut
   ├─ rejected: “Deeper Understanding (2018 Remaster)” — not the requested original recording
   └─ 12 final selections

Final create dry-run:       12/12 matched; no write performed
Audio-feature coverage:     12/12 usable (100%)
Flow cost, narrative locks: 44.14 → 41.14
```

Each title below opens the exact US catalog recording returned by the resolver, so the sequence can
be auditioned rather than taken on trust.

| Act | Grounded order | What the sequence is doing |
|---|---|---|
| **I — Boot** | [The Robots](https://music.apple.com/us/album/the-robots/726157248?i=726157329) — Kraftwerk<br>[Technopolis](https://music.apple.com/us/album/technopolis/1291843638?i=1291843640) — Yellow Magic Orchestra<br>[Kid A](https://music.apple.com/us/album/kid-a/1097862870?i=1097863120) — Radiohead | A body, then a city, then an unstable first-person voice. |
| **II — Desire** | [Oblivion](https://music.apple.com/us/album/oblivion/499874506?i=499875050) — Grimes<br>[Digital Witness](https://music.apple.com/us/album/digital-witness/1440942954?i=1440943307) — St. Vincent<br>[Is It Cold In The Water?](https://music.apple.com/us/album/is-it-cold-in-the-water/1709023350?i=1709023358) — SOPHIE<br>[Touch](https://music.apple.com/us/album/touch/617154241?i=617154364) — Daft Punk & Paul Williams<br>[All Is Full of Love](https://music.apple.com/us/album/all-is-full-of-love/20833577?i=20833608) — Björk | Public attention becomes bodily risk, transformation, a request for contact, and finally an answer. |
| **III — Re-entry** | [Cellophane](https://music.apple.com/us/album/cellophane/1458754719?i=1458754722) — FKA twigs<br>[Retrograde](https://music.apple.com/us/album/retrograde/1440871055?i=1440871816) — James Blake<br>[Long Road Home](https://music.apple.com/us/album/long-road-home/1589489446?i=1589489449) — Oneohtrix Point Never<br>[An Ending (Ascent)](https://music.apple.com/us/album/an-ending-ascent/714861155?i=714861225) — Brian Eno | The synthetic shell fails; retreat becomes return, and the story lands at dawn. |

The interesting failure happened during ordering. With only the three acts locked, the numerical
optimizer cut the measured cost from `48.28` to `14.88` — but put **Retrograde** after the dawn and
made **All Is Full of Love** answer a request that had not happened yet. That is cheaper and worse.
The host model therefore added semantic beat boundaries (`request → answer`, `return → dawn`) and
let `am_optimize_order` make only local changes inside those boundaries. Selection and story stayed
linguistic; BPM, key, energy, and valence remained supporting evidence.

<details>
<summary>Final dry-run input</summary>

```json
[
  "The Robots - Kraftwerk",
  "Technopolis - Yellow Magic Orchestra",
  "Kid A - Radiohead",
  "Oblivion - Grimes",
  "Digital Witness - St. Vincent",
  "Is It Cold In The Water? - SOPHIE",
  "Touch - Daft Punk",
  "All Is Full of Love - Björk",
  "Cellophane - FKA twigs",
  "Retrograde - James Blake",
  "Long Road Home - Oneohtrix Point Never",
  "An Ending (Ascent) - Brian Eno"
]
```

</details>

This is the normal MCP workflow: the host model interprets the brief and proposes more candidates
than it needs; `am_resolve_candidates` grounds them; the model chooses and assigns narrative roles;
`am_optimize_order` optionally checks local flow without crossing semantic boundaries; and
`am_create_playlist(dry_run=true)` verifies the exact final recordings before the write.

---

## What's in the box

| File | Purpose |
|---|---|
| `am_playlist.py` | Core: token management, catalog search, create / edit / delete playlists, track resolution |
| `am_mcp_server.py` | Primary MCP stdio service: one description-to-playlist prompt plus **13 tools** |
| `playlist_audit.py` | **Metadata audit**: length, artist concentration, genres, eras, durations, duplicates, interludes |
| `playlist_flow.py` | **Audio-feature audit**: BPM / key / loudness / energy / valence, adjacency checks, arc shape |
| `playlist_optimize.py` | Simulated-annealing **track ordering** against the measured rules |
| `listening_stats.py` | **Listening history**: recently played, and per-track/album/artist **play counts** (Apple Music Replay backend) |
| `profile_library.py` | **Descriptive sample profile**: measured BPM / energy / valence spread and sample-relative quadrants; it does not define the user's taste |
| `am_library.py` | **Your library**: paged export of every catalog-backed song you own, enriched with ISRC / year / genre |
| `build_pool.py` | **Listening-evidence pool**: merge recent plays with multiple Replay years, retaining dates and play counts for the LLM to interpret |

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

The standard prompt `create_playlist_from_description` asks for a natural-language brief and
optional name, track count, and response language. Curation stays in the host model; the tools are
the grounded Apple Music execution layer:

`am_status` · `am_search_songs` · `am_resolve_candidates` · `am_list_playlists` · `am_show_playlist` ·
`am_create_playlist` · `am_add_tracks` · `am_delete_playlist` ·
`am_audit_playlist` · `am_analyze_flow` · `am_optimize_order` ·
`am_recently_played` · `am_top_played`

`am_resolve_candidates` grounds a generous LLM-proposed pool in real catalog metadata, flags
duplicates and suspicious versions, and deliberately does not score theme fit. The host model
compares candidates directly with the user's words and explains their playlist roles.
`am_analyze_flow` diagnoses transitions; `am_optimize_order` can optionally refine ordering inside
already chosen narrative blocks. It never decides which songs belong in the playlist.

Mount it in a Cordis agent preset with the template in [`preset/`](preset/), or wire it into
any other MCP client with:

```json
{ "mcpServers": { "applemusic": {
    "command": "python", "args": ["/abs/path/am_mcp_server.py"] } } }
```

Complete tested examples for Codex, Claude, Cursor, VS Code/Copilot, Gemini CLI, Windsurf,
Docker, Cordis/DSH, and Harness are in **[docs/client-setup.md](docs/client-setup.md)**.

Build the non-root local container with:

```bash
docker build -t apple-music-playlists:1.4.0 .
```

The client must run it attached with `docker run --rm -i`; mount only the app config directory and
a writable cache as shown in the client guide. Config stays writable so token refresh can persist.
Never bake Apple credentials into the image.

---

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite is entirely **offline** — no network, no credentials. Two kinds:

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

**Coverage is reported, never silently dropped.** Every consumer prints a funnel saying *why* each
track could not be measured:

```
Audio-feature coverage: 1,395/1,581 usable (88%)
  ·  80 tracks have no ISRC — the feature chain cannot start, so changing sources will not help
  · 106 tracks are not in the current source — switch sources or analyse the audio locally
```

That distinction is the point. **No ISRC** means the chain cannot start at all — a different
feature source will not help. **Not in the source** means the ISRC is fine and switching sources
(or analysing the audio locally) would fix it. Collapsing both into "missing features" discards the
only information that tells you what to do next.

It matters more than it looks: `tempo` / `key` / `energy` / `valence` are the only things the
adjacency rules and the arc can act on, so **coverage is the ceiling on how good an ordering can
be**. At 60% coverage, four positions in ten were never evaluated — while the cost number still
looks excellent. The optimizer therefore prints coverage above its cost lines, and warns below 90%.

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

**Global arc** — you choose the target shape:

```bash
python playlist_optimize.py stack.json --arc cinderella
python playlist_optimize.py --list-shapes
```

| Axis | Target |
|---|---|
| `valence`, `energy`, `loudness` | the chosen narrative archetype |
| `tempo` | inverted U — fast in the middle |

Six shapes: `rags-to-riches`, `tragedy`, `man-in-a-hole` (default), `icarus`, `cinderella`,
`oedipus`. The target curve and the shape the audit *classifies* come from the same table in
`playlist_core.ARCHETYPES`, so "what shape is this" and "what shape am I aiming for" cannot drift
apart.

Tempo deliberately does **not** follow the chosen shape. The archetypes describe an emotional
trajectory (valence / arousal); "put the fast ones in the middle" is a sequencing convention.
Making tempo follow Cinderella too would conflate two independent principles.

Measuring this on a real arc playlist is what justified wiring it up: under `man-in-a-hole` — the
shape the optimizer used to hardcode — that playlist's opening 30 tracks score an arc cost of
**2.95**, the *worst* of the six. The same tracks score **1.19** under `cinderella`. The tool had
been aiming at the one shape that fit least.

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
| [`SETUP.en.md`](SETUP.en.md) | Credentials: what tokens exist, how to get each one, security notes, troubleshooting |
| [`docs/client-setup.md`](docs/client-setup.md) | Client-specific MCP, Docker, Cordis/DSH, generic harness, and Harness Platform setup |
| [`docs/publishing.md`](docs/publishing.md) | Maintainer-only PyPI and official MCP Registry publishing checklist |
| [`docs/apple-music-api-notes.md`](docs/apple-music-api-notes.md) | Token model, endpoint contracts, measured API behaviour, eval of 7 automation approaches |
| [`docs/how-to-build-a-good-playlist.md`](docs/how-to-build-a-good-playlist.md) | Curation methodology: adjacency physics, arc data, six narrative shapes, the ISO principle |
| [`docs/playlist-curation-survey.md`](docs/playlist-curation-survey.md) | Survey of published curation guidance (platform rules, DJ methods, academic findings) |
| [`docs/evaluation-signals.md`](docs/evaluation-signals.md) | LLM-native curation: direct candidate comparison, catalog grounding, readable constraints, and why scalar theme scores stay out of the critical path |
| [`docs/algorithm-review.md`](docs/algorithm-review.md) | Review boundary for early heuristics: which decisions belong to the LLM and which deterministic algorithms should retain |
| [`docs/platform-adapters.md`](docs/platform-adapters.md) | The platform-adapter boundary: what is platform-neutral, what an adapter must provide, and what breaks on a service that exposes no ISRC |
| [`skill/`](skill/) | Agent skill: workflow + the accumulated gotcha list |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history, including behaviour changes between versions |
| [`preset/`](preset/) | Cordis agent preset template that mounts the MCP server |

---

For the complete Simplified Chinese guide, see **[README_ZH_CN.md](README_ZH_CN.md)**.

---

## Community

- [Contributing](CONTRIBUTING.md) — development workflow, architecture boundaries, and review expectations
- [Support](SUPPORT.md) — where to ask questions, report bugs, or propose features
- [Code of Conduct](CODE_OF_CONDUCT.md) — participation standards and private reporting route
- [Security policy](SECURITY.md) — supported versions and confidential vulnerability reporting

---

## License

MIT — see [LICENSE](LICENSE).

Unofficial community tooling. Not affiliated with or endorsed by Apple.
Uses your own Apple Music account for personal use; follow Apple's terms of service.

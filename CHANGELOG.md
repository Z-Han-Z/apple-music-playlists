# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Direction tags**, so a user can steer a finished curation stylistically instead of restating
  the brief. After curating, the host model authors about five tags across two axes: `sonic` for
  the music's own character and `context` for why these tracks are here (recent, high rotation,
  already in the library, drawn from a reference). The new read-only, offline `am_tag_directions`
  tool validates that set, applies replies such as `more funk` or `less disco`, and returns both a
  display line and a direction note for the next round. `playlist_tags.py` holds the contract;
  `docs/playlist-tag-directions.md` documents it.

  Emphasis is **qualitative, not numeric**: three levels (`soften` / `neutral` / `boost`), with the
  user's own wording kept as a revision record. An earlier draft used a `0.0–2.0` weight and a fixed
  `±0.5` step; review rejected it correctly, because decimals dress an aesthetic judgement up as
  precision and conflict with the project's rule that the model reads the brief directly instead of
  compressing theme fit into parametric scores. A `weight` field is now rejected with that reason
  spelled out. An adjustment naming a tag the direction does not contain is reported as `unknown`
  along with the labels that do exist, and unparsable input is reported rather than ignored.

  The tags are a **steering surface, not the brief, and never a selection criterion**.
  `docs/evaluation-signals.md` explains why collapsing requirements into tags or weights loses
  scoped negation, reference semantics, and narrative beats; this feature does not reopen that. The
  original request and the curation contract stay authoritative, and `direction_note()` states both
  boundaries inside its own output rather than relying on external docs.

  A `context` tag describes **what the user has been listening to**, so it now carries an
  `evidence` field naming the call that backs it. A context tag without one is accepted but always
  reported, and is marked "no evidence" in the display line and the direction note: a listener has
  the right to tell a grounded claim from a guess. Two traps are called out explicitly in the
  contract, because both turn inference into a false fact about the user:
  `am_recently_played(kind=added)` means recently **added**, not recently **played**; and
  "concentrated listening" is not a field any endpoint returns — it can only be derived from
  `firstPlayed` / `lastPlayed` together with `playCount`.
- `am_resolve_candidates` now returns each grounded recording's Apple Music URL so users can
  audition and verify the exact catalog version before a playlist is written.
- A root `llms.txt` gives agents and directory crawlers a concise, spec-shaped map of the project's
  curation boundary, setup, research, and implementation documentation.
- A reusable multilingual curation evaluation set provides five difficult briefs with auditable
  constraints and blind-listening questions, without freezing any model's selections as truth.
- The evaluation guide now defines a reproducible one-shot baseline, result template, blind-listening
  protocol, interpretation boundaries, and privacy-safe sharing rules.

### Changed

- Package discovery metadata now describes the project as semantic curation and narrative
  playlist sequencing instead of a generic playlist generator.
- All localized READMEs and both client guides now document the official MCP Registry's `uvx`
  launch path for running the PyPI package without a permanent install.

## [1.4.0] - 2026-09-23

### Added

- Published the project as the zero-runtime-dependency `apple-music-playlists` package on PyPI and
  made that package the default installation path across all nine localized READMEs and client
  setup guides.
- Added a reviewed `server.json` plus a manual, approval-gated GitHub OIDC workflow for publishing
  matching releases to the official MCP Registry. The publisher binary is version- and checksum-
  pinned, and registry metadata is never published before its PyPI package exists.
- Added complete community-health files, issue forms, a pull-request template, a shared social
  preview, Glama discovery metadata, and richer MCP tool titles/descriptions.
- Added a fully executed README curation demo built from a difficult three-act brief, including
  candidate/version rejection, 100% audio-feature coverage, narrative locks, and the final 12/12
  catalog dry run.

### Changed

- Reframed the project around deep playlist curation: direct language understanding, catalog-
  grounded song and version selection, narrative structure, and flow-aware sequencing. Generic
  platform connection is supporting infrastructure rather than the product claim.
- Refactored `build_pool.py` from an aesthetic candidate selector into a cross-period listening-
  evidence collector. It now merges recent plays with multiple Replay years and preserves source,
  rank, play-count, and first/last-played facts for direct interpretation by the host LLM. The
  favourite-artist expansion, equal-step "variety filler", and implicit theme decisions are gone.
- Reworded `profile_library.py` as a descriptive report: its high/low quadrants are relative to the
  current sample medians and must not be presented as a definition of the user's taste.
- Added an algorithm-review boundary that separates semantic curation (LLM responsibility) from
  evidence normalization, catalog resolution, descriptive statistics, and optional physical
  sequencing (deterministic service responsibilities).

### Fixed

- Version grounding now marks the catalog suffix `(Mixed)` and unknown, unrequested trailing title
  qualifiers as suspicious. The README demo found real searches that silently preferred a track
  from a 2025 DJ Mix, then a 2026 alternate called `(under the fabric)`, over the requested studio
  recording; the resolver now exposes these in `version_markers` for the host model to review.
- `am_playlist.best_song_match` no longer falls back to the first search result when nothing
  matches the query. A `Title - Artist` query used to resolve to an unrelated track whenever the
  requested artist did not have that recording — one real case returned a karaoke version
  credited to a different artist, and another returned the original artist's recording instead of
  the band's cover. Candidates are now filtered on title and artist before scoring, an empty
  `artistName` never passes (an empty string is a substring of everything), and a query with no
  surviving candidate is reported as missed. `am_resolve_candidates` already surfaces that as
  `unmatched`, and the CLI reports it before creating or writing anything. Filtering first also
  fixes picking the wrong artist when the correct one is present but ranked lower by relevance.
- Matching preserves Unicode letters across Korean, Japanese, Chinese, and other scripts, folds
   Latin accents for comparison, and accepts spaced hyphen, en-dash, or em-dash delimiters.

## [1.3.0] - 2026-09-22

### Added

- A standard MCP prompt, `create_playlist_from_description`, that turns a natural-language brief
  into an explicit status → candidate pool → catalog grounding → direct comparison →
  dry-run → create workflow.
- `am_optimize_order` — a **read-only** MCP tool that computes a better track order (simulated
  annealing over the four adjacency rules and a chosen narrative arc) and writes nothing.

  The gap it closes: `am_analyze_flow` could tell an agent *what* was wrong with a playlist's
  sequence — two adjacent slow pairs, an Icarus shape — but nothing could tell it how to fix it.
  The agent had to hand-order from raw BPM numbers, which the curation research says loses to the
  optimizer. Accepts a free list, explicit blocks (movement order preserved, reordering only
  within), or an existing playlist, and returns a list ready to hand to `am_create_playlist`.
- `am_library` now keeps `hasLyrics` from the catalog response it was already fetching, and the
  library report shows lyrics coverage next to ISRC coverage. This costs no extra request; the
  field was already arriving and being discarded. A false value is treated as missing evidence,
  never as proof that a track is instrumental.
- `am_resolve_candidates` — a read-only MCP grounding tool for LLM-generated candidate pools. It
  preserves input order and returns real Apple Music metadata, catalog IDs, explicit version
  markers, duplicate recordings, and artist-concentration warnings without assigning theme-fit
  scores or making aesthetic decisions for the model.

### Changed

- Repositioned MCP stdio as the primary product path: the host client's LLM curates from the
  user's description while this server validates candidates against Apple Music and performs the
  account operations. No separate LLM provider or API key is embedded in the server.
- Kept the CLI as the authentication, diagnostics, scripting, and advanced-maintenance interface.
- Replaced the experimental LLM-number-to-optimizer bridge with an LLM-native curation workflow:
  generate a generous pool, ground it in Apple Music, compare candidates in natural language,
  assign narrative roles, and use deterministic sequencing only as an optional final pass.

### Fixed

- MCP now rejects lone Unicode surrogate characters as invalid arguments before a tool handler or
  Apple Music write runs. Valid UTF-8 Chinese and accented text continue to round-trip normally.

## [1.2.0] - 2026-09-22

This is the first stable (non-prerelease) release of the installable, agent-ready toolkit.

### Added

- Complete regional README entry points for English, Simplified Chinese, Traditional Chinese,
  Japanese, Korean, Spanish, Brazilian Portuguese, German, and French. Every localized README
  covers installation, authentication, CLI use, MCP, containers, safety, and verification.
- English credential documentation alongside the existing Chinese guide.
- Tested client setup guides for Codex, Claude, Cursor, VS Code/GitHub Copilot, Gemini CLI,
  Windsurf, generic MCP harnesses, Cordis/DSH, and Harness Platform.
- A non-root, zero-runtime-dependency Docker image definition, Compose configuration, strict
  `.dockerignore`, and a CI container handshake smoke test.
- Bilingual MCP server instructions and tool descriptions, plus read-only, destructive,
  idempotent, and open-world annotations for approval-aware clients.

### Changed

- MCP initialization now negotiates known handshake versions (`2024-11-05` through
  `2025-11-25`) and falls back to the server's implemented version for unknown proposals instead
  of echoing an unsupported value.
- CI now installs the package and checks the generated console scripts before running the offline
  regression suite.
- Distribution and container examples are pinned to the `v1.2.0` stable tag.

### Fixed

- Invalid MCP request shapes and missing required tool arguments now return standard JSON-RPC
  errors instead of leaking handler exceptions.
- Malformed JSON on stdio now returns a JSON-RPC parse error rather than disappearing silently.
- Stale MCP version and tool-count comments in the API and Cordis documentation.

### Compatibility note

- Local stdio clients and containerized stdio clients are supported directly. Harness CI/CD can
  run the CLI or container. Harness AI Worker Agent connectors require an authenticated network
  URL; the project deliberately does not claim that a local stdio process is a remote connector
  or ship an unauthenticated HTTP bridge.

## [1.1.0] - 2026-09-22

Everything below is relative to `v1.0.0` (commit `709123c`), the state before the hardening
pass. This is the version whose tree contains this changelog.

### Added

- **`am_playlist.py library`** — export your whole library (paged `/me/library/songs`,
  enriched with ISRC / year / genre). This was the missing link that made `build_pool.py`
  unusable for anyone but its author.
- **`--arc <shape>` and `--list-shapes`** on `playlist_optimize.py`. The six narrative
  shapes are now real targets rather than labels the audit merely prints.
- **`playlist_core.py`** — a platform-neutral core: Camelot, BPM folding, the four
  adjacency rules, the six narrative shapes, and the feature-coverage funnel. It imports
  nothing from this project and nothing third-party; tests enforce both.
- **Feature-coverage reporting.** Every consumer prints a funnel saying *why* each track
  could not be measured, and warns when coverage falls below 90%.
- **`am_meta.py`** — the single `catalog_meta` implementation (previously written four times).
- **`am_paths.py`** — platform-neutral paths and version.
- **An offline test suite** — no network, no credentials required.
- **`docs/platform-adapters.md`** — the boundary between the platform-neutral core and a
  platform adapter, what an adapter must provide, and what breaks on a service that
  exposes no ISRC.
- **Paginated list helpers** — `paged_data()`, `list_playlists()`, `playlist_tracks()`.
  They follow Apple's `next` cursor with a repeat-guard, so lists are read in full.
- **`created_playlist_from_response()`** — after creating a playlist, poll for it to appear
  instead of assuming the response carries an id, which covers iCloud propagation lag.
- **Continuous integration** — the offline suite runs on Linux / macOS / Windows across
  Python 3.10 and 3.13.
- **`AGENTS.md`** — repository conventions for automated contributors, including the
  architectural invariants that keep the core platform-neutral.
- **`pyproject.toml`** — the project is installable, and the version is read from
  `am_paths.VERSION` rather than written twice. Two console scripts: `am-playlist` and
  `am-mcp`. Runtime dependencies stay empty, so the zero-install path still works.
  Installation is what makes MCP registration one line: the modules land somewhere Python
  can import them, so a client no longer needs an absolute path to the server script.

### Changed

- **Caches moved out of the repository.** `refs/` used to be the cache directory; it is now
  a read-only fallback. New files go to the per-user directory
  (`%LOCALAPPDATA%\am-playlist`, or `$XDG_CACHE_HOME`). Existing caches keep working, so no
  action is needed.
- **The optimizer's default arc target changed** — see *Behaviour changes* below.
- `playlist_optimize.py` no longer imports `playlist_flow.py`, so the algorithm layer no
  longer reaches platform code transitively.
- `--storefront` no longer carries a literal default, so the region remembered in config
  actually applies.
- `profile_library.py` writes its profile cache to the user directory.
- The MCP server and both audits now go through the shared list helpers instead of issuing
  their own single-page `limit=100` requests.

### Fixed

- **Four storefront bugs, all of which failed silently.** Apple returns an empty `data`
  array for a wrong region rather than raising, so each of these degraded quietly:
  - `playlist_audit.catalog_meta` defaulted to a hardcoded region, so any account outside
    it got no catalog metadata and the audit fell back to bare statistics.
  - `playlist_flow` inlined a hardcoded catalog path — same failure.
  - `cmd_search` defaulted `--storefront` to `"us"`; because an explicit argument wins in
    `resolve_storefront`, the region from config never applied. The MCP tool *did* resolve
    it, so the CLI and MCP disagreed on the same query.
- **`build_pool.py` could not run for anyone but its author.** It read a gitignored file
  that nothing in the repository generated, and its whole body sat at module level, so
  importing it ran the pipeline.
- **The four adjacency rules were implemented twice, with different definitions.** The
  audit called a track "slow" below the tempo's 25th percentile while the optimizer used a
  fixed 100 BPM, and the audit never checked the BPM-jump rule the optimizer penalised — a
  tool diagnosing against one standard and repairing against another. Both now call
  `playlist_core.check_pair()`.
- **Version-suffix matching was substring-based**, so `Alive` / `Olive` / `Deliver` were
  penalised as live takes. Latin suffixes now match as whole words, CJK still matches as a
  substring, and `Remix` is listed explicitly so it is not lost.
- **`--help` did not print usage** in two entry points (`playlist_audit.py` took it as a
  playlist name, `playlist_optimize.py` as a file path). `SystemExit(__doc__)` was also
  wrong on its own terms: it exits 1 and writes the docstring to stderr.
- **Inconsistent UTF-8 stdout.** Some entry points forced it and some did not; on Windows
  that produced mojibake, and printing the warning glyph without it raised
  `UnicodeEncodeError` rather than merely looking wrong. One implementation now, called by
  all seven entry points.
- Unreachable code after `return "us"` in `resolve_storefront`.
- Four documentation pointers that had survived a file rename, and a doc that contradicted
  itself about whether missing feature data was still silently dropped.
- **Playlists longer than 100 tracks were silently truncated.** `playlist_audit` and
  `playlist_flow` each read a single page. This also made the coverage denominator wrong for
  long playlists — the funnel would have reported a confident 100% while seeing only the
  first page.
- **The length verdict in `playlist_audit` was inverted.** It passed `cond_ok = n <= 50`, so
  a 10-track playlist was reported as "✅ compliant with Apple's 15–50" rather than
  "❌ fewer than 15". Empty playlists now stop early instead of analysing nothing.
- Stale MCP tool counts in `docs/apple-music-api-notes.md` and `preset/README.md` (they said
  6 and 9; the server exposes 11), the protocol version in the docs' handshake example, and
  the clone URL placeholder.

### Behaviour changes

- **The optimizer's default target arc is now the published `man-in-a-hole` curve** instead
  of an ad-hoc parametric U with its valley pinned at 60%. For the same input the resulting
  order can differ. This is a fix — the documentation names a curve, so the optimizer should
  aim at that curve — but if you compare orders across the change, that is why.
- **A uniformly slow playlist now flags every adjacent pair** under `two_slow`. The previous
  data-driven threshold (25th percentile) hid this. It is real rather than a sequencing
  failure, and the report says so.

### Notes

- `config.json` is unchanged (`%APPDATA%\am-playlist`). Tokens are untouched, and no
  re-login is needed.
- A stale `refs/library-songs.json` from the earlier schema (no `isrc` field) is now
  rejected by a schema check and refetched. It is safe to delete.

## [1.0.0] - 2026-09-22

The first state the project itself called `1.0.0` — the MCP server reported that version —
and the first state that was general-purpose rather than personal. Tagged retrospectively.

- Create, edit and delete Apple Music playlists from the CLI or from an MCP server.
- Metadata audit, audio-feature audit, and simulated-annealing track ordering.
- Listening history: recently played, and per-track / album / artist play counts.
- Taste profile derived from play counts, plus a candidate-pool builder.
- Library-specific personal scripts removed, so the repository is a general-purpose tool.

## [0.3.0] - 2026-09-22

- Added `profile_library.py` — a taste profile built from play counts (BPM / energy /
  valence spread, mood quadrants).
- Added `build_pool.py` — build a candidate pool out of your own library.
- Fixed: arc classification split the curve into 3 segments, which mislabelled a
  rise-fall-rise playlist as `Icarus`. It now uses 5 segments, and all six narrative
  archetypes classify as themselves.
- Fixed: `status` now actually answers whether the tokens have expired, instead of only
  reporting that they exist.

## [0.2.0] - 2026-09-21

- Added `listening_stats.py` — recently played, and per-track / album / artist play counts,
  read from the Apple Music Replay backend (the only endpoint that exposes play counts).
- Added the corresponding MCP tools.
- Fixed: the storefront is resolved from config rather than defaulting to a hardcoded region.

## [0.1.0] - 2026-09-21

First working toolkit.

- `am_playlist.py` — token handling, catalog search, playlist create / edit / delete, and
  track resolution.
- `am_mcp_server.py` — an MCP stdio server over the same capabilities.
- `playlist_audit.py` (metadata), `playlist_flow.py` (audio features), and
  `playlist_optimize.py` (simulated-annealing ordering).
- `docs/` — the curation research the sequencing rules are derived from.
- `skill/` and `preset/` — an agent skill, and a Cordis preset that mounts the MCP server.

[Unreleased]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Z-Han-Z/apple-music-playlists/releases/tag/v0.1.0

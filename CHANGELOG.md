# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-09-22

First tagged release. Everything below is relative to the untagged `1.0.0` state
(commit `709123c`).

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

## [1.0.0] - 2026-09-21

Initial state, retroactively tagged. There was no `VERSION` constant at the time and the
MCP server reported `1.0.0`.

- Create, edit and delete Apple Music playlists from the CLI or from an MCP server
  (11 tools).
- Metadata audit, audio-feature audit, and simulated-annealing track ordering.
- Listening history: recently played, and per-track / album / artist play counts.
- Taste profile derived from play counts.

[Unreleased]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Z-Han-Z/apple-music-playlists/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Z-Han-Z/apple-music-playlists/releases/tag/v1.0.0

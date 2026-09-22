# Repository guidance for Codex agents

## Scope

This repository is a standard-library-first Apple Music playlist toolkit. Keep the CLI, MCP
server, analysis modules, documentation, and agent skill consistent with one another.

## Required checks

- Run `python -m unittest discover -s tests -v` after code changes.
- Run `git diff --check` before handing work back.
- Add an offline regression test for every fixed bug. Tests must not require Apple credentials,
  network access, or a user's music library.

## Architectural constraints

- Keep `playlist_core.py` platform-neutral: standard library only and no Apple-specific imports.
- Keep catalog metadata fetching centralized in `am_meta.catalog_meta`.
- Keep sequencing-rule definitions centralized in `playlist_core.check_pair`.
- Resolve the storefront through `am_playlist.resolve_storefront`; never hardcode a region.
- Follow Apple list pagination everywhere. A single `limit=100` request is not a complete list.
- Cache and generated artifacts belong in the per-user cache directory from `am_paths`, not in
  the repository.

## Safety and privacy

- Never commit tokens, cookies, `.p8` keys, local cache data, listening history, personal song
  selections, or generated playlists.
- Treat playlist deletion and live library writes as destructive. Unit tests must mock them.
- Do not run authenticated Apple Music smoke tests unless the user explicitly authorizes live
  account access for that task.
- Keep the project dependency-free at runtime. Optional login and developer-token features may
  continue to use their documented optional dependencies.

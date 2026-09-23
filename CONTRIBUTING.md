# Contributing

Thanks for helping improve the Apple Music MCP Playlist Toolkit. Bug reports, client setup fixes,
storefront-specific findings, documentation translations, and focused code changes are welcome.

## Before opening a pull request

1. Create a focused branch from `main`.
2. Keep the runtime standard-library-only. Optional login helpers may use their documented optional
   dependencies, but the MCP server and core CLI must continue to run without third-party packages.
3. Add an offline regression test for every bug fix. Tests must not require Apple credentials,
   network access, or a real music library.
4. Keep CLI, MCP schemas, documentation, and `skill/SKILL.md` consistent when behavior changes.
5. Run:

   ```bash
   python -m unittest discover -s tests -v
   git diff --check
   ```

## Architecture boundaries

- `playlist_core.py` stays platform-neutral and standard-library-only.
- Catalog metadata fetching stays centralized in `am_meta.catalog_meta`.
- Sequencing rules stay centralized in `playlist_core.check_pair`.
- Storefronts must be resolved through `am_playlist.resolve_storefront`; never hardcode a region.
- Generated data and caches belong in the per-user directories provided by `am_paths`, never in
  the repository.
- Semantic curation belongs to the host LLM. Deterministic code may collect evidence, resolve
  catalog identities, report measurements, and assist physical ordering, but must not hide
  aesthetic decisions inside unexplained scores.

## Pull request scope

Prefer one concern per pull request. Explain the user-visible problem, the chosen boundary, and the
offline evidence that proves the change. Do not include tokens, cookies, `.p8` keys, listening
history, personal song selections, cache files, or generated playlists.

For security issues, follow [SECURITY.md](SECURITY.md) instead of filing a public bug report.

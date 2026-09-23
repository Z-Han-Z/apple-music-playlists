# Support

This is a community-maintained project with best-effort support and no response-time guarantee.
The fastest route depends on what you need.

## Setup or usage question

1. Check the [quick start](README.md#quick-start), [credential setup](SETUP.en.md), and
   [MCP client guide](docs/client-setup.md).
2. Search existing [issues](https://github.com/Z-Han-Z/apple-music-playlists/issues) for the exact
   error or client name.
3. If the answer is still unclear, open a
   [question](https://github.com/Z-Han-Z/apple-music-playlists/issues/new?template=question.yml).

Include the operating system, Python version, client or container environment, project version,
and the redacted command or MCP configuration. Say what you expected and what happened.

## Reproducible bug

Use the [bug report form](https://github.com/Z-Han-Z/apple-music-playlists/issues/new?template=bug_report.yml).
A small offline reproduction or synthetic JSON-RPC example is especially useful.

## Feature idea

Use the [feature request form](https://github.com/Z-Han-Z/apple-music-playlists/issues/new?template=feature_request.yml).
Describe the user outcome and whether the responsibility belongs to the host LLM or deterministic
service code.

## Security or private conduct report

- Report a vulnerability through [GitHub private reporting](https://github.com/Z-Han-Z/apple-music-playlists/security/advisories/new)
  and follow [SECURITY.md](SECURITY.md).
- Report harassment or another conduct violation through the same private channel, prefixing the
  title with `Code of Conduct:`; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Never post Apple Music tokens, cookies, `.p8` private keys, account identifiers, listening history,
private playlists, or another person's personal information in an issue. Use redacted or synthetic
data instead.

## Project boundaries

Support covers this repository's MCP stdio server, CLI, container configuration, catalog matching,
playlist workflows, audits, and sequencing tools. Apple Music account billing, Apple platform
outages, unsupported client internals, and third-party audio-feature availability are outside the
project's control, although reproducible integration problems are still useful to document.

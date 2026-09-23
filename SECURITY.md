# Security policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting flow for this repository:

<https://github.com/Z-Han-Z/apple-music-playlists/security/advisories/new>

Do not include Apple Music tokens, cookies, `.p8` private keys, account identifiers, listening
history, or other personal data in a public issue. A useful report includes the affected version,
the relevant command or MCP tool, the expected security boundary, and a minimal reproduction using
redacted or synthetic data.

## Credential boundary

The project stores its user token in the per-user application config documented in `SETUP.en.md`
and `SETUP.md`. Credentials and generated listening data must never be committed, embedded in a
container image, pasted into an issue, or sent to a third-party directory submission form.

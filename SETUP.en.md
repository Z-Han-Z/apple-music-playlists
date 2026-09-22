# Credential setup

[中文](SETUP.md) | [English](SETUP.en.md)

The toolkit uses two tokens. Both stay in the current user's config directory; they are never
packaged, committed, or uploaded by this project.

| Token | Purpose | Source | Typical lifetime | Automation |
|---|---|---|---|---|
| Developer token (ES256 JWT) | Identifies a MusicKit client on every request | Public Apple Music web token, or your own MusicKit `.p8` key | Web token about 70 days; self-signed at most 6 months | Fully automatic by default |
| Music user token | Authorizes reads and writes to your library | `media-user-token` after signing in at music.apple.com | About 6 months | One interactive sign-in |

Config path:

```text
Windows  %APPDATA%\am-playlist\config.json
macOS    ~/.config/am-playlist/config.json
Linux    $XDG_CONFIG_HOME/am-playlist/config.json (normally ~/.config/...)
```

## 1. Developer token

Run any command, such as `am-playlist status`. The toolkit fetches the public token embedded in
Apple's web player, validates the JWT issuer and expiry, caches it, and refreshes it before expiry.
No Apple Developer Program membership is needed for this default path.

```bash
am-playlist status
```

## 2. Music user token

Apple requires an Apple ID sign-in and two-factor authentication before a client can modify a
library. Choose one method; after success, normal use is automatic until the token expires.

### A. Windows Apple Music app cookies

Sign in to the Microsoft Store Apple Music app, then:

```powershell
pip install "apple-music-playlists[windows-cookies] @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist login
```

### B. Playwright browser sign-in

```bash
pip install "apple-music-playlists[browser-login] @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist login
```

The tool opens the installed Microsoft Edge browser. Complete Apple ID and 2FA sign-in; the
profile is retained for future renewals.

### C. Manual cookie copy (zero dependencies)

1. Sign in at <https://music.apple.com>.
2. Open browser developer tools → **Application** → **Cookies** → `https://music.apple.com`.
3. Copy the value of `media-user-token`.
4. Run `am-playlist login --from-clipboard`, or pass it to `--token`.

The parser accepts a raw value, a quoted value, `media-user-token=...`, or a whole cookie row.
Do not copy the `devToken` URL parameter; that is the developer token, not your user token.

Verify:

```bash
am-playlist status
```

The result should report a saved music-user-token and an online storefront check.

## Optional: your own MusicKit key

The public web developer token uses a shared quota. Very large imports can receive HTTP 429. For
batch workloads, Apple Developer Program members can create a MusicKit key, download its one-time
`.p8` private key, and run:

```bash
pip install cryptography
am-playlist devtoken --key-path ~/AuthKey_XXXX.p8 --key-id ABC123DEFG --team-id DEF123GHIJ
```

Never commit or share the `.p8` file.

## Containers, WSL, and remote agents

Authentication belongs to the OS user and environment that owns the config file. WSL, SSH hosts,
containers, and sandboxed agents do not inherit the host config automatically. Complete login on
the host, then copy or mount only the `am-playlist` config directory into the execution environment.
Keep it writable so automatic developer-token refresh can be persisted. Container examples are in
[docs/client-setup.md](docs/client-setup.md).

Do not put a token directly in a client JSON file, container image, Dockerfile, Compose file, CI
log, or repository secret that is exposed to pull requests.

## Security

- `music-user-token` is a library read/write credential. Treat it as a password.
- The config is plaintext with user-only file permissions; any process running as the same user
  may be able to read it.
- Run `am-playlist logout` to remove the user token when finished.
- If a token reaches Git, revoke it by changing/revoking the Apple ID session, remove it from the
  complete Git history, and sign in again. Deleting it from only the latest commit is insufficient.

## Troubleshooting

| Symptom | Cause and action |
|---|---|
| HTTP 403 authentication required | User token is missing or expired; run `am-playlist login` again. |
| HTTP 401 | Refresh the developer token; playlist DELETE must use the amp-api host. |
| HTTP 429 | Shared quota is rate-limited; stop retrying and wait, or use your own MusicKit key. |
| Playlist write returns 403 | Apple only lets the creating API client modify that playlist. |
| MCP client reports not logged in | It runs as another user/environment; fix or mount its config path. |
| Developer-token fetch fails | Apple's web bundle layout may have changed; open an issue with the error and version. |

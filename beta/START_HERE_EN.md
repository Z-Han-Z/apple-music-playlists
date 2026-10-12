# NetEase MCP Curator 1.6.0 — Windows public-preview distribution

This is an **MCP server, not an application**. All setup, login and curation guidance belongs
to your AI host's conversation. No standalone wizard, fixed menu, player or taste questionnaire.
The browser is used only for local account authorization, never as a curation dashboard.

Requires Windows 10/11 x64, an existing normal Python 3.10+ installation and a local-stdio MCP
host. Python is not bundled; Node does not need to be installed. No additional LLM/key or official
NetEase endorsement is implied.

## Connect once; then converse

Give this guide to an agent with local tools and ask it to install/connect the supplied MCP
without overwriting existing servers. It may run install.cmd; without local execution tools,
double-click install.cmd yourself. This installs the wheel offline into a private user environment,
checks MCP, and outputs credential-free configuration. No administrator, global packages or PATH edits.

Merge mcp-config.json into the host's settings and reconnect. Keep NETEASE_LOGIN_BUNDLE pointing
to the extracted package; it is the private helper location, not a credential. configure.cmd is
a fallback configuration viewer, not a wizard. The server cannot configure a host that has not
connected to it yet. Missing Python requires a normal official install/launcher, not an embeddable ZIP.

Say **“Help me start using this NetEase MCP.”** The host should call nc_setup for offline facts and
nc_status for login verification, explain missing prerequisites in your language and ask permission
before nc_login(action=start, confirm=true). Initialization does not access accounts/start login.

The QR opens only in your local browser; scan and confirm in the official NetEase app. The host polls
nc_login(action=status), then nc_status. A displayed QR or saved session is not proof of valid login.
The helper closes its temporary gateway and verifies direct login. You can say “Cancel login.”
Host disconnection signals cancellation too; it does not revoke an already-approved server session.

Never send passwords, cookies, MUSIC_U, QR images/keys/authorization URLs or session files to chat.
No such fields exist in the tool arguments/results. Network verification failure is not evidence
of an expired session. Do not repeatedly start QR; a restart needs a fresh user decision.
An optional getting_started MCP Prompt is available, but ordinary chat is the primary interface.

## Curate naturally

Describe your playlist directly. The host LLM understands the brief, selects candidates and narrative
order; tools ground recordings and facts. Do not first fill numeric weights or a questionnaire.
Use collections/history only when requested/relevant. Without login, public discovery and
non-personalized preview remain possible; private history/collections and writes do not.

Default mode is readonly. When a real playlist write is requested, explain host opt-in
NETEASE_ENABLE_WRITES=1 and reconnection (a separate mcp-config-write-opt-in.json is included).
Every write still needs preview, explicit approval and confirm=true, dry_run=false.
Inspect partial/unknown outcomes officially before retrying.

## Local authorization implementation and fallback

The complete ZIP includes private Node 24.19.0, integrity-locked API Enhanced 4.41.1 dependencies,
upstream licenses and qr-runtime/THIRD_PARTY.json. Only approved login starts the helper.
Its ephemeral gateway binds 127.0.0.1 and exposes login/account verification only; no public proxy,
audio unblocking, downloads or persistent gateway. Temporary QR/upstream files are isolated/cleaned.

Standalone wheel/source nc-login qr still needs a user-managed loopback gateway. LIGHT_PACKAGE.txt
marks an advanced import-only package. Automatic helper management belongs to the complete Windows ZIP.
Fallback login-import.cmd / nc-login import --save hides a local paste of your own MUSIC_U from
official browser login: developer tools → Application/Storage → Cookies → music.163.com → Value.
Never hand the credential to an agent. Clear sensitive clipboard history/sync after import.

## Troubleshooting and cleanup

Explain errors conversationally: missing tools require host config/reconnection; missing/damaged helper
requires a trusted complete ZIP/reinstallation, not disabled security; network failures require checking
connectivity before assuming session expiry. Keep the extracted helper directory in place, or regenerate
the config after moving it. Same-version updates compare wheel SHA256, preserve prior installs on failure
and require copying new config/reconnection. Do not treat one page as the whole library: follow
has_more/next_offset. Missing features are unknown, and metadata never proves playback availability.

A container/remote host is not the local desktop; do not promise a browser there. Current-user Windows
DPAPI sessions are not portable to Linux/other users and do not protect against same-user malware.
MCP hosts/models may receive music metadata/listening evidence; review their privacy settings.

Before uninstall.cmd, disable the host service. Removal affects only the current beta environment,
not system Python, Apple settings or playlists. forget-login.cmd removes the shared local NetEase session
after confirmation; revoke exposed server sessions separately in the official account.
No maintainer credentials/history/telemetry are bundled. Checksums detect corruption, not publisher
identity; scripts are unsigned. Use trusted distribution channels.
[Feedback](https://github.com/Z-Han-Z/apple-music-playlists/issues): sanitized versions/steps/errors only.
Advanced details: docs/netease-port.md. The wheel includes the guides.

# Apple Music MCP Playlist-Kurator

![Apple Music MCP — natürlichsprachige Playlists, geprüft im Apple-Music-Katalog](https://raw.githubusercontent.com/Z-Han-Z/apple-music-playlists/main/.github/assets/social-preview.jpg)

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | Deutsch | [Français](README_FR.md)

**Beschreibe ein Gefühl, eine Szene, Epoche, Spannung oder einen Erzählbogen; der MCP-Agent formt
daraus eine Apple-Music-Playlist mit den richtigen Versionen, stimmiger Dramaturgie und fließenden Übergängen.**

Die primäre Schnittstelle ist der lokale stdio-Dienst `am-mcp`. Das Modell im MCP-Client versteht
die Beschreibung; dieser Dienst durchsucht den Katalog, löst Titel eindeutig auf und führt
Kontovorgänge aus. Ein weiteres LLM oder ein zusätzlicher API-Key ist nicht nötig. Clients mit
Prompts können `create_playlist_from_description` wählen; sonst genügt dieselbe Beschreibung im Chat.

Benötigt Python 3.10+ und läuft unter Windows, macOS und Linux. Zur Laufzeit wird nur die
Standardbibliothek verwendet. Standardmäßig wird das öffentliche Developer-Token aus Apples
Webplayer geladen; eine Mitgliedschaft im Apple Developer Program ist nicht erforderlich.
Künstlerlisten oder fertige Playlists sind nicht enthalten.

## Schnellstart

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "Meine Playlist" --tracks "Titel A - Interpret X, Titel B - Interpret Y"
```

Oder als Befehle installieren:

```bash
pip install apple-music-playlists
am-playlist status
am-playlist login
```

Danach stehen `am-playlist` (CLI) und `am-mcp` (MCP-stdio-Server) bereit. Für die Entwicklung:
`pip install -e .`.

## Zugangsdaten

Das Developer-Token wird automatisch geholt. Für Lese- und Schreibzugriffe auf die persönliche
Mediathek ist einmalig eine Apple-ID-Anmeldung nötig:

```bash
am-playlist login
```

Unterstützt werden die Windows-App Apple Music, ein Playwright-Browser und das manuelle Kopieren
des `media-user-token`. Vollständige Schritte und Sicherheitshinweise stehen in
[SETUP.en.md](SETUP.en.md). `config.json`, `.p8`-Schlüssel, Hörverlauf und erzeugte Playlists
dürfen nicht in Git gelangen.

## Funktionen

- Katalogsuche und Versionsabgleich nach Titel/Interpret oder ISRC.
- Playlists erstellen, erweitern, anzeigen und löschen; `dry_run` vor großen Änderungen.
- Metadatenprüfung: Länge, Künstleranteile, Genres, Epochen, Duplikate und kurze Interludes.
- Audioanalyse: BPM, Tonart, Lautheit, Energie, Valenz, Übergänge und Gesamtbogen.
- Reihenfolgeoptimierung mit erhaltenen Gruppen und sechs narrativen Bögen.
- Zuletzt gespielt und Wiedergabezahlen aus Apple Music Replay.

```bash
am-playlist search "Titel Interpret"
am-playlist playlists
am-playlist create --name "Name" --tracks "Titel - Interpret, ..."
python playlist_audit.py "Name"
python playlist_flow.py "Name"
python playlist_optimize.py list.json -o order.json --arc cinderella
```

## MCP, Agenten und Container

```json
{
  "mcpServers": {
    "applemusic": {
      "command": "am-mcp",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

Der Server stellt 13 Werkzeuge bereit. `am_resolve_candidates` gleicht den vom LLM vorgeschlagenen
Kandidatenpool mit echten Apple-Music-Metadaten ab, bewertet aber nicht die thematische Passung:
Das Modell vergleicht die Kandidaten direkt mit den Worten des Nutzers. Die Reihenfolgeoptimierung
ist erst nach der Auswahl optional. Die Werkzeuge enthalten englisch/chinesische Beschreibungen sowie Annotationen für
Nur-Lesen, Schreiben und destruktive Aktionen bereit. Anleitungen für Codex, Claude, Cursor,
VS Code/Copilot, Gemini CLI, Windsurf, Docker, Cordis/DSH und Harness stehen in
[docs/client-setup.md](docs/client-setup.md).

```bash
docker build -t apple-music-playlists:1.4.0 .
```

Der stdio-Container benötigt `-i` und darf nicht mit `-d` laufen. Nach der Anmeldung auf dem Host
wird nur das anwendungsspezifische Konfigurationsverzeichnis beschreibbar nach `/home/app/.config/am-playlist` und ein
Cache nach `/home/app/.cache/am-playlist` eingebunden. Tokens gehören nie in das Image.

## Sicherheit und Grenzen

- Vor Schreibzugriffen `am_status`, vor großen Stapeln `dry_run` verwenden.
- Vor dem Löschen das Ziel anzeigen und bestätigen lassen; MCP verlangt zusätzlich `confirm=true`.
- Apple erlaubt Änderungen nur durch den API-Client, der die Playlist erstellt hat.
- Beim Erstellen werden Titel der Mediathek hinzugefügt; das Löschen der Playlist entfernt sie nicht.

## Tests

```bash
python -m unittest discover -s tests -v
```

Alle Tests laufen offline und benötigen keine Apple-Zugangsdaten. Mehr unter [`docs/`](docs/),
[`skill/`](skill/) und [CHANGELOG.md](CHANGELOG.md).

MIT-Lizenz. Kein offizielles Apple-Projekt. Verwende dein eigenes Konto und beachte Apples Bedingungen.

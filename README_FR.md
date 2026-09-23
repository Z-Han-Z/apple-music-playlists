# Curateur MCP de playlists Apple Music

![Apple Music MCP — playlists en langage naturel vérifiées dans le catalogue Apple Music](https://raw.githubusercontent.com/Z-Han-Z/apple-music-playlists/main/.github/assets/social-preview.jpg)

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | Français

**Décrivez une émotion, une scène, une époque, une tension ou un arc narratif ; l'agent MCP en fait
une playlist Apple Music aux bonnes versions, avec une progression cohérente et des transitions fluides.**

L'interface principale est le service stdio local `am-mcp`. Le modèle du client MCP interprète la
description ; ce service recherche dans le catalogue, résout précisément les titres et agit sur le
compte. Aucun autre LLM ni clé API supplémentaire n'est requis. Les clients compatibles Prompts
peuvent choisir `create_playlist_from_description`; sinon, envoyez la même description dans le chat.

Nécessite Python 3.10+ et fonctionne sous Windows, macOS et Linux. À l'exécution, seule la
bibliothèque standard est utilisée. Par défaut, le developer token public du lecteur web Apple est
récupéré automatiquement ; le programme Apple Developer n'est donc pas requis. Aucun catalogue
d'artistes ni playlist prête à l'emploi n'est inclus.

## Démarrage rapide

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "Ma playlist" --tracks "Titre A - Artiste X, Titre B - Artiste Y"
```

Ou installez les commandes :

```bash
pip install apple-music-playlists
am-playlist status
am-playlist login
```

Si [uv](https://docs.astral.sh/uv/concepts/tools/) est déjà installé, vous pouvez aussi lancer le
serveur sans installation permanente :

```bash
uvx --from apple-music-playlists am-playlist status
uvx --from apple-music-playlists am-playlist login
uvx --from apple-music-playlists am-mcp
```

Pour utiliser `uvx` dans un client MCP, configurez `"command":"uvx"` et
`"args":["--from","apple-music-playlists","am-mcp"]`.

Vous obtenez `am-playlist` (CLI) et `am-mcp` (serveur MCP stdio). Pour le développement, utilisez
`pip install -e .`.

## Identifiants

Le developer token est récupéré automatiquement. La lecture ou l'écriture dans votre bibliothèque
personnelle demande une connexion Apple ID unique :

```bash
am-playlist login
```

L'application Apple Music pour Windows, un navigateur Playwright et la copie manuelle du
`media-user-token` sont pris en charge. Consultez [SETUP.en.md](SETUP.en.md) pour les étapes et la
sécurité. Ne publiez jamais `config.json`, une clé `.p8`, l'historique d'écoute ou les playlists générées.

## Fonctions

- Recherche dans le catalogue et choix de version par titre/artiste ou ISRC.
- Création, ajout, affichage et suppression, avec `dry_run` avant les gros lots.
- Audit des métadonnées : durée, artistes, genres, époques, doublons et interludes.
- Audit audio : BPM, tonalité, volume, énergie, valence, transitions et arc global.
- Optimisation de l'ordre conservant les groupes, avec six arcs narratifs.
- Historique récent et classements de lectures Apple Music Replay.

```bash
am-playlist search "titre artiste"
am-playlist playlists
am-playlist create --name "Nom" --tracks "Titre - Artiste, ..."
python playlist_audit.py "Nom"
python playlist_flow.py "Nom"
python playlist_optimize.py list.json -o order.json --arc cinderella
```

## MCP, agents et conteneurs

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

Le serveur fournit 13 outils. `am_resolve_candidates` confronte le vivier proposé par le LLM aux
métadonnées réelles d'Apple Music, sans noter l'adéquation au thème : le modèle compare directement
les candidats aux mots de l'utilisateur. L'optimisation de l'ordre reste facultative après la
sélection. Les outils incluent des descriptions anglais/chinois et des annotations lecture seule,
écriture et opération destructive. La configuration de Codex, Claude, Cursor, VS Code/Copilot,
Gemini CLI, Windsurf, Docker, Cordis/DSH et Harness est détaillée dans
[docs/client-setup.md](docs/client-setup.md).

```bash
docker build -t apple-music-playlists:1.4.0 .
```

Le conteneur stdio exige `-i` et ne doit pas utiliser `-d`. Connectez-vous sur l'hôte, montez la
configuration propre à l'application avec écriture dans `/home/app/.config/am-playlist` et un cache
dans `/home/app/.cache/am-playlist`. N'intégrez jamais de token dans l'image.

## Sécurité et limites

- Appelez `am_status` avant toute écriture et utilisez `dry_run` avant un gros lot.
- Affichez la cible et obtenez une confirmation avant suppression ; MCP exige aussi `confirm=true`.
- Apple n'autorise la modification que par le client API qui a créé la playlist.
- Créer une playlist ajoute ses titres à la bibliothèque ; supprimer la playlist ne retire pas les titres.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tous les tests sont hors ligne et sans identifiants Apple. Voir aussi [`docs/`](docs/), [`skill/`](skill/)
et [CHANGELOG.md](CHANGELOG.md).

Licence MIT. Projet communautaire non affilié à Apple. Utilisez votre compte et respectez les conditions Apple.

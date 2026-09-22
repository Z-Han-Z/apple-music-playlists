# Herramientas para listas de Apple Music

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | Español |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | [Français](README_FR.md)

**Describe la lista que quieres; tu agente MCP la selecciona, valida cada tema en Apple Music, la previsualiza y la crea.**

La interfaz principal es el servicio local stdio `am-mcp`. El modelo del cliente MCP interpreta la
descripción y este servicio busca en el catálogo, resuelve las canciones y opera la cuenta. No
incorpora otro LLM ni exige otra clave API. Los clientes con Prompts pueden elegir
`create_playlist_from_description`; en los demás basta con enviar la misma descripción por chat.

Requiere Python 3.10+ y funciona en Windows, macOS y Linux. En ejecución solo usa la biblioteca
estándar. De forma predeterminada obtiene el developer token público del reproductor web de Apple,
por lo que no exige Apple Developer Program. No incluye listas de artistas ni listas ya curadas.

## Inicio rápido

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "Mi lista" --tracks "Canción A - Artista X, Canción B - Artista Y"
```

O instálalo como comandos:

```bash
pip install "apple-music-playlists @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist status
am-playlist login
```

Se instalan `am-playlist` (CLI) y `am-mcp` (servidor MCP stdio). Para desarrollo usa
`pip install -e .`.

## Credenciales

El developer token se obtiene automáticamente. Para leer o modificar tu biblioteca debes iniciar
sesión una vez con tu Apple ID:

```bash
am-playlist login
```

Se admite la app Apple Music de Windows, un navegador Playwright o copiar manualmente
`media-user-token`. Consulta [SETUP.en.md](SETUP.en.md) para todos los pasos y advertencias.
No subas `config.json`, claves `.p8`, historial de escucha ni listas generadas a Git.

## Funciones principales

- Búsqueda y resolución de versiones por título/artista o ISRC.
- Crear, añadir, ver y borrar listas; `dry_run` antes de cambios grandes.
- Auditoría de metadatos: duración, artistas, géneros, épocas, duplicados e interludios.
- Auditoría sonora: BPM, tonalidad, volumen, energía, valencia, transiciones y arco global.
- Optimización de orden con grupos conservados y seis arcos narrativos.
- Reproducciones recientes y clasificaciones de Apple Music Replay.

```bash
am-playlist search "canción artista"
am-playlist playlists
am-playlist create --name "Nombre" --tracks "Canción - Artista, ..."
python playlist_audit.py "Nombre"
python playlist_flow.py "Nombre"
python playlist_optimize.py list.json -o order.json --arc cinderella
```

## MCP, agentes y contenedores

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

El servidor ofrece 13 herramientas. `am_resolve_candidates` contrasta el grupo propuesto por el LLM
con metadatos reales de Apple Music, pero no puntúa la afinidad temática: el modelo compara cada
candidato directamente con las palabras del usuario. La optimización del orden es opcional y solo
refina transiciones después de la selección. Las herramientas incluyen descripciones en inglés/chino y annotations de solo lectura,
escritura y operaciones destructivas. La configuración de Codex, Claude, Cursor, VS Code/Copilot,
Gemini CLI, Windsurf, Docker, Cordis/DSH y Harness está en
[docs/client-setup.md](docs/client-setup.md).

```bash
docker build -t apple-music-playlists:1.2.0 .
```

Un contenedor stdio necesita `-i` y no debe ejecutarse con `-d`. Inicia sesión en el host y monta la
configuración específica de la aplicación con escritura en `/home/app/.config/am-playlist`; monta una caché en
`/home/app/.cache/am-playlist`. Nunca incluyas tokens en la imagen.

## Seguridad y límites

- Ejecuta `am_status` antes de escribir y `dry_run` antes de lotes grandes.
- Muestra el objetivo y pide confirmación antes de borrar; MCP también exige `confirm=true`.
- Apple solo permite modificar una lista al cliente API que la creó.
- Crear una lista añade sus canciones a la biblioteca; borrar la lista no elimina las canciones.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Todas las pruebas son offline y no requieren credenciales. Más información en [`docs/`](docs/),
[`skill/`](skill/) y [CHANGELOG.md](CHANGELOG.md).

Licencia MIT. Proyecto comunitario no afiliado con Apple. Usa tu propia cuenta y respeta sus condiciones.

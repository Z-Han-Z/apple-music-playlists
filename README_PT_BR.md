# Kit de playlists do Apple Music

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | [한국어](README_KR.md) | [Español](README_ES.md) |
Português do Brasil | [Deutsch](README_DE.md) | [Français](README_FR.md)

**Descreva a playlist desejada; o agente MCP faz a curadoria, valida cada faixa no Apple Music, pré-visualiza e cria.**

A interface principal é o serviço stdio local `am-mcp`. O modelo do cliente MCP interpreta a
descrição; este serviço pesquisa o catálogo, resolve as faixas e opera a conta. Não há outro LLM
embutido nem outra chave de API. Em clientes com Prompts, escolha
`create_playlist_from_description`; nos demais, envie a mesma descrição no chat.

Requer Python 3.10+ e funciona no Windows, macOS e Linux. Em tempo de execução usa apenas a biblioteca
padrão. Por padrão, obtém o developer token público do player web da Apple, sem exigir o Apple
Developer Program. O projeto não inclui listas de artistas nem playlists prontas.

## Início rápido

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "Minha playlist" --tracks "Música A - Artista X, Música B - Artista Y"
```

Ou instale os comandos:

```bash
pip install "apple-music-playlists @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist status
am-playlist login
```

Isso instala `am-playlist` (CLI) e `am-mcp` (servidor MCP stdio). Para desenvolvimento use
`pip install -e .`.

## Credenciais

O developer token é obtido automaticamente. Para ler ou alterar sua biblioteca, faça login uma vez
com o Apple ID:

```bash
am-playlist login
```

Há suporte ao app Apple Music do Windows, navegador Playwright ou cópia manual do
`media-user-token`. Veja [SETUP.en.md](SETUP.en.md) para o procedimento completo e segurança.
Não envie `config.json`, chaves `.p8`, histórico de reprodução ou playlists geradas ao Git.

## Recursos

- Pesquisa e seleção da versão correta por título/artista ou ISRC.
- Criação, inclusão, visualização e exclusão de playlists, com `dry_run` antes de lotes grandes.
- Auditoria de metadados: duração, artistas, gêneros, épocas, duplicatas e interlúdios.
- Auditoria sonora: BPM, tom, volume, energia, valência, transições e arco geral.
- Otimização da ordem preservando grupos e escolhendo entre seis arcos narrativos.
- Histórico recente e rankings de reproduções do Apple Music Replay.

```bash
am-playlist search "música artista"
am-playlist playlists
am-playlist create --name "Nome" --tracks "Música - Artista, ..."
python playlist_audit.py "Nome"
python playlist_flow.py "Nome"
python playlist_optimize.py list.json -o order.json --arc cinderella
```

## MCP, agentes e contêineres

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

O servidor oferece 12 ferramentas, descrições em inglês/chinês e annotations de leitura, escrita e
operação destrutiva. A configuração para Codex, Claude, Cursor, VS Code/Copilot, Gemini CLI,
Windsurf, Docker, Cordis/DSH e Harness está em [docs/client-setup.md](docs/client-setup.md).

```bash
docker build -t apple-music-playlists:1.2.0 .
```

O contêiner stdio precisa de `-i` e não deve usar `-d`. Faça login no host, monte a configuração
com escrita em `/home/app/.config/am-playlist` e um cache gravável em
`/home/app/.cache/am-playlist`. Nunca grave tokens na imagem.

## Segurança e limitações

- Execute `am_status` antes de gravar e `dry_run` antes de lotes grandes.
- Mostre o alvo e peça confirmação antes de excluir; o MCP também exige `confirm=true`.
- A Apple só permite alterar uma playlist pelo cliente API que a criou.
- Criar uma playlist adiciona as músicas à biblioteca; excluir a playlist não remove as músicas.

## Testes

```bash
python -m unittest discover -s tests -v
```

Todos os testes são offline e dispensam credenciais. Veja também [`docs/`](docs/), [`skill/`](skill/)
e [CHANGELOG.md](CHANGELOG.md).

Licença MIT. Projeto comunitário sem afiliação com a Apple. Use sua conta e siga os termos da Apple.

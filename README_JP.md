# Apple Music MCP プレイリスト・キュレーター

![Apple Music MCP — Apple Music カタログで検証する自然言語プレイリスト](.github/assets/social-preview.jpg)

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
日本語 | [한국어](README_KR.md) | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | [Français](README_FR.md)

**感情、場面、時代、緊張感、物語の弧を言葉にすると、MCP エージェントが正確なバージョン、
自然な起伏とつながりを備えた、最初から最後まで聴ける Apple Music プレイリストへ仕上げます。**

中心となるインターフェースはローカルの `am-mcp` stdio サービスです。MCP クライアント側の
モデルが自然言語の要望を解釈し、本サービスがカタログ検索、正確な照合、アカウント操作を
担当します。別の LLM や API キーは不要です。Prompt 対応クライアントでは
`create_playlist_from_description` を選択でき、それ以外では要望をそのままチャットに入力できます。

Python 3.10 以上、Windows / macOS / Linux 対応。実行時依存は標準ライブラリのみです。
既定では Apple の Web プレーヤーに含まれる公開 developer token を取得するため、
Apple Developer Program は不要です。アーティスト一覧や完成済みプレイリストは同梱しません。

## クイックスタート

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "My Playlist" --tracks "Song A - Artist X, Song B - Artist Y"
```

コマンドとしてインストールする場合：

```bash
pip install apple-music-playlists
am-playlist status
am-playlist login
```

`am-playlist` CLI と `am-mcp` MCP stdio サーバーが利用可能になります。開発用は
`pip install -e .` を使用してください。

## 認証

developer token は初回実行時に自動取得されます。個人ライブラリの読み書きには、一度だけ
Apple ID でログインします：

```bash
am-playlist login
```

Windows Apple Music アプリ、Playwright、または `media-user-token` の手動コピーに対応します。
詳しい手順とセキュリティ上の注意は [SETUP.en.md](SETUP.en.md) を参照してください。
`config.json`、`.p8`、再生履歴、生成したプレイリストを Git にコミットしないでください。

## 主な機能

- 曲名・アーティストまたは ISRC で Apple Music catalog を検索し、バージョンを照合。
- プレイリストの作成、追加、表示、削除。大量操作の前に `dry_run` が可能。
- メタデータ診断：曲数、アーティスト集中度、ジャンル、年代、長さ、重複、短い間奏。
- 音響診断：BPM、キー、ラウドネス、energy、valence、曲間遷移、全体の物語曲線。
- グループを保持できる焼きなまし法の曲順最適化と、6 種類の narrative arc。
- 最近の再生履歴と Apple Music Replay の再生回数ランキング。

```bash
am-playlist search "曲名 アーティスト"
am-playlist playlists
am-playlist create --name "プレイリスト名" --tracks "曲名 - アーティスト, ..."
python playlist_audit.py "プレイリスト名"
python playlist_flow.py "プレイリスト名"
python playlist_optimize.py list.json -o order.json --arc cinderella
python listening_stats.py top --kind songs --year 2026
```

## MCP、エージェント、コンテナ

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

13 個の MCP ツールを公開します。`am_resolve_candidates` は LLM が出した候補群を Apple Music の
実メタデータに照合しますが、テーマ適合度は採点しません。モデルがユーザーの言葉と候補を直接比較し、
並び替え最適化は選曲後の任意の補助として使います。ツール説明は英語/中国語の併記で、読み取り専用・書き込み・
破壊的操作の annotation も含みます。Codex、Claude、Cursor、VS Code/Copilot、Gemini CLI、
Windsurf、Docker、Cordis/DSH、Harness の設定は
[docs/client-setup.md](docs/client-setup.md) を参照してください。

```bash
docker build -t apple-music-playlists:1.4.0 .
```

stdio コンテナでは `-i` が必須で、`-d` は使用できません。ホストでログインした後、専用設定ディレクトリを
`/home/app/.config/am-playlist` に書き込み可能で、キャッシュを
`/home/app/.cache/am-playlist` に書き込み可能でマウントします。トークンをイメージに含めないでください。

## 安全性と制限

- 書き込み前に `am_status`、大量操作前に `dry_run` を実行。
- 削除前に対象をユーザーへ提示し、MCP では `confirm=true` も必須。
- Apple の制限により、その API クライアントが作成したプレイリストだけを変更できます。
- プレイリスト作成時、曲はライブラリにも追加されます。プレイリスト削除では曲は削除されません。

## テスト

```bash
python -m unittest discover -s tests -v
```

テストはすべてオフラインで、Apple の認証情報は不要です。詳細は [`docs/`](docs/)、
[`skill/`](skill/)、[CHANGELOG.md](CHANGELOG.md) を参照してください。

MIT License。Apple の公式プロジェクトではありません。ご自身の Apple Music アカウントを使い、
Apple の利用規約に従ってください。

# Apple Music 플레이리스트 툴킷

[English](README.md) | [简体中文](README_ZH_CN.md) | [繁體中文](README_ZH_TW.md) |
[日本語](README_JP.md) | 한국어 | [Español](README_ES.md) |
[Português do Brasil](README_PT_BR.md) | [Deutsch](README_DE.md) | [Français](README_FR.md)

**원하는 플레이리스트를 설명하면 MCP 에이전트가 선곡하고 Apple Music에서 검증·미리보기 후 생성합니다.**

기본 인터페이스는 로컬 `am-mcp` stdio 서비스입니다. MCP 클라이언트의 모델이 자연어 요청을
해석하고, 이 서비스가 카탈로그 검색, 정확한 곡 매칭 및 계정 작업을 담당합니다. 별도의 LLM이나
API 키가 필요하지 않습니다. Prompt 지원 클라이언트에서는 `create_playlist_from_description`을
선택할 수 있고, 그 외 클라이언트에서는 같은 설명을 채팅으로 보내면 됩니다.

Python 3.10 이상과 Windows / macOS / Linux를 지원합니다. 런타임에는 Python 표준 라이브러리만
사용합니다. 기본 설정은 Apple 웹 플레이어의 공개 developer token을 자동으로 가져오므로
Apple Developer Program 가입이 필요하지 않습니다. 아티스트 목록이나 완성된 플레이리스트는 포함하지 않습니다.

## 빠른 시작

```bash
git clone https://github.com/Z-Han-Z/apple-music-playlists.git
cd apple-music-playlists
python am_playlist.py status
python am_playlist.py login
python am_playlist.py create --name "My Playlist" --tracks "Song A - Artist X, Song B - Artist Y"
```

명령으로 설치하려면:

```bash
pip install "apple-music-playlists @ git+https://github.com/Z-Han-Z/apple-music-playlists.git@v1.2.0"
am-playlist status
am-playlist login
```

설치 후 `am-playlist` CLI와 `am-mcp` MCP stdio 서버를 사용할 수 있습니다. 개발 환경에서는
`pip install -e .`을 사용하세요.

## 인증

developer token은 처음 실행할 때 자동으로 가져옵니다. 개인 보관함을 읽거나 쓰려면 한 번 Apple ID로
로그인해야 합니다.

```bash
am-playlist login
```

Windows Apple Music 앱, Playwright 브라우저 또는 `media-user-token` 수동 복사를 지원합니다.
자세한 절차와 보안 지침은 [SETUP.en.md](SETUP.en.md)를 참고하세요. `config.json`, `.p8`, 청취 기록,
생성된 플레이리스트를 Git에 커밋하지 마세요.

## 주요 기능

- 곡명/아티스트 또는 ISRC로 Apple Music catalog를 검색하고 올바른 버전을 매칭합니다.
- 플레이리스트 생성, 추가, 보기, 삭제와 대량 작업 전 `dry_run` 미리보기.
- 메타데이터 진단: 곡 수, 아티스트 집중도, 장르, 시대, 길이, 중복, 짧은 인터루드.
- 오디오 특성 진단: BPM, 키, 음량, energy, valence, 인접 곡 전환, 전체 서사 곡선.
- 그룹을 유지할 수 있는 simulated annealing 순서 최적화와 여섯 가지 narrative arc.
- 최근 재생 내역과 Apple Music Replay 재생 횟수 순위.

```bash
am-playlist search "곡명 아티스트"
am-playlist playlists
am-playlist create --name "플레이리스트 이름" --tracks "곡명 - 아티스트, ..."
python playlist_audit.py "플레이리스트 이름"
python playlist_flow.py "플레이리스트 이름"
python playlist_optimize.py list.json -o order.json --arc cinderella
python listening_stats.py top --kind songs --year 2026
```

## MCP, 에이전트 및 컨테이너

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

11개의 MCP 도구를 제공합니다. 도구 설명은 영어/중국어로 제공되고 읽기 전용, 쓰기, 파괴적 작업
annotation을 포함합니다. Codex, Claude, Cursor, VS Code/Copilot, Gemini CLI, Windsurf, Docker,
Cordis/DSH 및 Harness 설정은 [docs/client-setup.md](docs/client-setup.md)를 참고하세요.

```bash
docker build -t apple-music-playlists:1.2.0 .
```

stdio 컨테이너는 `-i`가 필요하며 `-d`를 사용하면 안 됩니다. 호스트에서 로그인한 뒤 전용 설정 디렉터리를
`/home/app/.config/am-playlist`에 쓰기 가능하게, 캐시를 `/home/app/.cache/am-playlist`에 쓰기
가능하게 마운트하세요. 토큰을 이미지에 포함하지 마세요.

## 안전 및 제한 사항

- 쓰기 전에 `am_status`, 대량 작업 전에 `dry_run`을 실행합니다.
- 삭제 전에 대상을 사용자에게 보여 주고 확인받아야 하며 MCP에서는 `confirm=true`도 필요합니다.
- Apple 제한상 해당 API 클라이언트가 만든 플레이리스트만 수정할 수 있습니다.
- 플레이리스트를 만들면 곡이 보관함에도 추가됩니다. 플레이리스트 삭제는 곡을 제거하지 않습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

모든 테스트는 오프라인이며 Apple 인증 정보가 필요하지 않습니다. 자세한 내용은 [`docs/`](docs/),
[`skill/`](skill/), [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

MIT License. Apple의 공식 프로젝트가 아닙니다. 본인의 Apple Music 계정으로 Apple 이용 약관을 준수하세요.

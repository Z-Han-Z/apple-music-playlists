#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_playlist.py — 全自动创建 Apple Music 歌单（Windows / macOS / Linux 通用）

原理
----
Apple Music 网页播放器 (music.apple.com) 的 JS bundle 里内嵌了一个公开的
"developer token"(ES256 JWT)。用它 + 你自己账号的 music-user-token，
就可以直接调用 Apple Music 的 REST API：

    POST https://api.music.apple.com/v1/me/library/playlists          创建歌单(可同时带曲目)
    POST https://api.music.apple.com/v1/me/library/playlists/{id}/tracks  继续加曲目
    GET  https://api.music.apple.com/v1/catalog/{storefront}/search    搜索曲目

developer token 由本脚本自动抓取并缓存（过期自动重抓），
music-user-token 只需登录一次（见 `login` 子命令），之后全部自动。

零第三方依赖（仅标准库）。`login` 子命令如需浏览器自动化才用 Playwright。

用法
----
    python am_playlist.py login                 # 一次性：抓取并保存 music-user-token
    python am_playlist.py login --from-clipboard  # 从剪贴板读（先在 DevTools 里复制 cookie）
    python am_playlist.py login --token XXX     # 或直接给出 token 值
    python am_playlist.py status                # 查看 token 状态
    python am_playlist.py search "周杰伦 晴天"   # 搜索曲目
    python am_playlist.py list                  # 列出我的歌单
    python am_playlist.py show "歌单名"          # 查看歌单曲目
    python am_playlist.py create --name "通勤" --tracks "Song A - Artist, Song B"
    python am_playlist.py create --name "通勤" --json tracks.json     # 批量/脚本化
    python am_playlist.py add --playlist "通勤" --tracks "..."
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from am_paths import VERSION, cache_dir, config_dir  # noqa: E402

# Windows 控制台默认 GBK，强制 UTF-8 以免中文乱码
if os.name == "nt":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ---------------------------------------------------------------- 常量

API_ROOT = "https://api.music.apple.com/v1"
AMP_ROOT = "https://amp-api.music.apple.com/v1"
WEB_HOME = "https://music.apple.com/us/browse"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_TRACKS_PER_REQUEST = 100      # Apple 单次写入上限（社区实测；超过则分批）
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
SCRIPT_RE = re.compile(r'src="(/assets/[^"]+\.js)"')


# config_dir() / cache_dir() / VERSION 的唯一实现在 am_paths.py ——
# 那是个平台无关模块，playlist_optimize.py 那类纯算法代码可以只依赖它。
CONFIG_PATH = config_dir() / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    try:  # 尽量收紧权限（POSIX 才有意义）
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass


# ---------------------------------------------------------------- HTTP

class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} {url}\n{body[:600]}")
        self.status = status
        self.body = body


class NeedLogin(RuntimeError):
    pass


def require_user(cfg: dict) -> str:
    tok = get_user_token(cfg)
    if not tok:
        raise NeedLogin("尚未保存 music-user-token")
    return tok


def http(method: str, url: str, *, headers: dict | None = None,
         body: dict | None = None, timeout: int = 30, retries: int = 2) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    h = {"User-Agent": UA, "Accept": "application/json",
         "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
         "Accept-Encoding": "gzip",
         "Origin": "https://music.apple.com", "Referer": "https://music.apple.com/"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})

    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                # 实测：Apple 会在**没有 Accept-Encoding 请求**的情况下也返回
                # Content-Encoding: gzip。不解压就会把二进制当 UTF-8 解出乱码，
                # 于是"响应体是空的"这种误判就来了（创建歌单的响应正是如此）。
                enc = (r.headers.get("Content-Encoding") or "").lower()
                if "gzip" in enc:
                    raw = gzip.decompress(raw)
                elif "deflate" in enc:
                    try:
                        raw = zlib.decompress(raw)
                    except zlib.error:
                        raw = zlib.decompress(raw, -15)
                return r.status, raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code == 429 and attempt < retries:
                wait = 20 * (attempt + 1) + random.uniform(0, 5)
                print(f"  ! 触发限流(429)，等待 {wait:.0f}s 后重试…", file=sys.stderr)
                time.sleep(wait)
                continue
            last_err = ApiError(e.code, raw, url)
            # 429 之外的重试没有意义，直接抛
            raise last_err
        except urllib.error.URLError as e:
            last_err = ApiError(0, str(e), url)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_err
    raise last_err  # pragma: no cover


def json_or_empty(body: str):
    """Apple 有些写操作会返回空响应体（或 204 无内容），不能直接 json.loads。"""
    if not body or not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def resolve_storefront(explicit: str | None, cfg: dict, dev: str,
                       user: str | None = None) -> str:
    """地区码解析顺序：显式参数 → 配置里记住的 → 问 /me/storefront → 兜底 us。

    登录时会把账号的真实 storefront 存进配置，所以之后不用每次传 --storefront。
    """
    if explicit:
        return explicit
    if cfg.get("storefront"):
        return cfg["storefront"]
    if user:
        try:
            _, body = api("GET", "/me/storefront", dev=dev, user=user)
            sf = json.loads(body)["data"][0]["id"]
            cfg["storefront"] = sf
            save_config(cfg)
            return sf
        except Exception:
            pass
    return "us"


def api(method: str, path: str, *, dev: str, user: str | None = None,
        body: dict | None = None, root: str = API_ROOT,
        query: dict | None = None) -> tuple[int, str]:
    url = root + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
    headers = {"Authorization": f"Bearer {dev}"}
    if user:
        headers["Music-User-Token"] = user
    return http(method, url, headers=headers, body=body)


# ---------------------------------------------------------------- token

def jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def scrape_developer_token(verbose: bool = False) -> str:
    """从 music.apple.com 前端 bundle 里抓公开 developer token（无需开发者账号）。"""
    if verbose:
        print("  · 抓取 music.apple.com 首页…")
    status, html = http("GET", WEB_HOME)
    if status != 200:
        raise RuntimeError(f"无法访问 music.apple.com (HTTP {status})")

    candidates: list[str] = []
    srcs = SCRIPT_RE.findall(html)
    candidates += JWT_RE.findall(html)
    for src in srcs[:6]:
        try:
            st, js = http("GET", "https://music.apple.com" + src, timeout=60)
            if st == 200:
                candidates += JWT_RE.findall(js)
                if verbose:
                    print(f"  · 扫描 {src} → 命中 {len(JWT_RE.findall(js))}")
        except Exception as e:
            if verbose:
                print(f"  · 跳过 {src}: {e}")
        if candidates:
            break

    now = int(time.time())
    best = None
    for tok in candidates:
        try:
            c = jwt_claims(tok)
        except Exception:
            continue
        if c.get("exp", 0) <= now + 3600:
            continue
        # 网页播放器 token 的特征
        if c.get("iss") == "AMPWebPlay" or c.get("root_https_origin"):
            best = tok
            break
        best = best or tok
    if not best:
        raise RuntimeError("未能在网页 bundle 中找到可用的 developer token")
    return best


def get_developer_token(cfg: dict, refresh: bool = False, verbose: bool = False) -> str:
    """优先用自己缓存的（自己申请 .p8 生成的 / 上次抓的），过期则重抓。"""
    tok = cfg.get("developer_token")
    if tok and not refresh:
        try:
            if jwt_claims(tok).get("exp", 0) > time.time() + 86400:
                return tok
        except Exception:
            pass
    tok = scrape_developer_token(verbose=verbose)
    cfg["developer_token"] = tok
    cfg["developer_token_fetched_at"] = int(time.time())
    save_config(cfg)
    return tok


def get_user_token(cfg: dict) -> str | None:
    return os.environ.get("APPLE_MUSIC_USER_TOKEN") or cfg.get("music_user_token")


def generate_developer_token(key_path: str, key_id: str, team_id: str,
                             ttl_days: int = 150) -> str:
    """用自己 Apple Developer 账号的 MusicKit .p8 私钥生成 ES256 JWT（需 cryptography）。"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
    except ImportError:
        raise SystemExit("需要 cryptography：pip install cryptography\n"
                         "（若不想装，可继续使用网页 token，见 `login`）")

    header = {"alg": "ES256", "kid": key_id}
    now = int(time.time())
    claims = {"iss": team_id, "iat": now, "exp": now + ttl_days * 86400}

    def b64(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    signing_input = (b64(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     b64(json.dumps(claims, separators=(",", ":")).encode())).encode()
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input.decode() + "." + b64(raw)


# ---------------------------------------------------------------- cookie 采集

def harvest_cookie_via_playwright(headless: bool = False) -> str | None:
    """用 Playwright 打开浏览器，等你登录后自动读取 media-user-token cookie。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    profile = config_dir() / "browser-profile"
    print("  正在启动浏览器（Edge/Chrome）…请在窗口里登录 Apple ID（含双重认证）。")
    print("  登录成功后脚本会自动读取 cookie，无需手动操作。\n")
    with sync_playwright() as p:
        ctx = None
        for kwargs in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(profile), headless=headless, args=["--disable-blink-features=AutomationControlled"],
                    **kwargs)
                break
            except Exception:
                continue
        if ctx is None:
            return None
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://music.apple.com/login", wait_until="domcontentloaded", timeout=120_000)
            deadline = time.time() + 600
            while time.time() < deadline:
                for c in ctx.cookies("https://music.apple.com"):
                    if c["name"] == "media-user-token" and c.get("value"):
                        print("  ✓ 已获取 media-user-token")
                        return c["value"]
                time.sleep(2)
            print("  ✗ 等待超时（10 分钟）未检测到登录 cookie")
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    return None


def harvest_from_windows_app() -> str | None:
    """
    从 Apple Music for Windows 应用（WebView2）的 cookie 库里读取 media-user-token。
    需要先在商店版 Apple Music 应用里登录过。Chromium 的 cookie 用 AES-GCM 加密，
    密钥由 DPAPI(当前用户) 保护，因此同一用户下的脚本可以解密。
    """
    if os.name != "nt":
        return None
    import glob
    import sqlite3
    import shutil
    import tempfile

    pkg_glob = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages",
                            "AppleInc.AppleMusicWin_*", "LocalCache", "Local",
                            "WebViewUserDataDirs", "*", "EBWebView")
    roots = glob.glob(pkg_glob)
    if not roots:
        return None

    for root in roots:
        db = os.path.join(root, "Default", "Network", "Cookies")
        state = os.path.join(root, "Local State")
        if not (os.path.exists(db) and os.path.exists(state)):
            continue
        try:
            ls = json.loads(Path(state).read_text(encoding="utf-8"))
            enc_key_b64 = ls["os_crypt"]["encrypted_key"]
            blob = base64.b64decode(enc_key_b64)
            if not blob.startswith(b"DPAPI"):
                print("  ! 该 WebView2 使用 App-Bound 加密，本路径不可用", file=sys.stderr)
                continue
            import ctypes
            import ctypes.wintypes as wt

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

            buf = ctypes.create_string_buffer(blob[5:], len(blob) - 5)
            blobin = DATA_BLOB(len(blob) - 5, ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
            blobout = DATA_BLOB()
            if not ctypes.windll.crypt32.CryptUnprotectData(
                    ctypes.byref(blobin), None, None, None, None, 0, ctypes.byref(blobout)):
                continue
            key = ctypes.string_at(blobout.pbData, blobout.cbData)
            ctypes.windll.kernel32.LocalFree(blobout.pbData)

            tmp = os.path.join(tempfile.gettempdir(), "am_cookies_copy.db")
            shutil.copy2(db, tmp)
            con = sqlite3.connect(tmp)
            rows = con.execute(
                "select name, encrypted_value from cookies where name='media-user-token'").fetchall()
            con.close()
            os.remove(tmp)
        except Exception:
            continue

        for _name, enc in rows:
            try:
                if enc[:3] in (b"v10", b"v11"):
                    enc = enc[3:]
                nonce, payload = enc[:12], enc[12:-16]
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                return AESGCM(key).decrypt(nonce, payload + enc[-16:], None).decode()
            except ImportError:
                print("  ! 需要 cryptography 才能解密 WebView2 cookie：pip install cryptography",
                      file=sys.stderr)
                return None
            except Exception:
                continue
    return None


# ---------------------------------------------------------------- 功能

def cmd_status(args) -> int:
    """报告两个令牌的状态。

    developer token 是 JWT，能解出确切的过期时间；music-user-token 是不透明字符串，
    **没有可解析的过期时间**，只能实调验证——所以这里会真的打几个接口。
    """
    cfg = load_config()
    now = int(time.time())

    def ts(x):
        return time.strftime("%Y-%m-%d %H:%M", time.gmtime(x)) + " UTC"

    print(f"配置文件 : {CONFIG_PATH}")
    print(f"现在     : {ts(now)}")

    print("\n── developer token（网页播放器内嵌的公开 token）")
    tok = cfg.get("developer_token")
    if not tok:
        print("   未保存 —— 运行任意命令会自动抓取")
    else:
        try:
            c = jwt_claims(tok)
            left = c.get("exp", 0) - now
            print(f"   iss    : {c.get('iss')}")
            print(f"   iat    : {ts(c['iat'])}")
            print(f"   exp    : {ts(c['exp'])}")
            print(f"   剩余   : {left/86400:.2f} 天")
            print(f"   状态   : {'✅ 有效' if left > 0 else '❌ 已过期'}")
            if 0 < left < 86400:
                print("   ⚠️ 不足 1 天；下次运行会自动重抓，无需手动处理")
        except Exception:
            print("   ❌ 无法解析 —— 删掉配置里的 developer_token 可触发重抓")

    print("\n── music-user-token（你的账号登录态）")
    user = get_user_token(cfg)
    if not user:
        print("   未保存 —— 运行 python am_playlist.py login")
    else:
        src = ("环境变量 APPLE_MUSIC_USER_TOKEN"
               if os.environ.get("APPLE_MUSIC_USER_TOKEN") else "配置文件")
        saved = cfg.get("music_user_token_saved_at")
        print(f"   来源   : {src}")
        print(f"   长度   : {len(user)} 字符")
        if saved:
            print(f"   保存于 : {ts(saved)}（{(now - saved)/86400:.1f} 天前）")
        print("   注意   : 不透明字符串，**没有可解析的过期时间**（官方只说约 6 个月），")
        print("            唯一可靠的判断方式是实调 ↓")

    if tok and user:
        print("\n── 在线校验（实调，可靠依据）")
        checks = [
            ("读账号信息", API_ROOT, "/me/storefront", None),
            ("读音乐库", API_ROOT, "/me/library/playlists", {"limit": 1}),
            ("读最近播放", API_ROOT, "/me/recent/played/tracks", {"limit": 1}),
            ("播放次数", AMP_ROOT, "/me/music-summaries/search", {"period": "year,all-time"}),
        ]
        passed = 0
        for label, root, path, q in checks:
            try:
                st, _ = api("GET", path, dev=tok, user=user, root=root, query=q)
                print(f"   ✅ {label:<10} HTTP {st}")
                passed += 1
            except ApiError as e:
                hint = {401: "developer token 无效",
                        403: "music-user-token 失效 → 重新 login"}.get(e.status, "")
                print(f"   ❌ {label:<10} HTTP {e.status}  {hint}")
        print(f"   {passed}/{len(checks)} 通过 → "
              + ("两个令牌都可用" if passed == len(checks) else "见上面的提示"))
    return 0


# 查询里没提到、却出现在曲名里的"版本后缀"——出现就扣分，避免匹配到现场版/伴奏版。
#
# ⚠️ 必须区分两种语言，不能一律子串匹配：
#   · 拉丁词要**按整词**匹配。子串匹配会误伤一大片——"Alive" / "Olive" /
#     "Deliver" 全都含 "live"，会被当成现场版扣 1.2 分，把好结果挤下去。
#   · CJK 没有词边界，只能继续子串匹配。
# 另外 "mix" 不能单独按整词列出，否则 "Remix" 反而不再算版本后缀；
# 这类合成词要显式进表（remix / re-mix）。
VERSION_NOISE_WORDS = (
    "remastered", "instrumental", "acoustic", "karaoke", "remaster", "reprise",
    "deluxe", "stereo", "version", "remix", "re-mix", "bonus", "cover", "live",
    "demo", "edit", "mono",
)
VERSION_NOISE_CJK = ("现场", "演唱会", "伴奏", "翻唱", "重制", "纯音乐")

# 保留这个名字：文档里用它指代"版本后缀扣分"这件事
VERSION_NOISE = VERSION_NOISE_WORDS + VERSION_NOISE_CJK

_NOISE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in VERSION_NOISE_WORDS) + r")\b", re.I)


def version_noise_hits(title: str) -> list[str]:
    """曲名里命中了哪些"版本后缀"，返回小写词表。

    调用方拿它跟查询词比对，决定要不要扣分——所以这里只负责"命中什么"，
    不负责"该不该扣"。
    """
    low = (title or "").lower()
    hits = [w for w in VERSION_NOISE_CJK if w in low]
    hits += [m.group(0).lower() for m in _NOISE_RE.finditer(low)]
    return hits


def best_song_match(query: str, songs: list[dict]) -> dict | None:
    """从搜索结果里挑最匹配的一首：标题/艺人相似度打分，并惩罚没被要求的版本后缀。"""
    def norm(s: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower())

    if not songs:
        return None
    if " - " in query:
        want_t, want_a = query.split(" - ", 1)
    else:
        want_t, want_a = query, ""
    nt, na = norm(want_t), norm(want_a)
    # 查询自己提到的版本词不算"没被要求"。这里也要用同一套整词判定——
    # 否则查询 "Alive" 会因为自身含 "live" 而豁免所有现场版罚分。
    q_hits = set(version_noise_hits(want_t))

    scored = []
    for s in songs:
        a = s.get("attributes", {})
        raw_t = a.get("name") or ""
        t, ar = norm(raw_t), norm(a.get("artistName", ""))
        score = 0.0
        if nt:
            if nt == t:
                score += 3.0            # 曲名完全一致，最理想
            elif nt in t or t in nt:
                score += 2.0
        if na:
            if na == ar:
                score += 2.0            # 艺人完全一致
            elif na in ar or ar in na:
                score += 1.5
        # 曲名里带查询没要求的版本后缀 → 扣分（"Live" 之类）
        for w in version_noise_hits(raw_t):
            if w not in q_hits:
                score -= 1.2
                break
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored[0][0] > 0 else songs[0]


def resolve_tracks(items: list[str], dev: str, storefront: str, *,
                   isrcs: bool = False, quiet: bool = False) -> tuple[list[str], list[str]]:
    """把 '歌名 - 艺人' / ISRC 列表解析成 catalog song id 列表。"""
    ids: list[str] = []
    missed: list[str] = []

    if isrcs:
        for i in range(0, len(items), 25):
            chunk = [x.strip() for x in items[i:i + 25] if x.strip()]
            st, body = api("GET", f"/catalog/{storefront}/songs", dev=dev,
                           query={"filter[isrc]": ",".join(chunk)})
            found = {}
            for s in json.loads(body).get("data", []):
                found[s["attributes"].get("isrc")] = s["id"]
            for code in chunk:
                if code in found:
                    ids.append(found[code])
                else:
                    missed.append(code)
            if not quiet:
                print(f"  · ISRC 精确匹配 {len(found)}/{len(chunk)}")
        return ids, missed

    for i, q in enumerate(items, 1):
        q = q.strip()
        if not q:
            continue
        # 注意：把 "歌名 - 艺人" 整串丢给 Apple 搜索，结果会明显变差
        # （实测搜 "Hotel California - Eagles" 时录音室版根本不出现，只有各种 Live 版）。
        # 用空格分隔去搜，命中录音室版的概率高得多；打分仍用原始的 q。
        term = q.replace(" - ", " ")
        st, body = api("GET", f"/catalog/{storefront}/search", dev=dev,
                       query={"term": term, "types": "songs", "limit": 8})
        songs = json.loads(body).get("results", {}).get("songs", {}).get("data", [])
        hit = best_song_match(q, songs)
        if hit:
            a = hit["attributes"]
            ids.append(hit["id"])
            if not quiet:
                print(f"  [{i}/{len(items)}] ✓ {a.get('name')} — {a.get('artistName')}  ({hit['id']})")
        else:
            missed.append(q)
            if not quiet:
                print(f"  [{i}/{len(items)}] ✗ 未找到: {q}")
        time.sleep(0.4)  # 温和节流，避免 429
    return ids, missed


def find_playlist(name_or_id: str, dev: str, user: str) -> dict | None:
    if name_or_id.startswith("p."):
        st, body = api("GET", f"/me/library/playlists/{name_or_id}", dev=dev, user=user)
        d = json.loads(body).get("data", [])
        return d[0] if d else None
    st, body = api("GET", "/me/library/playlists", dev=dev, user=user,
                   query={"limit": 100})
    for p in json.loads(body).get("data", []):
        if p.get("attributes", {}).get("name") == name_or_id:
            return p
    return None


def read_clipboard() -> str | None:
    """读系统剪贴板（零依赖：优先 tkinter，失败则用 Win32 API）。"""
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            return root.clipboard_get().strip()
        finally:
            root.destroy()
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes as wt

            CF_UNICODETEXT = 13
            u = ctypes.windll.user32
            if not u.OpenClipboard(None):
                return None
            try:
                if not u.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return None
                h = u.GetClipboardData(CF_UNICODETEXT)
                p = ctypes.windll.kernel32.GlobalLock(h)
                try:
                    return ctypes.wstring_at(p).strip()
                finally:
                    ctypes.windll.kernel32.GlobalUnlock(h)
            finally:
                u.CloseClipboard()
        except Exception:
            return None
    return None


def clean_user_token(raw: str) -> str:
    """容错：允许用户直接粘贴整行 cookie、带引号、或带 'media-user-token=' 前缀。"""
    t = (raw or "").strip().strip('"').strip("'")
    if t.lower().startswith("media-user-token="):
        t = t.split("=", 1)[1]
    if ";" in t:
        t = t.split(";", 1)[0]
    return t.strip()


def cmd_login(args) -> int:
    cfg = load_config()
    token = args.token
    if getattr(args, "from_clipboard", False):
        raw = read_clipboard()
        if not raw:
            print("✗ 剪贴板是空的（或读不到）。请先在 DevTools 里复制 media-user-token 的值。")
            return 2
        token = clean_user_token(raw)
        print(f"· 从剪贴板读到 {len(token)} 个字符，按 media-user-token 处理")
    if token:
        token = clean_user_token(token)
    if not token:
        token = harvest_from_windows_app()
        if token:
            print("✓ 从 Apple Music Windows 应用的 cookie 库中读取到 token")
        else:
            print("· Apple Music 应用里没有可用的登录态，改用浏览器登录…")
            token = harvest_cookie_via_playwright(headless=False)
    if not token:
        print("\n未能自动获取，三选一：")
        print("  1) 【最快，30 秒】你已经开着 music.apple.com 的话：")
        print("       F12 → Application/应用 → 左侧 Cookies → https://music.apple.com")
        print("       → 找到 media-user-token → 双击 Value 全选复制")
        print("     然后回来跑：  python am_playlist.py login --from-clipboard")
        print("  2) 【之后全自动】在商店版 Apple Music 应用里登录一次，然后：")
        print("       pip install cryptography   &&   python am_playlist.py login")
        print("     说明：该应用的 WebView2 cookie 库只用了 DPAPI 加密（不是 Edge/Chrome 那套")
        print("     App-Bound 加密），所以本脚本能以你的身份解密读出 media-user-token。")
        print("  3) 【半自动】pip install playwright 后重跑 login，脚本会开 Edge 让你登录并自动读取。")
        return 2

    # 校验
    try:
        dev = get_developer_token(cfg)
        st, body = api("GET", "/me/storefront", dev=dev, user=token)
        sf = json.loads(body).get("data", [{}])[0].get("id", "?")
        cfg["storefront"] = sf          # 记住账号所在地区，之后不用每次传 --storefront
        print(f"✓ token 校验通过，storefront = {sf}")
    except ApiError as e:
        print(f"✗ token 校验失败: HTTP {e.status} {e.body[:200]}")
        return 3

    cfg["music_user_token"] = token
    cfg["music_user_token_saved_at"] = int(time.time())
    save_config(cfg)
    print(f"✓ 已保存到 {CONFIG_PATH}（此后创建歌单全自动）")
    return 0


def cmd_search(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg, verbose=args.verbose)
    # 必须解析地区。这个子命令的 --storefront 曾经默认写死 "us"，
    # 于是 resolve_storefront 的 explicit 分支永远先命中，配置里记住的
    # 账号地区完全没生效——而 MCP 的 am_search_songs 是解析过的，
    # 于是同一个查询在 CLI 和 MCP 里会得到不同地区的结果。
    sf = resolve_storefront(args.storefront, cfg, dev, get_user_token(cfg))
    st, body = api("GET", f"/catalog/{sf}/search", dev=dev,
                   query={"term": args.term, "types": args.types, "limit": args.limit})
    data = json.loads(body).get("results", {})
    for kind, payload in data.items():
        print(f"\n=== {kind} ===")
        for item in payload.get("data", []):
            a = item.get("attributes", {})
            title = a.get("name")
            extra = a.get("artistName") or a.get("curatorName") or ""
            print(f"  {item['id']:<14} {title}  —  {extra}")
    return 0


def cmd_list(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg)
    user = require_user(cfg)
    st, body = api("GET", "/me/library/playlists", dev=dev, user=user,
                   query={"limit": args.limit})
    for p in json.loads(body).get("data", []):
        a = p.get("attributes", {})
        n = p.get("relationships", {}).get("tracks", {}).get("data")
        print(f"  {p['id']:<22} {a.get('name')}  ({a.get('dateAdded','')[:10]})"
              + (f"  曲目数={len(n)}" if n else ""))
    return 0


def cmd_show(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg)
    user = require_user(cfg)
    p = find_playlist(args.playlist, dev, user)
    if not p:
        print(f"找不到歌单: {args.playlist}")
        return 4
    st, body = api("GET", f"/me/library/playlists/{p['id']}/tracks", dev=dev, user=user,
                   query={"limit": 100})
    for i, t in enumerate(json.loads(body).get("data", []), 1):
        a = t.get("attributes", {})
        print(f"  {i:>3}. {a.get('name')} — {a.get('artistName')}")
    return 0


def cmd_library(args) -> int:
    import am_library as lib

    cfg = load_config()
    dev = get_developer_token(cfg, verbose=args.verbose)
    user = require_user(cfg)
    sf = resolve_storefront(None, cfg, dev, user)
    items = lib.ensure_library_songs(dev, user, sf, refresh=args.refresh,
                                     limit=args.limit, quiet=args.quiet)
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return 0
    print(lib.library_report(items))
    print(f"\n缓存文件：{lib.cache_path()}")
    print("（--refresh 重抓；这份缓存是 build_pool.py 的输入）")
    return 0


def _gather_track_ids(args, dev: str) -> list[str]:
    """把 --tracks / --json 的输入变成有序的 catalog song id 列表。

    每个条目可以是：
      - "歌名 - 艺人"        → 在 catalog 里搜索匹配
      - 纯数字字符串          → 直接当作 catalog song id（钉死版本）
      - {"id": "1440857781"} → 同上，显式写法
      - {"name": "...", "artist": "..."} → 搜索匹配
    钉死的条目和搜索出来的条目会**保持原始顺序**合并。
    """
    ISRC_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{3}\d{7}")

    def pinned(x) -> str | None:
        if isinstance(x, dict) and x.get("id"):
            return str(x["id"])
        if isinstance(x, str) and re.fullmatch(r"\d{6,}", x.strip()):
            return x.strip()
        return None

    def as_query(x) -> str:
        if isinstance(x, dict):
            return f"{x.get('name') or x.get('title') or ''} - {x.get('artist') or ''}".strip(" -")
        return str(x).strip()

    if args.json:
        raw = json.loads(Path(args.json).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            # 兼容几种常见的键名，便于把"带注释的曲目清单"直接喂进来
            for key in ("tracks", "tracks_in_order", "items", "songs"):
                if key in raw:
                    raw = raw[key]
                    break
            else:
                raw = []
        entries = list(raw)
    else:
        entries = [x for x in re.split(r"[,\n;]+", args.tracks or "") if x.strip()]

    if not entries:
        return []

    fixed = [pinned(x) for x in entries]
    queries = [as_query(x) for x in entries if pinned(x) is None]

    resolved: list[str] = []
    if queries:
        isrc_mode = bool(args.isrcs) or all(ISRC_RE.fullmatch(q) for q in queries if q)
        print(f"解析 {len(queries)} 首曲目（storefront={args.storefront}）…")
        resolved, missed = resolve_tracks(queries, dev, args.storefront, isrcs=isrc_mode)
        if missed:
            print(f"  ! 未匹配 {len(missed)} 首: {', '.join(missed[:10])}")
    if any(fixed):
        print(f"（其中 {sum(1 for f in fixed if f)} 首使用指定 ID，跳过搜索）")

    it = iter(resolved)
    out = [f if f else next(it, "") for f in fixed]
    return [i for i in out if i]


def cmd_create(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg, verbose=args.verbose)

    if args.dry_run:                       # 预演只需 catalog 权限，不需要登录
        args.storefront = resolve_storefront(args.storefront, cfg, dev, get_user_token(cfg))
        ids = _gather_track_ids(args, dev)
        print(f"[dry-run] 将创建歌单「{args.name}」并写入 {len(ids)} 首曲目")
        return 0

    user = require_user(cfg)
    args.storefront = resolve_storefront(args.storefront, cfg, dev, user)
    ids = _gather_track_ids(args, dev)

    payload: dict = {"attributes": {"name": args.name}}
    if args.description:
        payload["attributes"]["description"] = args.description
    if args.public:
        payload["attributes"]["isPublic"] = True
    batch, rest = ids[:MAX_TRACKS_PER_REQUEST], ids[MAX_TRACKS_PER_REQUEST:]
    if batch:
        payload["relationships"] = {"tracks": {"data": [{"id": i, "type": "songs"} for i in batch]}}

    st, body = api("POST", "/me/library/playlists", dev=dev, user=user, body=payload)

    # 实测：Apple 有时对创建请求返回 201/204 但**响应体为空**。写入是成功的，
    # 只是没有回显资源；这时按名字回查一次拿 id，否则后续批量追加会没有目标。
    data = json_or_empty(body)
    if data and data.get("data"):
        created = data["data"][0]
        pid = created.get("id")
        name = created.get("attributes", {}).get("name", args.name)
        can_edit = created.get("attributes", {}).get("canEdit")
        print(f"✓ 歌单已创建: {name}  id={pid} (canEdit={can_edit})")
    else:
        print(f"  · 创建返回 HTTP {st} 但响应体为空，按名字回查 id…")
        # 实测：新歌单有 iCloud 传播延迟，立刻回查会查不到（几十秒后才出现）。
        pid = None
        for attempt in range(8):
            found = find_playlist(args.name, dev, user)
            if found:
                pid = found["id"]
                break
            time.sleep(4)
        if pid:
            print(f"✓ 歌单已创建: {args.name}  id={pid}（等了 {attempt*4}s 才同步出来）")
        else:
            print("  · 创建请求已发出，但 30s 内没能回查到。写入很可能已成功，"
                  "稍后自行确认：")
            print(f"      python am_playlist.py show \"{args.name}\"")
            return 0

    for i in range(0, len(rest), MAX_TRACKS_PER_REQUEST):
        chunk = rest[i:i + MAX_TRACKS_PER_REQUEST]
        api("POST", f"/me/library/playlists/{pid}/tracks", dev=dev, user=user,
            body={"data": [{"id": x, "type": "songs"} for x in chunk]})
        print(f"  + 追加 {len(chunk)} 首")

    print(f"共写入 {len(ids)} 首。提示：新歌单在客户端/iCloud 同步可能有几十秒延迟。")
    return 0


def cmd_delete(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg)
    user = require_user(cfg)
    p = find_playlist(args.playlist, dev, user)
    if not p:
        print(f"找不到歌单: {args.playlist}")
        return 4
    name = p.get("attributes", {}).get("name")
    if not args.yes:
        print(f"将删除歌单「{name}」({p['id']}) —— 加 --yes 确认执行")
        return 4
    st, body = api("DELETE", f"/me/library/playlists/{p['id']}", dev=dev, user=user,
                   root=AMP_ROOT)
    if st not in (200, 202, 204):
        # 实测：DELETE 在 api.music.apple.com 上固定返回 401，但在 amp-api 上正常。
        # 万一 amp-api 也不行，再回退到官方主机试一次，并把两个结果都报出来。
        st2, body2 = api("DELETE", f"/me/library/playlists/{p['id']}", dev=dev, user=user)
        if st2 in (200, 202, 204):
            print(f"✓ 已删除歌单「{name}」（HTTP {st2}，经 api.music.apple.com）")
            return 0
        print(f"✗ 删除失败：amp-api → HTTP {st}；api → HTTP {st2}")
        print("  这是 Apple 已知问题（DELETE 在官方主机上返回 401）。替代办法："
              "在 iPhone/Mac/客户端里手动删除，或用 rename 改成占位名。")
        return 1
    print(f"✓ 已删除歌单「{name}」（HTTP {st}）")
    return 0


def cmd_add(args) -> int:
    cfg = load_config()
    dev = get_developer_token(cfg)
    if args.dry_run:                       # 预演只需 catalog 权限，不需要登录
        args.storefront = resolve_storefront(args.storefront, cfg, dev, get_user_token(cfg))
        ids = _gather_track_ids(args, dev)
        print(f"[dry-run] 将向「{args.playlist}」写入 {len(ids)} 首")
        return 0

    user = require_user(cfg)
    args.storefront = resolve_storefront(args.storefront, cfg, dev, user)
    p = find_playlist(args.playlist, dev, user)
    if not p:
        print(f"找不到歌单: {args.playlist}")
        return 4
    ids = _gather_track_ids(args, dev)
    for i in range(0, len(ids), MAX_TRACKS_PER_REQUEST):
        chunk = ids[i:i + MAX_TRACKS_PER_REQUEST]
        api("POST", f"/me/library/playlists/{p['id']}/tracks", dev=dev, user=user,
            body={"data": [{"id": x, "type": "songs"} for x in chunk]})
        print(f"  + 写入 {len(chunk)} 首")
    print(f"✓ 已写入 {p['attributes']['name']}，共 {len(ids)} 首")
    return 0


def cmd_logout(args) -> int:
    """清掉本地保存的令牌（下次要用再 login）。"""
    cfg = load_config()
    had_dev = bool(cfg.get("developer_token"))
    had_user = bool(cfg.get("music_user_token"))
    if not (had_dev or had_user):
        print("本地没有保存任何令牌")
        return 0
    if args.keep_developer:
        cfg.pop("music_user_token", None)
        cfg.pop("music_user_token_saved_at", None)
        print("✓ 已清除 music-user-token（保留 developer token）")
    else:
        cfg = {}
        print("✓ 已清除全部令牌（developer token + music-user-token）")
    save_config(cfg)
    return 0


def cmd_devtoken(args) -> int:
    """用自己的 .p8 生成 developer token 并存起来（有开发者账号时用，配额独立）。"""
    cfg = load_config()
    for k in ("key_path", "key_id", "team_id"):
        if not getattr(args, k):
            raise SystemExit(f"--{k.replace('_','-')} 必填")
    tok = generate_developer_token(args.key_path, args.key_id, args.team_id, args.days)
    cfg["developer_token"] = tok
    cfg["developer_token_source"] = "self"
    save_config(cfg)
    print("✓ 已生成并保存自己的 developer token（有效期 %d 天）" % args.days)
    return 0


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(
        description="全自动创建 Apple Music 歌单",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法")[-1])
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="查看 token 状态"); p.set_defaults(fn=cmd_status)

    p = sub.add_parser("login", help="一次性获取并保存 music-user-token")
    p.add_argument("--token", help="直接提供 media-user-token 值")
    p.add_argument("--from-clipboard", action="store_true",
                   help="从系统剪贴板读取 media-user-token（先在 DevTools 里复制）")
    p.set_defaults(fn=cmd_login)

    p = sub.add_parser("logout", help="清除本地保存的令牌")
    p.add_argument("--keep-developer", action="store_true",
                   help="只清 music-user-token，保留 developer token")
    p.set_defaults(fn=cmd_logout)

    p = sub.add_parser("devtoken", help="用 .p8 生成开发者 token（可选，配额更高）")
    p.add_argument("--key-path", required=True); p.add_argument("--key-id", required=True)
    p.add_argument("--team-id", required=True); p.add_argument("--days", type=int, default=150)
    p.set_defaults(fn=cmd_devtoken)

    p = sub.add_parser("search", help="搜索 catalog")
    p.add_argument("term"); p.add_argument("--types", default="songs")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--storefront", default=None,
                   help="地区码；不给则用配置里记住的，再兜底 us")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("list", help="列出我的歌单")
    p.add_argument("--limit", type=int, default=100); p.set_defaults(fn=cmd_list)

    p = sub.add_parser("library", help="导出我的音乐库（含 ISRC，是 build_pool.py 的输入）")
    p.add_argument("--refresh", action="store_true", help="忽略缓存，重新拉取")
    p.add_argument("--limit", type=int, default=None, help="最多取多少首（默认全部）")
    p.add_argument("--json", action="store_true", help="直接输出 JSON")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_library)

    p = sub.add_parser("show", help="查看歌单曲目")
    p.add_argument("playlist"); p.set_defaults(fn=cmd_show)

    def add_track_args(sp):
        sp.add_argument("--tracks", help="逗号/换行分隔的 '歌名 - 艺人' 列表")
        sp.add_argument("--json", help="JSON 文件：[\"歌名 - 艺人\", ...] 或 [{name,artist},...]")
        sp.add_argument("--isrcs", action="store_true", help="按 ISRC 精确匹配（更快更准）")
        sp.add_argument("--storefront", default=None,
                        help="地区码；不给则用配置里记住的，再兜底 us")
        sp.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("create", help="创建歌单（可一次带上全部曲目）")
    p.add_argument("--name", required=True)
    p.add_argument("--description"); p.add_argument("--public", action="store_true")
    add_track_args(p); p.set_defaults(fn=cmd_create)

    p = sub.add_parser("add", help="向已有歌单添加曲目")
    p.add_argument("--playlist", required=True, help="歌单名或 p.xxxx id")
    add_track_args(p); p.set_defaults(fn=cmd_add)

    p = sub.add_parser("delete", help="删除歌单（清理演示/临时歌单用）")
    p.add_argument("playlist", help="歌单名或 p.xxxx id")
    p.add_argument("--yes", action="store_true", help="确认删除")
    p.set_defaults(fn=cmd_delete)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except NeedLogin:
        print("✗ 还没有登录。先执行一次：\n"
              "    python am_playlist.py login\n"
              "（会自动打开浏览器让你登录 Apple ID，之后创建歌单就全自动了）", file=sys.stderr)
        return 4
    except ApiError as e:
        print(f"\n✗ API 错误: {e}", file=sys.stderr)
        if e.status == 403:
            print("  提示：403 通常是 music-user-token 失效（约 6 个月）→ 重新 login；"
                  "或该歌单不是由本工具创建（Apple 限制只有创建者可写）。", file=sys.stderr)
        if e.status == 429:
            print("  提示：网页 token 的配额是共享的，批量导入请用 devtoken 换成自己的密钥。",
                  file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

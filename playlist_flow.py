#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlist_flow.py — 给歌单做「好听度」体检（BPM / 调性 / 响度 / 能量 / 情绪）

数据链路（全部免费、无需任何密钥）：
    Apple Music 曲目  →  ISRC  →  reccobeats.com /v1/track?ids=<ISRC>  →  UUID
                                →  /v1/audio-features?ids=<UUID>
                                →  tempo, key, mode, loudness, energy, valence,
                                   danceability, acousticness, instrumentalness,
                                   liveness, speechiness

为什么要绕这一圈：**Apple Music 的 catalog API 不提供任何音频特征字段**
（实测字段只有 genreNames/durationInMillis/trackNumber/releaseDate/composerName/
albumName/isrc/artwork...）。而 Spotify 的 audio-features 已于 2024-11-27 对新应用关闭。
ReccoBeats 是当前可用的免费替代，**且直接支持用 ISRC 查询**——ISRC 正好是 Apple 会给的字段。

体检依据（见 调研-怎么做一个好听又有意思的歌单.md）：
  §2.1 不要两首慢歌相邻；不要"只慢一点"（会让慢歌显得拖）
  §2.3 相邻两首不该在 tempo 和 key 上「同时」相似
  §2.4/§3.1 响度前重后轻；valence/arousal/loudness 呈 U 型，tempo 呈倒 U 型
  §3.2 第一首是共识最高、最该单独打磨的位置
  §4   整体弧线形状（man in a hole = 先落再起）

用法：
    python playlist_flow.py "歌单名或 p.xxxx"          # 抓特征（带缓存）+ 体检
    python playlist_flow.py "歌单名" --refresh         # 忽略缓存重抓
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RB = "https://api.reccobeats.com"
CACHE_DIR = Path(__file__).resolve().parent / "refs"

# Spotify 的 key 是 0-11 的半音序号；mode 0=小调 1=大调
PITCH = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CAMELOT_MINOR = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
                 6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}
CAMELOT_MAJOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                 6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}


def camelot(key: int, mode: int) -> str:
    return (CAMELOT_MAJOR if mode == 1 else CAMELOT_MINOR).get(key, "?")


# 速度估计的倍频（octave）歧义是通病：同一首歌可能被估成 90 或 180。
# 把 BPM 折进 [70,160) 再比较，才能判断"两首慢歌""降幅够不够"这类相对关系。
def fold_tempo(bpm: float) -> float:
    if not bpm or bpm <= 0:
        return 0.0
    x = float(bpm)
    while x >= 160:
        x /= 2
    while x < 70:
        x *= 2
    return round(x, 1)


def harmonic_ok(a: str, b: str) -> bool:
    """Camelot 的四种"最容易的移动"：同码 / ±1 同字母 / 同号 A↔B。"""
    if a == "?" or b == "?":
        return False
    na, la = int(a[:-1]), a[-1]
    nb, lb = int(b[:-1]), b[-1]
    if na == nb:
        return True                      # 同码，或同号 A↔B
    if la == lb and abs(na - nb) == 1:
        return True                      # 编号 ±1
    if la == lb and {na, nb} == {1, 12}:
        return True                      # 环形相邻 12A↔1A
    return False


def rb_get(path: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(RB + path,
                                         headers={"User-Agent": am.UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"    ! {path[:60]} → {type(e).__name__}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_features(pid: str, tracks: list[tuple[str, str, str, str]], refresh: bool) -> dict:
    """tracks: [(catalog_id, name, artist, isrc)] → {isrc: features}

    每条特征里会带上 `_cid`（catalog id），这样下游（比如 playlist_optimize.py）
    可以直接按 catalog id 索引，不需要使用者另外手工维护一张 id→ISRC 映射表。
    """
    cache_file = CACHE_DIR / f"features-{pid.replace('.', '_')}.json"
    cache = {}
    if cache_file.exists() and not refresh:
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    todo = [t for t in tracks if t[3] and t[3] not in cache]
    print(f"特征缓存: 已有 {len(cache)} 条，待抓 {len(todo)} 条")
    for i, (cid, name, artist, isrc) in enumerate(todo, 1):
        j = rb_get(f"/v1/track?ids={isrc}")
        c = (j or {}).get("content") or []
        if not c:
            cache[isrc] = {"_miss": True, "_cid": cid, "_name": name}
            print(f"  [{i}/{len(todo)}] ✗ {name[:34]}（ReccoBeats 未收录）")
            time.sleep(0.3)
            continue
        uuid = c[0]["id"]
        f = rb_get(f"/v1/audio-features?ids={uuid}") or {}
        f = f.get("content", [f])[0] if isinstance(f.get("content"), list) else f
        f["_cid"] = cid
        f["_name"] = name
        f["_artist"] = artist
        f["_reccobeats_title"] = c[0].get("trackTitle")
        cache[isrc] = f
        print(f"  [{i}/{len(todo)}] ✓ {name[:30]:<32} {f.get('tempo',0):6.1f}BPM "
              f"{camelot(f.get('key',0), f.get('mode',0)):>4}  "
              f"E={f.get('energy',0):.2f} V={f.get('valence',0):.2f}")
        time.sleep(0.3)

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def norm(vals: list[float]) -> list[float]:
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


def analyze(rows: list[dict]) -> None:
    n = len(rows)
    print(f"\n{'='*100}\n好听度体检（{n} 首有特征的曲目）\n{'='*100}")

    print(f"\n{'#':>3} {'曲目':<30} {'BPM':>6} {'≈':>6} {'调':>5} {'响度':>7} {'energy':>7} {'valence':>8} {'时长':>6}")
    for i, r in enumerate(rows, 1):
        f = r["f"]
        raw = f.get("tempo", 0)
        fd = fold_tempo(raw)
        mark = "*" if abs(fd - raw) > 0.5 else " "
        print(f"{i:>3} {str(r['name'])[:28]:<30} {raw:6.1f}{mark}{fd:6.1f} "
              f"{camelot(f.get('key',0), f.get('mode',0)):>5} {f.get('loudness',0):7.1f} "
              f"{f.get('energy',0):7.2f} {f.get('valence',0):8.2f} "
              f"{r['dur_ms']//1000//60}:{r['dur_ms']//1000%60:02d}")
    print("     （* = 原始值被折半/加倍过。BPM 估计的倍频歧义是通病，")
    print("       '≈' 列是折进 [70,160) 后的值，下面的相邻分析用它比较）")

    tempo = [fold_tempo(r["f"].get("tempo", 0)) for r in rows]
    energy = [r["f"].get("energy", 0) for r in rows]
    valence = [r["f"].get("valence", 0) for r in rows]
    loud = [r["f"].get("loudness", -60) for r in rows]
    keys = [camelot(r["f"].get("key", 0), r["f"].get("mode", 0)) for r in rows]

    # ---------- 1. 弧线：跟 PLOS 的 U 型/倒U 对比 ----------
    print(f"\n【1】整体弧线（PLOS 2025：valence/energy/loudness 应为 U 型，tempo 应为倒 U 型）")
    print("     位置分五段，段内取均值（z 化后）")

    def seg(vals):
        k = max(1, len(vals) // 5)
        segs = [vals[i:i + k] for i in range(0, len(vals), k)][:5]
        return [round(statistics.mean(s), 3) for s in segs if s]

    for label, vals, want in [("valence", valence, "U（两端高）"), ("energy", energy, "U（两端高）"),
                              ("loudness", loud, "U（两端高）"), ("tempo", tempo, "倒U（中间高）")]:
        z = norm(vals)
        s = seg(z)
        head = "█" * max(0, int(s[0] * 20))
        mid = "█" * max(0, int(s[len(s)//2] * 20))
        tail = "█" * max(0, int(s[-1] * 20))
        print(f"     {label:<9} 首{head:<21} 中{mid:<21} 末{tail:<21}  期望: {want}")

    # ---------- 2. 首尾（PLOS：首尾都该高 valence/arousal；首 tempo 低） ----------
    print(f"\n【2】首尾（PLOS：开场与收尾都高 valence/arousal；开场 tempo 偏低）")
    print(f"     首曲 {rows[0]['name'][:34]:<36} BPM={tempo[0]:6.1f} E={energy[0]:.2f} V={valence[0]:.2f}")
    print(f"     末曲 {rows[-1]['name'][:34]:<36} BPM={tempo[-1]:6.1f} E={energy[-1]:.2f} V={valence[-1]:.2f}")
    print(f"     全曲中位 BPM={statistics.median(tempo):.1f}  V={statistics.median(valence):.2f}")

    # ---------- 3. 相邻衔接检查 ----------
    print(f"\n【3】相邻衔接（§2.1 / §2.3）")
    problems = {"two_slow": [], "small_drop": [], "both_similar": [], "big_jump": []}
    bpm_med = statistics.median(tempo)
    slow_cut = min(100.0, statistics.quantiles(tempo, n=4)[0] if len(tempo) >= 4 else 100.0)
    for i in range(n - 1):
        a, b = rows[i], rows[i + 1]
        ta, tb = tempo[i], tempo[i + 1]
        ka, kb = keys[i], keys[i + 1]
        ea, eb = energy[i], energy[i + 1]
        pct = (tb - ta) / ta * 100 if ta else 0
        if ta < slow_cut and tb < slow_cut:
            problems["two_slow"].append((i + 1, a["name"], b["name"], ta, tb))
        if ta > tb and 0 < -pct < 12:      # 变慢了，但降幅不到 12% → "只慢一点"
            problems["small_drop"].append((i + 1, a["name"], b["name"], ta, tb, -pct))
        if abs(pct) < 6 and harmonic_ok(ka, kb):
            problems["both_similar"].append((i + 1, a["name"], b["name"], ta, tb, ka, kb))
        if abs(ea - eb) > 0.35 and not harmonic_ok(ka, kb):
            problems["big_jump"].append((i + 1, a["name"], b["name"], ea, eb, ka, kb))

    def show(tag, items, fmt):
        if not items:
            print(f"     ✅ {tag}：无")
            return
        print(f"     ⚠️  {tag}：{len(items)} 处（共 {n-1} 个衔接）")
        for it in items:
            print("          " + fmt(it))

    show(f"两首慢歌相邻（§2.1 明确禁止；阈值 {slow_cut:.0f}BPM）", problems["two_slow"],
         lambda x: f"#{x[0]}→#{x[0]+1}  {x[1][:22]} ({x[3]:.0f}BPM) → {x[2][:22]} ({x[4]:.0f}BPM)")
    show("「只慢一点」（降幅<12%，会让慢歌显得拖）", problems["small_drop"],
         lambda x: f"#{x[0]}→#{x[0]+1}  {x[1][:20]} {x[3]:.0f}→{x[4]:.0f}BPM（降 {x[5]:.0f}%）")
    show("相邻在 tempo 和 key 上同时相似（§2.3）", problems["both_similar"],
         lambda x: f"#{x[0]}→#{x[0]+1}  {x[1][:20]} {x[3]:.0f}→{x[4]:.0f}BPM {x[5]}→{x[6]}")
    show("能量骤变且调性不兼容（突兀）", problems["big_jump"],
         lambda x: f"#{x[0]}→#{x[0]+1}  {x[1][:20]} E {x[3]:.2f}→{x[4]:.2f} ({x[5]}→{x[6]})")

    # ---------- 4. 形状 ----------
    print(f"\n【4】弧线形状（§4：六种叙事弧）")
    v0, vmid, v1 = statistics.mean(valence[:max(1, n//3)]), \
                   statistics.mean(valence[n//3:2*n//3] or [0]), \
                   statistics.mean(valence[2*n//3:])
    shape = "Man in a hole（落-起）" if vmid < v0 and v1 > vmid else \
            "Icarus（起-落）" if vmid > v0 and v1 < vmid else \
            "Rags to riches（持续上升）" if v1 > v0 > vmid else \
            "Tragedy（持续下降）" if v1 < vmid < v0 else "混合/无明确形状"
    print(f"     valence 三段均值：首 {v0:.3f} → 中 {vmid:.3f} → 末 {v1:.3f}")
    print(f"     识别出的形状：**{shape}**")
    print(f"     （PLOS 发现专业人排专辑偏向 Man in a hole）")

    # ---------- 5. 调性分布 ----------
    print(f"\n【5】调性分布（Camelot）")
    from collections import Counter
    for k, c in Counter(keys).most_common(8):
        print(f"     {k:>4}  {c:>2} 首")


def run(target: str, refresh: bool = False) -> int:
    """给一个歌单名/ID：抓特征（带缓存）并打印体检报告。返回退出码。"""
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)

    p = am.find_playlist(target, dev, user)
    if not p:
        print(f"找不到歌单: {target}")
        return 4
    pid = p["id"]
    print(f"歌单：{p['attributes'].get('name')}  id={pid}")

    st, body = am.api("GET", f"/me/library/playlists/{pid}/tracks", dev=dev, user=user,
                      query={"limit": 100})
    lib = json.loads(body).get("data", [])
    cat_ids, dur = [], {}
    for t in lib:
        a = t.get("attributes", {})
        cid = (a.get("playParams") or {}).get("catalogId") or (a.get("playParams") or {}).get("id")
        if cid:
            cat_ids.append(str(cid))
            dur[str(cid)] = a.get("durationInMillis", 0)

    meta = {}
    for i in range(0, len(cat_ids), 100):
        st, body = am.api("GET", "/catalog/cn/songs", dev=dev,
                          query={"ids": ",".join(cat_ids[i:i + 100])})
        for s in json.loads(body).get("data", []):
            meta[s["id"]] = s["attributes"]

    tracks = [(c,
               meta.get(c, {}).get("name") or f"id:{c}",
               meta.get(c, {}).get("artistName") or "?",
               meta.get(c, {}).get("isrc"))
              for c in cat_ids if c in meta]

    feats = fetch_features(pid, tracks, refresh)

    rows = []
    for cid, name, artist, isrc in tracks:
        f = feats.get(isrc or "")
        if not f or f.get("_miss") or "tempo" not in f:
            continue
        rows.append({"cid": cid, "name": name, "artist": artist, "f": f, "dur_ms": dur.get(cid, 0)})

    miss = len(tracks) - len(rows)
    if miss:
        print(f"\n⚠️ {miss} 首没有特征，已从下面的分析中排除")
    if len(rows) < 3:
        print("有效曲目太少，无法分析")
        return 1
    analyze(rows)
    return 0


def flow_report(target: str, refresh: bool = False) -> str:
    """跑体检并把报告当字符串返回（供 MCP 服务 / 其他脚本调用）。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            run(target, refresh)
        except am.NeedLogin:
            return "尚未登录 Apple Music：请先在终端运行 python am_playlist.py login"
        except am.ApiError as e:
            return f"API 错误 HTTP {e.status}: {e.body[:300]}"
    return buf.getvalue().strip() or "（体检没有输出）"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    return run(args[0], "--refresh" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())

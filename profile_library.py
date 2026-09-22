#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
profile_library.py — 给你最常听的歌做「声音画像」

思路：不看流派标签，直接抓音频特征，找出一批歌**共同的声音特征**，
再据此命名一个主题。这比"按流派抓歌"更能反映真实听感。

数据来源：
  · 播放次数 → /me/music-summaries/<period>/view/top-songs
  · 音频特征 → ISRC → ReccoBeats（见 playlist_flow.py）
  · 是否在库 → /me/library/songs

用法：
    python profile_library.py [--year 2026] [--top 60]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402
import playlist_flow as pf  # noqa: E402
from am_meta import catalog_meta  # noqa: E402

ROOT = Path(__file__).resolve().parent
REF = ROOT / "refs"


def replay_top(period: str, dev: str, user: str, want: int) -> list[dict]:
    """取播放次数排行，返回 [{cid, plays}]。一次最多 50 条/页。"""
    out, off = [], 0
    while len(out) < want:
        st, body = am.api("GET", f"/me/music-summaries/{period}/view/top-songs",
                          dev=dev, user=user, root=am.AMP_ROOT,
                          query={"limit": 50, "offset": off})
        j = json.loads(body)
        page = j.get("data", [])
        if not page:
            break
        for x in page:
            a = x.get("attributes", {})
            rel = ((x.get("relationships") or {}).get("song") or {}).get("data") or []
            if rel:
                out.append({"cid": rel[0].get("id"), "plays": a.get("playCount"),
                            "first": str(a.get("firstPlayed"))[:10],
                            "last": str(a.get("lastPlayed"))[:10]})
        off += len(page)
        if not j.get("next"):
            break
    return out[:want]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    sf = am.resolve_storefront(None, cfg, dev, user)

    cache_f = REF / f"profile-{a.year}.json"
    if cache_f.exists() and not a.refresh:
        prof = json.loads(cache_f.read_text(encoding="utf-8"))
        print(f"读缓存 {cache_f.name}（{len(prof)} 条）—— 加 --refresh 可重抓")
        return report(prof)

    print(f"取 {a.year} 播放次数 Top {a.top} …")
    tops = replay_top(f"year-{a.year}", dev, user, a.top)
    ids = [t["cid"] for t in tops if t["cid"]]
    print(f"  拿到 {len(ids)} 个 catalog id，批量查元数据（拿 ISRC）…")
    meta = catalog_meta(ids, dev, sf)

    prof = []
    for i, t in enumerate(tops, 1):
        m = meta.get(t["cid"])
        if not m or not m.get("isrc"):
            prof.append({**t, "_miss": "no-isrc"})
            continue
        j = pf.rb_get(f"/v1/track?ids={m['isrc']}")
        c = (j or {}).get("content") or []
        if not c:
            prof.append({**t, "name": m.get("name"), "artist": m.get("artistName"),
                         "isrc": m.get("isrc"), "_miss": "reccobeats"})
            continue
        f = pf.rb_get(f"/v1/audio-features?ids={c[0]['id']}") or {}
        f = f.get("content", [f])[0] if isinstance(f.get("content"), list) else f
        f.update({**t, "name": m.get("name"), "artist": m.get("artistName"),
                  "album": m.get("albumName"), "isrc": m.get("isrc"),
                  "year": (m.get("releaseDate") or "")[:4], "genre": m.get("genreNames")})
        prof.append(f)
        if i % 15 == 0:
            print(f"  …{i}/{len(tops)}")
        time.sleep(0.3)

    REF.mkdir(exist_ok=True)
    cache_f.write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已存 {cache_f.name}\n")
    return report(prof)


def report(prof: list[dict]) -> int:
    ok = [p for p in prof if "tempo" in p]
    miss = [p for p in prof if p.get("_miss")]
    print(f"=== 样本 {len(prof)} 首（有特征 {len(ok)}，缺 {len(miss)}）===")

    print("\n── 声音画像（中位数）")
    for k, label in [("tempo", "BPM（已折叠）"), ("energy", "能量"), ("valence", "愉悦度"),
                     ("loudness", "响度 dB"), ("danceability", "舞动度"),
                     ("acousticness", "原声度"), ("instrumentalness", "器乐度")]:
        if k == "tempo":
            v = [pf.fold_tempo(p["tempo"]) for p in ok if p.get("tempo")]
        else:
            v = [p[k] for p in ok if p.get(k) is not None]
        if v:
            print(f"   {label:<12} 中位 {statistics.median(v):8.3f}    范围 {min(v):.3f} ~ {max(v):.3f}")

    if ok:
        minor = sum(1 for p in ok if p.get("mode") == 0)
        print(f"   {'小调占比':<12} {minor}/{len(ok)} = {minor/len(ok)*100:.0f}%")
        print(f"   {'Camelot Top6':<12} {Counter(pf.camelot(p.get('key',0), p.get('mode',0)) for p in ok).most_common(6)}")

    print("\n── 艺人分布")
    for ar, c in Counter(p.get("artist") for p in prof if p.get("artist")).most_common(12):
        tot = sum(p.get("plays") or 0 for p in prof if p.get("artist") == ar)
        print(f"   {c:>3} 首 / {tot:>5} 次   {ar}")

    print("\n── 年代分布")
    for y, c in sorted(Counter(p.get("year") for p in prof if p.get("year")).items()):
        print(f"   {y}  {c:>3}")

    # 情绪四象限
    if ok:
        print("\n── 情绪四象限（valence × energy，各以中位为界）")
        vm = statistics.median([p["valence"] for p in ok])
        em = statistics.median([p["energy"] for p in ok])
        q = Counter()
        for p in ok:
            q[(p["valence"] >= vm, p["energy"] >= em)] += 1
        for (hv, he), c in sorted(q.items(), key=lambda x: -x[1]):
            tag = ("高愉悦" if hv else "低愉悦") + " + " + ("高能量" if he else "低能量")
            print(f"   {tag:<18} {c:>3} 首  {'█' * c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pool.py — 从音乐库里挑出候选池并抓音频特征

候选池的优先级（都限定在**用户自己的音乐库**内）：
  1. Replay 播放次数最高的那些（已知最爱）
  2. 最爱艺人名下的其他库内曲目（横向铺开）
  3. 库内其他簇的代表曲（保证"材料够杂"）

输出 refs/pool-<tag>.json，含每首的特征，供选曲与排序使用。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402
import playlist_flow as pf  # noqa: E402

ROOT = Path(__file__).resolve().parent
REF = ROOT / "refs"

TAG = sys.argv[1] if len(sys.argv) > 1 else "dayarc"
CAP = int(sys.argv[2]) if len(sys.argv) > 2 else 130

cfg = am.load_config()
dev = am.get_developer_token(cfg)
user = am.require_user(cfg)
sf = am.resolve_storefront(None, cfg, dev, user)

lib = json.load(open(REF / "library-songs.json", encoding="utf-8"))
lib = [s for s in lib if s.get("cid")]
print(f"库内可用曲目: {len(lib)}")

# 最爱艺人（按 Replay 播放次数聚合）
prof = json.load(open(REF / "profile-2026.json", encoding="utf-8"))
plays = Counter()
for p in prof:
    if p.get("artist"):
        plays[p["artist"]] += p.get("plays") or 0
top_artists = [a for a, _ in plays.most_common(18)]
print("最爱艺人 Top:", ", ".join(f"{a}({c})" for a, c in plays.most_common(10)))
top_cids = {p["cid"] for p in prof if p.get("cid")}

picked: list[dict] = []
seen: set[str] = set()

# ① 最爱听的那些
for p in sorted(prof, key=lambda x: -(x.get("plays") or 0)):
    if p.get("cid") and p["cid"] not in seen:
        picked.append({"cid": p["cid"], "name": p.get("name"), "artist": p.get("artist"),
                       "plays": p.get("plays"), "why": "top-played"})
        seen.add(p["cid"])

# ② 最爱艺人名下的其他库内曲
by_artist = defaultdict(list)
for s in lib:
    if s["artist"] in top_artists and s["cid"] not in seen:
        by_artist[s["artist"]].append(s)
per = max(3, (CAP - len(picked)) // max(1, len(top_artists)) // 2)
for a in top_artists:
    for s in by_artist[a][:per]:
        if s["cid"] in seen:
            continue
        picked.append({"cid": s["cid"], "name": s["name"], "artist": s["artist"],
                       "plays": 0, "why": f"artist:{a}"})
        seen.add(s["cid"])

# ③ 其它簇（不同语种/年代），保证"杂"
others = [s for s in lib if s["cid"] not in seen and s["artist"] not in top_artists]
others.sort(key=lambda s: (s["artist"] or "", s["year"] or ""))
step = max(1, len(others) // max(1, CAP - len(picked)))
for s in others[::step][: CAP - len(picked)]:
    picked.append({"cid": s["cid"], "name": s["name"], "artist": s["artist"],
                   "plays": 0, "why": "filler"})
    seen.add(s["cid"])

picked = picked[:CAP]
print(f"候选池: {len(picked)} 首")
print("  来源分布:", Counter(p["why"].split(":")[0] for p in picked))

# 批量取 ISRC
ids = [p["cid"] for p in picked]
meta = {}
for i in range(0, len(ids), 100):
    st, body = am.api("GET", f"/catalog/{sf}/songs", dev=dev,
                      query={"ids": ",".join(ids[i:i + 100])})
    for s in json.loads(body).get("data", []):
        meta[s["id"]] = s["attributes"]
print(f"  拿到元数据 {len(meta)}/{len(ids)}")

tracks = []
for p in picked:
    m = meta.get(p["cid"], {})
    if m.get("isrc"):
        p["isrc"] = m["isrc"]
        p["year"] = (m.get("releaseDate") or "")[:4]
        p["genre"] = m.get("genreNames")
        tracks.append((p["cid"], m.get("name") or p["name"], m.get("artistName") or p["artist"],
                       m["isrc"]))

print("抓音频特征（有缓存则跳过）…")
feats = pf.fetch_features(f"pool-{TAG}", tracks, refresh=False)

out = []
for p in picked:
    f = feats.get(p.get("isrc") or "")
    if f and "tempo" in f:
        p["f"] = f
        out.append(p)
REF.mkdir(exist_ok=True)
(REF / f"pool-{TAG}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
print(f"\n候选池落盘: {len(out)}/{len(picked)} 首有特征 → refs/pool-{TAG}.json")

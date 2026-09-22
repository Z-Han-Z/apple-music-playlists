#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_day_playlist.py — 用音乐库做一个「一日」主题歌单

主题：**一日 — 24 時間**
形状：**Cinderella（起–落–起）**——一天本身就是先升（夜明け→真昼）、
      再落（夕暮れ→夜）、最后回升（また夜明け）。硬套 man-in-a-hole 会与概念矛盾。

六段（按你库里歌曲自带的「时间」意象划分，全部取自你自己的音乐库）：
  ① 夜明け前  ② 朝  ③ 真昼  ④ 夕暮れ  ⑤ 夜（谷底）  ⑥ そしてまた朝へ
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402

ROOT = Path(__file__).resolve().parent
REF = ROOT / "refs"

# ── 选曲（按曲名指定，脚本再从候选池里解析成 catalog id）────────────────────
# 每段都优先取"你实际听得多的"，并用库里其他艺人补足"杂"
PICKS = {
    "A": {
        "title": "① 夜明け前 — まだ誰も起きていない",
        "note": "低能量、低愉悦；一天的起点，也是全曲最安静的地方",
        "songs": ["夜更かし", "Introduction", "夜の探検", "K歌之王", "陀飞轮",
                  "Blues-Ette", "Break it Down (Elp Version)"],
    },
    "B": {
        "title": "② 朝 — 始発に乗る",
        "note": "回升。曲线开始往上走（Cinderella 的第一段上升）",
        "songs": ["始発とカフカ", "A.M.3:21", "転がる岩、君に朝が降る", "Sunny",
                  "晴るる", "music for you", "Once You Get A Taste"],
    },
    "C": {
        "title": "③ 真昼 — 一日でいちばん明るいところ",
        "note": "峰值：高愉悦 + 高能量",
        "songs": ["Absolute Ego Dance", "Mirror Tune", "猫リセット", "花一匁", "海胆",
                  "Campus Mode!!", "だから僕は音楽を辞めた", "恋愛裁判", "Get Lucky"],
    },
    "D": {
        "title": "④ 夕暮れ — 傾きはじめる",
        "note": "转折点。亮度还在，能量开始掉",
        "songs": ["Setting Sun", "月 feat. ヰ世界情緒", "八月、某、月明かり",
                  "Moon's Temperature", "夏霞", "また夏を追う", "八月のif"],
    },
    "E": {
        "title": "⑤ 夜 — 一日でいちばん暗いところ",
        "note": "谷底。库里 valence 最低的一批（0.12–0.46）",
        "songs": ["MEDAL SUZDAL PANIC◎○●", "淘汰", "浮夸", "あの夏が飽和する",
                  "礎の花冠", "花びらたちのマーチ", "輪廻 (feat. 花譜, 理芽, 春猿火, ヰ世界情緒 & 幸祜)",
                  "嘘つき", "your trip"],
    },
    "F": {
        "title": "⑥ そしてまた朝へ",
        "note": "回升。收在明亮处——呼应开头的 04:00",
        "songs": ["街路、ライトの灯りだけ", "Madder", "line", "music (feat. LINION)",
                  "Martian", "Price (Another Version)"],
    },
}


def main() -> int:
    pool = json.load(open(REF / "pool-dayarc.json", encoding="utf-8"))
    by_name: dict[str, dict] = {}
    for p in pool:
        key = (p["name"] or "").strip().lower()
        # 同名保留播放次数高的那个
        if key not in by_name or (p.get("plays") or 0) > (by_name[key].get("plays") or 0):
            by_name[key] = p

    def lookup(nm: str) -> dict | None:
        """先精确匹配，再允许候选池里的名字多带后缀（如 '(feat. KAF)'、'(Cover)'）。"""
        k = nm.strip().lower()
        if k in by_name:
            return by_name[k]
        for cand_key, p in by_name.items():
            if cand_key.startswith(k):
                return p
        return None

    blocks, order, missing = [], [], []
    for bid, spec in PICKS.items():
        ids = []
        for nm in spec["songs"]:
            p = lookup(nm)
            if not p:
                missing.append(f"{bid}:{nm}")
                continue
            ids.append(p["cid"])
            order.append(p)
        blocks.append({"id": bid, "title": spec["title"], "tracks": ids})

    if missing:
        print("⚠️ 候选池里没找到（可能没特征或被去重）:")
        for m in missing:
            print("   ", m)
    print(f"\n选曲 {sum(len(b['tracks']) for b in blocks)} 首，分 {len(blocks)} 段")

    spec_file = REF / "day-blocks.json"
    spec_file.write_text(json.dumps({"_theme": "一日 — 24 時間", "blocks": blocks},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"分段清单 → {spec_file.name}")

    print("\n段内分布（valance / energy 均值）:")
    for b in blocks:
        rows = [p for p in order if p["cid"] in b["tracks"]]
        v = sum(p["f"]["valence"] for p in rows) / max(1, len(rows))
        e = sum(p["f"]["energy"] for p in rows) / max(1, len(rows))
        print(f"   {b['id']}  {b['title'][:26]:<28} {len(rows):>2} 首   V={v:.2f}  E={e:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

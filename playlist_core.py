#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlist_core.py — 与音乐平台**无关**的乐理与相邻规则。

这个模块不 import 任何平台相关代码（连 am_paths 都不需要）。它单独存在的理由
是一个具体的 bug：

    **同一个概念在体检器和优化器里被定义成了两套。**

      · playlist_flow.analyze   把"慢歌"定义为 tempo 的 25 分位（且不超过 100）
      · playlist_optimize       把"慢歌"定义为固定 < 100

  于是工具用一套定义**诊断**问题、用另一套定义**修复**问题。实测那张歌单时
  这个不一致直接让结论含糊：体检说"2 处两首慢歌相邻"，而优化器压根没在最小化
  同一个量——所以"不可避免"的说法当时是靠不住的。

另外还有一处不对称：优化器惩罚 BPM 大跳（>40%），而体检器**从来没有检查过**
这一项。于是它能被优化、却不会被报告。

定义只能有一份，就在这里。将来接第二个音乐平台时，这一层必须逐字保持不变——
它是"好听"判断的全部依据。
"""

from __future__ import annotations

import statistics

# ---------------------------------------------------------------- 调性 / 速度

# Spotify/ReccoBeats 的 key 是 0-11 的半音序号；mode 0=小调 1=大调
PITCH = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CAMELOT_MINOR = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
                 6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}
CAMELOT_MAJOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                 6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}

# 折叠区间。注意它宽于一个八度（160/70 ≈ 2.29），这是**有意的**：
# 收成真正的八度（如 [80,160)）会让 70~79 BPM 的歌被折到 140~158，
# 于是真正慢的歌会被判成快的——而"两首慢歌相邻"这条规则恰恰依赖它们留在慢区间。
FOLD_LO, FOLD_HI = 70.0, 160.0


def camelot(key: int, mode: int) -> str:
    return (CAMELOT_MAJOR if mode == 1 else CAMELOT_MINOR).get(key, "?")


def fold_tempo(bpm: float) -> float:
    """把 BPM 折进 [70,160)。

    速度估计的倍频歧义是通病：同一首歌可能被估成 90 或 180。不折叠的话
    "两首慢歌相邻"会误报约 4 倍。
    """
    if not bpm or bpm <= 0:
        return 0.0
    x = float(bpm)
    while x >= FOLD_HI:
        x /= 2
    while x < FOLD_LO:
        x *= 2
    return round(x, 1)


def harmonic_ok(a: str, b: str) -> bool:
    """Camelot 的四种"最容易的移动"：同码 / ±1 同字母 / 同号 A↔B / 环形相邻。"""
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


def norm(vals: list[float]) -> list[float]:
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


# ---------------------------------------------------------------- 相邻规则
#
# ⚠️ 这一节是四条硬性相邻规则的**唯一**定义处。
# 体检器（playlist_flow）和优化器（playlist_optimize）都必须走 check_pair()。
# 各自再写一遍，就等于又埋了一次"诊断和修复不同标准"的坑。

SLOW_BPM = 100.0        # "慢歌"的绝对阈值
SMALL_DROP_PCT = 12.0   # 降幅在这个区间内 = "只慢一点"，会让慢歌显得拖
SIMILAR_PCT = 6.0       # 节奏差异小于这个 = "几乎一样"
BIG_JUMP_PCT = 40.0     # BPM 无理由大跳
ENERGY_CLASH = 0.35     # 能量骤变

RULES = ("two_slow", "small_drop", "both_similar", "big_jump", "energy_clash")

RULE_LABELS = {
    "two_slow": f"两首慢歌相邻（都 < {SLOW_BPM:.0f}BPM）",
    "small_drop": f"只慢一点（降幅 < {SMALL_DROP_PCT:.0f}%，会让慢歌显得拖）",
    "both_similar": f"相邻在 tempo 和 key 上同时相似（§2.3）",
    "big_jump": f"BPM 无理由大跳（>{BIG_JUMP_PCT:.0f}%）",
    "energy_clash": "能量骤变且调性不兼容（突兀）",
}


def slow_cut(tempos=None) -> float:
    """多慢算"慢歌"。

    刻意用**绝对阈值**而不是分位数：优化器要在退火过程中反复求值同一序列，
    分位数会随当前排列漂移，使 cost 不稳定，退火就收敛不到确定结果。
    绝对阈值同时也更好解释。

    代价要说清楚：一张整体都是慢歌的歌单，会把每一对相邻都标成 two_slow。
    那**是真实的**（确实一路慢下去），但别把它当成排序失败。
    """
    return SLOW_BPM


def check_pair(a: dict | None, b: dict | None) -> set[str]:
    """检查一对相邻曲目踩了哪些规则，返回规则名集合。

    a/b 需要 {"bpm": 折叠后的 BPM, "key": Camelot 码, "energy": 0..1}。
    任一为 None 或缺 BPM 时返回空集——没有特征就不该凭空惩罚。
    """
    if not a or not b:
        return set()
    ta, tb = a.get("bpm") or 0.0, b.get("bpm") or 0.0
    if not ta or not tb:
        return set()
    ka, kb = a.get("key") or "?", b.get("key") or "?"
    ea, eb = a.get("energy") or 0.0, b.get("energy") or 0.0
    pct = (tb - ta) / ta * 100

    bad: set[str] = set()
    if ta < SLOW_BPM and tb < SLOW_BPM:
        bad.add("two_slow")
    if ta > tb and 0 < -pct < SMALL_DROP_PCT:
        bad.add("small_drop")
    if abs(pct) < SIMILAR_PCT and harmonic_ok(ka, kb):
        bad.add("both_similar")
    if abs(pct) > BIG_JUMP_PCT:
        bad.add("big_jump")
    if abs(ea - eb) > ENERGY_CLASH and not harmonic_ok(ka, kb):
        bad.add("energy_clash")
    return bad


def scan_adjacency(tracks: list[dict]) -> dict[str, list[tuple[int, dict]]]:
    """扫一遍整条序列，返回每个规则命中的位置：{规则: [(序号, 详情), ...]}。

    序号是 1-based 的**后一首**位置（"第 i 首→第 i+1 首"里的 i+1），
    跟报告里的写法一致。
    """
    found: dict[str, list[tuple[int, dict]]] = {r: [] for r in RULES}
    for i in range(len(tracks) - 1):
        a, b = tracks[i], tracks[i + 1]
        ta, tb = a.get("bpm") or 0.0, b.get("bpm") or 0.0
        pct = (tb - ta) / ta * 100 if ta else 0.0
        detail = {"a": a, "b": b, "pct": pct}
        for r in check_pair(a, b):
            found[r].append((i + 2, detail))
    return found


# ---------------------------------------------------------------- 叙事弧
#
# 六种基本情感弧（Vonnegut → Reagan et al. 2016 实证）。
# 5 点，0=最低 1=最高；每条都已归一化到 [0,1]，
# 否则和 norm() 之后的实际曲线比 MSE 会不公平。
ARCHETYPES = {
    "Rags to riches（持续上升）": [0.0, 0.25, 0.5, 0.75, 1.0],
    "Tragedy（持续下降）": [1.0, 0.75, 0.5, 0.25, 0.0],
    "Man in a hole（落-起）": [0.70, 0.20, 0.0, 0.35, 1.0],
    "Icarus（起-落）": [0.0, 0.60, 1.0, 0.50, 0.0],
    "Cinderella（起-落-起）": [0.0, 0.70, 1.0, 0.30, 1.0],
    "Oedipus（落-起-落）": [1.0, 0.30, 0.80, 0.20, 0.0],
}


def classify_shape(vals: list[float]) -> tuple[str, list[float], dict[str, float]]:
    """把曲线的 5 段均值与六种叙事弧比 MSE，返回 (最佳形状, 段均值, 各形状得分)。

    切成 **5** 段而不是 3 段：3 段看不出谷底加回升，会把"起-落-起"的
    Cinderella 误判成 Icarus（实测踩过这一条）。

    ⚠️ 这是启发式：段数少、曲线平缓、或曲子构成复合弧时会误判。
    所以调用方应该把段均值一起打出来，让人自己判断。
    """
    k = 5
    step = max(1, len(vals) // k)
    segs = [statistics.mean(vals[i * step:(i + 1) * step]) for i in range(k)]
    z = norm(segs)
    scores = {
        name: sum((a - b) ** 2 for a, b in zip(z, ideal)) / k
        for name, ideal in ARCHETYPES.items()
    }
    best = min(scores, key=scores.get)
    return best, segs, scores


# ---------------------------------------------------------------- 目标形状
#
# 上面是"认出你排出来的是什么形状"，这里是"朝着哪个形状排"。
# 两者共用 ARCHETYPES 这**一份**曲线定义，这是刻意的：
# 以前"选形状"只停在诊断层，优化器永远朝 man-in-a-hole 走，
# 而策划文档把"先选一个形状"列为第一步——工具没兑现它自己写的流程。

DEFAULT_SHAPE = "man-in-a-hole"

# 文档与命令行里用的短名 → ARCHETYPES 的键
SHAPE_ALIASES = {
    "rags-to-riches": "Rags to riches（持续上升）",
    "tragedy": "Tragedy（持续下降）",
    "man-in-a-hole": "Man in a hole（落-起）",
    "icarus": "Icarus（起-落）",
    "cinderella": "Cinderella（起-落-起）",
    "oedipus": "Oedipus（落-起-落）",
}


def resolve_shape(name: str) -> str:
    """把短名（`cinderella`）或完整键名解析成 ARCHETYPES 的键。"""
    if name in ARCHETYPES:
        return name
    key = SHAPE_ALIASES.get((name or "").strip().lower())
    if key is None:
        raise ValueError(f"未知形状 {name!r}。可选：" + "、".join(SHAPE_ALIASES))
    return key


def shape_target(name: str, n: int) -> list[float]:
    """把 5 点的理想曲线线性插值成 n 个点的目标序列。"""
    ideal = ARCHETYPES[resolve_shape(name)]
    if n <= 0:
        return []
    if n == 1:
        return [ideal[0]]
    out = []
    last = len(ideal) - 1
    for i in range(n):
        pos = i * last / (n - 1)
        lo = int(pos)
        hi = min(lo + 1, last)
        frac = pos - lo
        out.append(ideal[lo] * (1 - frac) + ideal[hi] * frac)
    return out


def tempo_target(n: int) -> list[float]:
    """tempo 的目标：倒 U（快的放中段）。

    **刻意不随情感形状变。** 叙事弧描述的是情绪走向（valence / energy /
    loudness），而"快的放中段"是排序惯例，两者不是一回事。让 tempo 也跟着
    Cinderella 起落起，等于把两个独立的原则搅成一个。
    """
    if n <= 0:
        return []
    if n == 1:
        return [0.5]
    return [1.0 - abs(i / (n - 1) - 0.5) * 2 for i in range(n)]


# ---------------------------------------------------------------- 特征覆盖漏斗
#
# 为什么这一节存在：**"有多少曲目能拿到音频特征"是决定整个工具能力的数字。**
# 相邻规则和弧线只能作用在有特征的曲目上；覆盖率掉到 60%，排出来的顺序
# 就有四成位置没被评估过，而报告里的 cost 数字会**看起来很好**。
#
# 以前这件事散落在几处 `continue` 里，而且被压成一个笼统的 miss：
#   · playlist_flow   `if not f or f.get("_miss") or "tempo" not in f: continue`
#   · build_pool      "N 首查不到音频特征，已被排除"
#   · profile_library 反而做对了，它分了 "no-isrc" 和 "reccobeats" 两种
# 只有 profile_library 做对，恰恰说明这不是能力问题，而是定义没有归属。
#
# 接第二个平台时这一节最要紧：网易云/QQ 不返回 ISRC，no-isrc 会从 12% 直接
# 逼近 100%，而**那是换特征源也解决不了的**——和"特征源没收录"完全是两回事。
# 压成一个数字就把唯一能指导决策的信息丢掉了。

COVERAGE_STAGES = (
    "no-id",          # 没有平台曲目 id
    "no-meta",        # 拿不到元数据（地区未上架 / 已下架）
    "no-isrc",        # 没有 ISRC —— 特征链的硬边界
    "not-in-cache",   # 不在特征缓存里（还没抓过）
    "source-miss",    # 有 ISRC，但特征源没收录
    "no-features",    # 特征源返回了记录，但里面没有 tempo
    "ok",
)

COVERAGE_LABELS = {
    "no-id": "没有平台曲目 id（如库内自行上传的内容）",
    "no-meta": "拿不到元数据（地区未上架 / 已下架）",
    "no-isrc": "没有 ISRC —— **特征链的硬边界**，换特征源也解决不了",
    "not-in-cache": "不在特征缓存里（这批还没抓过）",
    "source-miss": "有 ISRC，但特征源未收录（可换源，或本地分析）",
    "no-features": "特征源返回了记录，但缺 tempo 字段",
    "ok": "可用",
}

# 低于这个覆盖率就该明说"排序只覆盖了一部分曲目"
LOW_COVERAGE = 0.90


def classify_coverage(*, has_id: bool = True, has_meta: bool = True,
                      isrc: str | None = None, in_cache: bool = True,
                      feat: dict | None = None) -> str:
    """一首曲子为什么能/不能被音频特征覆盖。**按漏斗顺序，先命中先返回。**

    顺序本身是有意义的，不能重排：`no-isrc` 必须排在 `source-miss` 前面。
    前者是"特征链根本没法开始"（换平台可能更糟，换特征源无用），
    后者是"有 ISRC 但这家源没收录"（换源就能解决）。这两件事的可行动性相反。
    """
    if not has_id:
        return "no-id"
    if not has_meta:
        return "no-meta"
    if not isrc:
        return "no-isrc"
    if not in_cache:
        return "not-in-cache"
    if feat is None or feat.get("_miss"):
        return "source-miss"
    if "tempo" not in feat:
        return "no-features"
    return "ok"


def coverage_report(counts: dict[str, int], total: int,
                    warn_below: float = LOW_COVERAGE) -> str:
    """把漏斗变成一个能读、能据以决策的几行字。"""
    if total <= 0:
        return "音频特征覆盖：（没有曲目可统计）"
    c = {k: int(counts.get(k, 0)) for k in COVERAGE_STAGES}
    ok = c["ok"]
    pct = ok / total * 100
    lines = [f"音频特征覆盖：{ok}/{total} 可用（{pct:.0f}%）"]
    for stage in COVERAGE_STAGES:
        if stage == "ok" or not c[stage]:
            continue
        lines.append(f"  · {c[stage]:>4} 首 {COVERAGE_LABELS[stage]}")
    lost = total - ok
    if lost and pct < warn_below * 100:
        lines.append(
            f"  ⚠️ 覆盖率 {pct:.0f}% 低于 {warn_below * 100:.0f}%："
            f"相邻规则与弧线**只在能测量的曲目之间**生效，"
            f"剩下 {lost} 首的位置实际上没有被评估过——"
            f"报告里的 cost 只描述前一部分。")
    return "\n".join(lines)

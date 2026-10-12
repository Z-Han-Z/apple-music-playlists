"""Shared Unicode catalog-identity matching, never a thematic taste score."""
import re
import unicodedata
from playlist_core import marker_hits

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
    "deluxe", "stereo", "version", "remix", "re-mix", "mixed", "bonus", "cover", "live",
    "demo", "edit", "mono",
)
VERSION_NOISE_CJK = ("现场", "演唱会", "伴奏", "翻唱", "重制", "纯音乐")

# 保留这个名字：文档里用它指代"版本后缀扣分"这件事
VERSION_NOISE = VERSION_NOISE_WORDS + VERSION_NOISE_CJK


def version_noise_hits(title: str) -> list[str]:
    """曲名里命中了哪些"版本后缀"，返回小写词表。

    匹配机制来自 `playlist_core.marker_hits`：拉丁词按整词匹配，CJK 按子串匹配。
    """
    return marker_hits(title, VERSION_NOISE_WORDS, VERSION_NOISE_CJK)


def has_unrequested_title_suffix(query: str, resolved_title: str) -> bool:
    """Whether catalog resolution appended a version-like title qualifier.

    Catalog search sometimes returns an otherwise matching alternate whose only difference is an
    unrequested trailing parenthetical, bracket, or dash subtitle.  A fixed vocabulary cannot
    cover names such as ``(under the fabric)``, so surface the structural mismatch for the host
    model to review.  Qualifiers explicitly present in the query are not flagged.
    """
    parts = re.split(r"\s+(?:-|—|–)\s+", query or "", maxsplit=1)
    wanted = parts[0].strip()
    actual = (resolved_title or "").strip()
    if not wanted or not actual or wanted.casefold() == actual.casefold():
        return False
    match = re.match(re.escape(wanted), actual, flags=re.IGNORECASE)
    if not match:
        return False
    suffix = actual[match.end():].lstrip()
    if not suffix.startswith(("(", "[", "-", "–", "—")):
        return False
    requested_markers = set(version_noise_hits(wanted))
    actual_markers = set(version_noise_hits(actual))
    return not bool(requested_markers & actual_markers)


def best_song_match(query: str, songs: list[dict]) -> dict | None:
    """从搜索结果里挑最匹配的一首：先按查询条件硬过滤，再按相似度打分。

    过滤是硬条件——查询里带了艺人，就只保留艺人能对上的候选；带了曲名，
    就只保留曲名能对上的候选。**一个候选都留不下时返回 None。**

    为什么不能兜底返回搜索第一条：搜索结果的排序受热度影响，未必是这首歌。
    真实误伤是「某艺人的一首翻唱并未上架，搜索首条成了别家录的伴奏版」，
    兜底会把一首完全无关的曲子无提示地写进歌单。漏掉会明确报「未找到」，
    比静默写错一首安全。
    """
    def norm(s: str) -> str:
        # The previous ASCII+CJK range erased Hangul and Japanese kana. Unicode
        # alphanumerics preserve every script; NFKD also folds Latin accents.
        decomposed = unicodedata.normalize("NFKD", (s or "").casefold())
        return "".join(ch for ch in decomposed if ch.isalnum())

    if not songs:
        return None
    parts = re.split(r"\s+(?:-|—|–)\s+", query, maxsplit=1)
    want_t, want_a = (parts[0], parts[1]) if len(parts) == 2 else (query, "")
    nt, na = norm(want_t), norm(want_a)
    if not nt and not na:
        return None

    def title_ok(t: str) -> bool:
        return not nt or nt == t or nt in t or t in nt

    def artist_ok(ar: str) -> bool:
        # 艺人名为空的候选不能放行：`"" in na` 恒为真，等于没过滤。
        return not na or (bool(ar) and (na in ar or ar in na))

    kept = []
    for s in songs:
        a = s.get("attributes", {})
        if title_ok(norm(a.get("name") or "")) and artist_ok(norm(a.get("artistName") or "")):
            kept.append(s)
    if not kept:
        return None
    songs = kept

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
            # 进得来的候选一定是完全一致或包含关系，这里只需区分两者
            score += 3.0 if nt == t else 2.0
        if na:
            score += 2.0 if na == ar else 1.5
        # 曲名里带查询没要求的版本后缀 → 扣分（"Live" 之类）
        for w in version_noise_hits(raw_t):
            if w not in q_hits:
                score -= 1.2
                break
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]

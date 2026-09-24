#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歌单「方向标签」（direction tags）——把一次策展的意图压成约 5 个可操纵的标签。

定位必须说清楚，否则很容易用错。

**这个模块不认识音乐。** 标签由宿主 LLM 写：它读过用户的 brief、了解那些歌，
才写得出 `synthwave` / `night` / `recent-heavy-rotation` 这样的词。本模块不含任何
艺人、流派或主题清单，也不给任何标签打分或排序。

**它只做三件确定性的事：**

1. 校验一组标签（数量上限、去重、轴归属、侧重档位），把问题和修法一并报出来；
2. 按用户说的 `more funk` / `less disco` 改侧重档——这是**记账**，不是审美判断，
   所以它属于代码而不属于模型；
3. 把结果渲染成一份可读的**修订记录**，供下一轮策展参考。

## 为什么没有数值权重

第一版给每个标签一个 `0.0–2.0` 的小数权重，`more` / `less` 各加减 `0.5`。
评审否掉了它，理由成立：**那会把自然语言里的审美判断伪装成有精度的数值**，
与项目已经确定的原则（模型直接理解 brief，不要把主题契合度压成参数化分数）冲突。

所以侧重只有三档**定性**状态，且**原始措辞一律留存**：

    soften   弱化（用户说 less / 少一点）
    neutral  中性（默认）
    boost    强调（用户说 more / 多一点）

`more` 在档位上走一格，到 `boost` 为止；`less` 走一格，低于 `soften` 就移除。
全程没有浮点数，因此不存在「1.5 到底比 1.0 多多少」这种假精度。

**侧重不是选曲依据。** 它是一份给用户看、可编辑的策展摘要，记录「往哪边挪」；
选哪些歌仍然只由模型对 brief 的理解决定，`direction_note()` 会把这条边界写进输出。

## 与 brief 的关系：操纵面，不是替代品

`docs/evaluation-signals.md` 说明了为什么把需求压成标签或权重表会丢掉否定范围、
参照语义和叙事节点。本模块不推翻这个结论，而是反过来用：方向标签是**给用户的操纵面**，
brief 与策展契约始终是唯一权威，冲突时以 brief 为准。

两个轴把「音乐本身」和「用户行为」分开，因为它们的可信度不同：

    sonic    音乐自身的属性：流派、年代、织体、氛围、编制
    context  这些歌为什么在这里：最近在听、高播放、集中循环、本就在库里、
             来自某个参照曲、新发现但没听过

## context 必须带 evidence

`context` 标签是「**用户在听什么**」的断言，所以它不能是印象：

| 行为类方向 | 能支撑它的工具调用 | 实际能看到 | 注意 |
|---|---|---|---|
| 近期 | `am_recently_played` | 最近**播放**的有序列表 | 没有次数，只有顺序 |
| 高播放 | `am_top_played` | Replay 的 `playCount` 排名 | 按周期；`all-time` 不一定存在，须退到具体年份 |
| 集中播放 | `am_top_played` | `firstPlayed` / `lastPlayed` + `playCount` | **没有现成字段**，得自己算「窄时间窗 × 高次数」——是**派生**结论 |
| 在用户歌单中 | `am_list_playlists` + `am_show_playlist` | 歌单成员关系 | 直接、准确 |

写 `{"label": "...", "axis": "context", "evidence": "am_top_played year-2026"}`。
**没有 evidence 的 context 标签会被接受，但一定报出来，并在展示串里标成「证据缺失」**——
用户有权分辨哪个行为说法是有依据的、哪个是模型的猜测。

两个反例值得单独记着：`am_recently_played(kind=added)` 是「最近**入库**」，不等于
「最近在听」；「集中播放」不是任何接口的现成字段，只能由 `firstPlayed`/`lastPlayed`
与 `playCount` 推出来。这两处都容易把推断说成事实。

`sonic` 标签带 evidence 会提示多余——音乐属性不需要收听证据。
"""

import unicodedata

# ---------------------------------------------------------------- 契约参数

TARGET_TAG_COUNT = 5     # 用户要的「约 5 个」
MAX_TAGS = 8             # 超过就不是操纵面，是清单了

SONIC = "sonic"
CONTEXT = "context"
UNSPECIFIED = "unspecified"
AXES = (SONIC, CONTEXT, UNSPECIFIED)

# `context` 标签是「用户在听什么」的断言，只有两类东西撑得住它：
#   am_recently_played       最近播放（有序，无次数）
#   am_top_played            Replay 的 playCount / firstPlayed / lastPlayed
#   am_list_playlists + am_show_playlist   歌单成员关系
# 没有来源的 context 标签不是"待补充"，而是**把模型推断当作用户事实呈现**，
# 所以它会被接受但一定报出来，并在展示串里标成「证据缺失」。
EVIDENCE_HINT = ("am_recently_played / am_top_played / am_list_playlists / am_show_playlist")

# 侧重：三档定性状态，没有数值，也不做算术。
SOFTEN = "soften"
NEUTRAL = "neutral"
BOOST = "boost"
EMPHASES = (SOFTEN, NEUTRAL, BOOST)
_LEVEL = {SOFTEN: 0, NEUTRAL: 1, BOOST: 2}
_BY_LEVEL = {0: SOFTEN, 1: NEUTRAL, 2: BOOST}

# 不靠词表猜轴——只认显式写法。猜轴需要一份流派/行为词库，那就等于把
# 「这个模块不认识音乐」这句话作废。
AXIS_PREFIX = (SONIC + ":", CONTEXT + ":")

# 操作词。拉丁词**必须**后接词边界：否则 `nothing but jazz` 会被读成
# `drop "thing but jazz"`、`downbeat` 读成 `less "beat"`、`morello` 读成 `more "llo"`，
# 把正常句子篡改成相反甚至破坏性的调整。CJK 没有词边界，但操作词本身
# 足够长且具体，直接前缀匹配。
_LATIN_OPS = sorted(
    [(w, "more") for w in ("more", "increase", "boost", "emphasise", "emphasize", "up")] +
    [(w, "less") for w in ("less", "fewer", "decrease", "reduce", "lower", "down", "soften")] +
    [(w, "drop") for w in ("drop", "remove", "delete", "without", "exclude", "no")] +
    [(w, "add") for w in ("add", "also", "include")],
    key=lambda p: -len(p[0]),
)
_CJK_OPS = sorted(
    [(w, "more") for w in ("多一点", "多一些", "更多", "加强", "强化", "加重")] +
    [(w, "less") for w in ("少一点", "少一些", "更少", "减弱", "弱化", "淡化", "减轻")] +
    [(w, "drop") for w in ("去掉", "移除", "删除", "不要", "别要")] +
    [(w, "add") for w in ("加上", "加入", "再加", "补上")],
    key=lambda p: -len(p[0]),
)

_SEPARATORS = " \t:：,，、;；"


# ---------------------------------------------------------------- 基础工具

def tag_key(label: str) -> str:
    """标签的匹配键：NFKC + casefold + 只留字母数字。

    用 `isalnum()` 而不是 `[^0-9a-z\\u4e00-\\u9fff]`：后者会把日文假名和韩文
    整个抹掉（这个仓库在别处修过同一类 bug，见 `am_playlist.best_song_match`）。
    """
    s = unicodedata.normalize("NFKC", str(label or "")).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def _axis_of(raw: str) -> tuple:
    """拆掉 `context:` / `sonic:` 前缀，返回 (标签文本, 轴)。"""
    text = str(raw or "").strip()
    low = text.casefold()
    for prefix in AXIS_PREFIX:
        if low.startswith(prefix):
            return text[len(prefix):].strip(), prefix[:-1]
    return text, UNSPECIFIED


def _emphasis_of(value) -> tuple:
    """把 emphasis 归一化成三档之一，返回 (档位, 说明或 None)。"""
    if value is None or value == "":
        return NEUTRAL, None
    text = str(value).strip().casefold()
    alias = {"strong": BOOST, "more": BOOST, "up": BOOST, "high": BOOST,
             "normal": NEUTRAL, "none": NEUTRAL, "mid": NEUTRAL,
             "weak": SOFTEN, "less": SOFTEN, "low": SOFTEN}
    text = alias.get(text, text)
    if text in EMPHASES:
        return text, None
    return NEUTRAL, (f"侧重「{value}」看不懂；只认 {'/'.join(EMPHASES)}，"
                      f"已按 {NEUTRAL} 处理")


def _coerce(raw) -> tuple:
    """把 str 或 dict 变成 (label, axis, emphasis, evidence, notes)。"""
    notes = []
    if isinstance(raw, dict):
        label = raw.get("label") or raw.get("name") or raw.get("tag") or ""
        axis = str(raw.get("axis") or "").strip().casefold()
        if axis not in (SONIC, CONTEXT):
            axis = UNSPECIFIED
        if "weight" in raw:
            notes.append("weight 已废弃：数值权重会把审美判断伪装成有精度的数值，"
                         "改用 emphasis: soften/neutral/boost")
        emphasis, note = _emphasis_of(raw.get("emphasis"))
        if note:
            notes.append(note)
        evidence = str(raw.get("evidence") or "").strip()
        return str(label).strip(), axis, emphasis, evidence, notes
    label, axis = _axis_of(str(raw or ""))
    return label, axis, NEUTRAL, "", notes


def _evidence_notes(label: str, axis: str, evidence: str) -> list:
    """`context` 轴必须能说出证据来源，否则就是拿模型推断冒充用户事实。

    这不是格式洁癖，是仓库那条三分法（catalog 事实 / 收听证据 / 模型推断）的落点：
    `context` 标签描述的是**用户在听什么**，只有前两类撑得住。**不阻断**——
    只出一条说明，因为调用方可能把证据放在别处（例如整份报告的说明里）。
    """
    if axis == CONTEXT and not evidence:
        return [f"context 标签「{label}」没写 evidence：行为类方向要有真实收听证据"
                f"（{EVIDENCE_HINT} 之一），否则等于把模型推断当作用户事实呈现"]
    if axis == SONIC and evidence:
        return [f"标签「{label}」是 sonic（音乐自身属性），不需要收听证据；"
                f"evidence 已保留，但它在这里不起支撑作用"]
    return []


# ---------------------------------------------------------------- 校验

def normalize_tags(items) -> tuple:
    """校验一组标签，返回 (tags, problems)。

    `items` 每项可以是 `"night"`、`"context:recent-heavy-rotation"`，或
    `{"label": ..., "axis": "sonic", "emphasis": "boost", "evidence": "..."}`。

    `context` 轴建议带 `evidence`（支撑它的工具调用）。没有证据的 `context` 标签
    会被接受但**报出来**：用户有权知道哪个「你在听什么」的说法是有依据的。

    problems 是给人看的说明，不是错误码——调用方应当把它们报告给用户，
    而不是静默改完继续。
    """
    by_key, order, problems = {}, [], []
    for raw in items or []:
        label, axis, emphasis, evidence, notes = _coerce(raw)
        problems.extend(notes)
        if not label:
            problems.append("跳过了一个没有名字的标签")
            continue
        key = tag_key(label)
        if not key:
            problems.append(f"标签「{label}」去掉符号后是空的，已跳过")
            continue
        if key in by_key:
            kept = by_key[key]
            if axis != UNSPECIFIED and kept["axis"] == UNSPECIFIED:
                kept["axis"] = axis
            elif axis != UNSPECIFIED and axis != kept["axis"]:
                problems.append(f"标签「{label}」给了两种轴（{kept['axis']} / {axis}），"
                                f"保留先出现的 {kept['axis']}")
            if evidence and not kept.get("evidence"):
                kept["evidence"] = evidence
            problems.append(f"标签「{label}」重复出现，保留先出现的那条"
                            f"（侧重 {kept['emphasis']}）")
            continue
        if axis == UNSPECIFIED:
            problems.append(f"标签「{label}」没写轴；写 sonic: 或 context: 才能区分"
                            f"音乐属性与行为来源")
        problems.extend(_evidence_notes(label, axis, evidence))
        by_key[key] = {"key": key, "label": label, "axis": axis,
                       "emphasis": emphasis, "evidence": evidence}
        order.append(key)

    tags = [by_key[k] for k in order]
    if len(tags) > MAX_TAGS:
        problems.append(f"给了 {len(tags)} 个标签，超过上限 {MAX_TAGS}；"
                        f"保留前 {MAX_TAGS} 个，其余请先合并再传"
                        f"（超出：{'、'.join(t['label'] for t in tags[MAX_TAGS:])}）")
        tags = tags[:MAX_TAGS]
    return tags, problems


# ---------------------------------------------------------------- 调整

def _match_op(raw: str) -> tuple:
    """返回 (op, 剩余文本)，匹配不到就 (None, None)。

    拉丁操作词要求后接**词边界**——这条边界是必需的而不是修饰。见文件顶部说明。
    """
    low = raw.casefold()
    for word, op in _CJK_OPS:
        if low.startswith(word):
            return op, raw[len(word):]
    for word, op in _LATIN_OPS:
        if low.startswith(word):
            rest = raw[len(word):]
            if rest and (rest[0].isalnum() or rest[0] == "_"):
                continue
            return op, rest
    return None, None


def parse_adjustment(text) -> dict:
    """把 `more funk` / `少一点 disco` / `drop x` / `add y` 解析成结构化调整。

    解析不了就返回 None——调用方必须把它报成「没读懂」，不能当没说过。
    """
    if isinstance(text, dict):
        op = str(text.get("op") or "").strip().casefold()
        label = str(text.get("label") or text.get("tag") or "").strip()
        if op not in ("more", "less", "drop", "add") or not label:
            return None
        return {"op": op, "label": label}

    raw = str(text or "").strip()
    if not raw:
        return None

    # 简写：+funk / -disco
    if raw[0] in "+-" and len(raw) > 1:
        return {"op": "more" if raw[0] == "+" else "less", "label": raw[1:].strip()}

    op, rest = _match_op(raw)
    if not op:
        return None
    rest = str(rest or "").strip(_SEPARATORS)
    if not rest:
        return None
    return {"op": op, "label": rest}


def _shift_level(emphasis: str, steps: int) -> int:
    """返回**未钳位**的档位数字。

    `less` 要能落到 0 以下才知道「弱化到头、应移除」，所以钳位必须延后到
    调用方决定完语义之后——先钳位会让那个分支永远走不到。
    """
    return _LEVEL.get(emphasis, _LEVEL[NEUTRAL]) + steps


def apply_adjustments(tags, adjustments) -> tuple:
    """按用户的方向调侧重档，返回 (tags, report)。

    语义（刻意做成简单可解释的记账，且全程没有算术）：

        more X   侧重上移一档（已是 boost 则不动）
        less X   侧重下移一档；低于 soften 就移除
        drop X   直接移除
        add  X   不存在就补一个，侧重 neutral

    report 保留用户的**原始措辞**（`input`），所以整份结果是一份可见的修订记录。

    找不到的标签会报 `unknown`，**不会**当成「说过了但没效果」吞掉——
    用户说 more funk 而方向里没有 funk 时，必须让他知道。
    """
    current = [dict(t) for t in tags]
    by_key = {t["key"]: t for t in current}
    report = []

    def entry(raw, status, detail, **extra):
        row = {"input": raw if not isinstance(raw, dict) else raw.get("label", raw),
               "status": status, "detail": detail}
        row.update(extra)
        report.append(row)

    for raw in adjustments or []:
        # 修订记录要留**用户原话**，不是解析后的标签：用户回看时该看到自己说了什么。
        orig = raw if isinstance(raw, str) else (
            raw.get("label") if isinstance(raw, dict) else str(raw))
        adj = parse_adjustment(raw)
        if not adj:
            entry(orig, "unparsed",
                  "没读懂方向；用 more X / less X / drop X / add X 的写法")
            continue
        op, label = adj["op"], adj["label"]
        shown = label

        if op == "add":
            # 新增项必须走同一套规范化：否则 `add !!!` 会塞进一个空 key，
            # 带 `context:` 前缀的新增项也不会被拆轴。
            new_label, axis, emphasis, evidence, _ = _coerce(label)
            key = tag_key(new_label)
            if not key:
                entry(orig, "rejected",
                      f"「{shown}」去掉符号后没有可用字符，不能作为标签")
                continue
            if key in by_key:
                entry(orig, "already-present",
                      f"「{new_label}」已经在方向里，侧重保持 {by_key[key]['emphasis']}")
                continue
            if len(current) >= MAX_TAGS:
                entry(orig, "rejected",
                      f"方向已有 {len(current)} 个标签，到上限 {MAX_TAGS}，删掉一个再加")
                continue
            new = {"key": key, "label": new_label, "axis": axis,
                   "emphasis": emphasis, "evidence": evidence}
            current.append(new)
            by_key[key] = new
            missing = _evidence_notes(new_label, axis, evidence)
            entry(orig, "added",
                  f"新增「{new_label}」，侧重 {emphasis}"
                  f"（轴 {'未指定' if axis == UNSPECIFIED else axis}）"
                  + ("；" + "；".join(missing) if missing else ""))
            continue

        key = tag_key(label)
        if key not in by_key:
            entry(orig, "unknown",
                  f"方向里没有「{shown}」，所以 {op} 没有作用；"
                  f"现有标签：{'、'.join(t['label'] for t in current) or '（空）'}")
            continue

        tag = by_key[key]
        before = tag["emphasis"]

        if op == "drop":
            current = [t for t in current if t["key"] != key]
            del by_key[key]
            entry(orig, "dropped", f"删掉「{shown}」（原侧重 {before}）",
                  before=before, after=None)
            continue

        if op == "more" and before == BOOST:
            entry(orig, "at-max", f"「{shown}」已经是 {BOOST}，不会再加强",
                  before=before, after=before)
            continue

        after = _BY_LEVEL[min(max(_shift_level(before, 1 if op == "more" else -1), 0), 2)]
        if op == "less" and _shift_level(before, -1) < 0:
            current = [t for t in current if t["key"] != key]
            del by_key[key]
            entry(orig, "dropped",
                  f"「{shown}」弱化到头，已从方向里移除（原侧重 {before}）",
                  before=before, after=None)
            continue
        tag["emphasis"] = after
        entry(orig, "applied", f"「{shown}」{before} → {after}",
              before=before, after=after)

    return current, report


# ---------------------------------------------------------------- 呈现

def axis_summary(tags) -> dict:
    """按轴计数。宿主据此判断方向是否只描了音乐、没写行为来源（或反之）。"""
    out = {SONIC: 0, CONTEXT: 0, UNSPECIFIED: 0}
    for t in tags or []:
        axis = t.get("axis", UNSPECIFIED)
        out[axis] = out.get(axis, 0) + 1
    return out


def _mark(tag) -> str:
    """定性标记。刻意不用数字——数字会被读成精度。"""
    bits = []
    if tag["emphasis"] == BOOST:
        bits.append("强调")
    elif tag["emphasis"] == SOFTEN:
        bits.append("弱化")
    if tag.get("axis") == CONTEXT:
        # 行为类标签的证据要**露出来**：用户有权知道哪个「你在听什么」的说法有依据。
        ev = tag.get("evidence") or ""
        bits.append(f"证据：{ev}" if ev else "证据缺失")
    return f"{tag['label']}（{' · '.join(bits)}）" if bits else tag["label"]


def render_tags(tags, language: str = "en") -> str:
    """一行展示串，直接给用户看。"""
    if not tags:
        return ""
    zh = str(language or "").lower().startswith("zh")
    groups = [(SONIC, "音乐" if zh else "sonic"),
              (CONTEXT, "行为" if zh else "context"),
              (UNSPECIFIED, None)]
    parts = []
    for axis, label in groups:
        members = [t for t in tags if t.get("axis", UNSPECIFIED) == axis]
        if not members:
            continue
        body = " · ".join(_mark(t) for t in members)
        parts.append(f"{label} — {body}" if label else body)
    return "  ‖  ".join(parts)


def direction_note(tags, language: str = "zh") -> str:
    """把方向写成一句能塞回 brief 的说明。

    刻意把两条边界写进输出本身：宿主模型读到的就是带约束的指令，
    不靠外部文档提醒——「不是 brief」以及「侧重不是选曲依据」。
    """
    if not tags:
        return ""
    zh = str(language or "").lower().startswith("zh")
    focus = [t["label"] for t in tags if t["emphasis"] == BOOST]
    soften = [t["label"] for t in tags if t["emphasis"] == SOFTEN]
    no_evidence = [t["label"] for t in tags
                   if t.get("axis") == CONTEXT and not t.get("evidence")]
    if zh:
        def one(t):
            bits = ["音乐" if t["axis"] == SONIC else
                    "行为" if t["axis"] == CONTEXT else "未标轴"]
            if t["emphasis"] == BOOST:
                bits.append("强调")
            elif t["emphasis"] == SOFTEN:
                bits.append("弱化")
            if t.get("axis") == CONTEXT:
                bits.append(f"证据：{t['evidence']}" if t.get("evidence") else "证据缺失")
            return f"{t['label']}（{'，'.join(bits)}）"
        body = "；".join(one(t) for t in tags)
        tail = ""
        if focus:
            tail += f"本轮更偏「{'、'.join(focus)}」。"
        if soften:
            tail += f"相应收紧「{'、'.join(soften)}」。"
        if no_evidence:
            tail += (f"注意「{'、'.join(no_evidence)}」没有证据来源，"
                     f"只能当作待确认的推测，不要说成用户事实。")
        return (f"方向标签（约 {TARGET_TAG_COUNT} 个）：{body}。{tail}"
                f"这些标签是给用户的操纵面，**不是 brief**：原始需求与策展契约仍然优先，"
                f"冲突时以 brief 为准；侧重只是方向提示，**不构成选曲依据**。"
                f"行为类标签必须有真实收听证据支持。")
    def one_en(t):
        bits = ["sonic" if t["axis"] == SONIC else
                "context" if t["axis"] == CONTEXT else "axis unset"]
        if t["emphasis"] == BOOST:
            bits.append("emphasize")
        elif t["emphasis"] == SOFTEN:
            bits.append("soften")
        if t.get("axis") == CONTEXT:
            bits.append(f"evidence: {t['evidence']}" if t.get("evidence") else "no evidence")
        return f"{t['label']} ({', '.join(bits)})"
    body = " / ".join(one_en(t) for t in tags)
    tail = ""
    if focus:
        tail += f" Lean toward {', '.join(focus)}."
    if soften:
        tail += f" Hold back on {', '.join(soften)}."
    if no_evidence:
        tail += (f" Note that {', '.join(no_evidence)} carry no evidence source, so treat them "
                 f"as unconfirmed inference rather than as facts about the user.")
    return (f"Direction tags (~{TARGET_TAG_COUNT}): {body}.{tail} "
            f"These tags are a user-facing steering surface, **not the brief**: the original "
            f"request and the curation contract stay authoritative, and the brief wins any "
            f"conflict. Emphasis is a direction hint and is **not a selection criterion**; "
            f"context tags must be backed by real listening evidence.")


def summary(tags, problems=None, report=None, language: str = "zh",
            brief: str = "") -> str:
    """给 MCP 工具用的紧凑文本报告。

    `brief` 传入时会被**原样回显**在最前面。评审要求「原始 brief 仍应始终可见且优先」：
    提示词路径里 brief 本来就在标签之上，但**调整路径**上不是——用户隔一轮只说
    「more funk」时，模型手上只剩方向说明，原始需求可能已被挤出上下文。回显它，
    这条路径也满足「始终可见」。
    """
    lines = []
    if brief and brief.strip():
        lines.append("原始 brief（**始终优先**；下面的方向标签只是补充）：")
        lines.append(f"  {brief.strip()}")
        lines.append("")
    if not tags:
        lines.append("方向标签：空。")
    else:
        lines.append(f"方向标签（{len(tags)} 个，目标约 {TARGET_TAG_COUNT} 个）：")
        for t in tags:
            row = f"  · {t['label']}  [轴={t['axis']}  侧重={t['emphasis']}"
            if t.get("axis") == CONTEXT:
                row += f"  证据={t.get('evidence') or '（缺）'}"
            lines.append(row + "]")
        counts = axis_summary(tags)
        lines.append(f"  轴分布：音乐 {counts[SONIC]} / 行为 {counts[CONTEXT]} / "
                     f"未标 {counts[UNSPECIFIED]}")
        missing = [t["label"] for t in tags
                   if t.get("axis") == CONTEXT and not t.get("evidence")]
        if missing:
            lines.append(f"  ⚠ 无证据的行为标签：{'、'.join(missing)}"
                         f"（只能当成待确认的推测，不要说成用户事实）")
        lines.append(f"  展示：{render_tags(tags, language)}")
    if problems:
        lines.append("校验说明：")
        lines.extend(f"  ! {p}" for p in problems)
    if report:
        lines.append("方向修订记录（保留原话）：")
        for r in report:
            lines.append(f"  · 「{r['input']}」→ [{r['status']}] {r['detail']}")
    if tags:
        lines.append("")
        lines.append(direction_note(tags, language))
    return "\n".join(lines)

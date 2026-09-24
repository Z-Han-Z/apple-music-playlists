#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歌单「方向标签」（direction tags）——把一次策展的意图压成约 5 个可操纵的标签。

定位必须说清楚，否则很容易用错。

**这个模块不认识音乐。** 标签由宿主 LLM 写：它读过用户的 brief、了解那些歌，
才写得出 `synthwave` / `night` / `recent-heavy-rotation` 这样的词。本模块不含任何
艺人、流派或主题清单，也不给任何标签打分或排序。

**它只做三件确定性的事：**

1. 校验一组标签（数量上限、权重区间、去重、轴归属），把问题和修法一并报出来；
2. 按用户说的 `more funk` / `less disco` 调权重——这是**记账**，不是审美判断，
   所以它属于代码而不属于模型；
3. 把结果渲染成一句能塞回 brief 的方向说明，供下一轮策展使用。

**它不替代 brief，只是操纵面。** 仓库里的
`docs/evaluation-signals.md` 说明了为什么把需求压成标签或权重表
会丢掉否定范围、参照语义和叙事节点。这里刻意反着用：标签是给用户的**风格化、
抽象化的修改方向**，brief 与策展契约始终是唯一权威；方向说明只是对它的补充，
冲突时以 brief 为准。这一点也写进了 `direction_note()` 的输出里，宿主模型读得到。

两个轴把「音乐本身」和「用户行为」分开，因为它们的可信度不同：

    sonic    音乐自身的属性：流派、年代、织体、氛围、编制
    context  这些歌为什么在这里：最近在听、高播放、集中循环、本就在库里、
             来自某个参照曲、新发现但没听过

`context` 轴上的标签必须来自真实证据（`am_recently_played` / `am_top_played` /
音乐库），不能凭印象写——这是「catalog 事实 / 收听证据 / 模型推断」三分法的延伸。
"""

import re
import unicodedata

# ---------------------------------------------------------------- 契约参数

TARGET_TAG_COUNT = 5     # 用户要的「约 5 个」
MAX_TAGS = 8             # 超过就不是操纵面，是清单了
BASE_WEIGHT = 1.0
MIN_WEIGHT = 0.0
MAX_WEIGHT = 2.0
DEFAULT_STEP = 0.5       # 「多一点 / 少一点」一次动多少

SONIC = "sonic"
CONTEXT = "context"
UNSPECIFIED = "unspecified"
AXES = (SONIC, CONTEXT, UNSPECIFIED)

# 不靠词表猜轴——只认显式写法。猜轴需要一份流派/行为词库，那就等于把
# 「这个模块不认识音乐」这句话作废了。
AXIS_PREFIX = (SONIC + ":", CONTEXT + ":")

# 操作词表。纯记账用的语法糖，不涉及任何音乐知识。
# 长的先匹配，否则 `no` 会抢走 `nothing` 这类前缀。
_MORE = ("more", "increase", "boost", "emphasise", "emphasize", "up",
         "多一点", "多一些", "更多", "加强", "强化", "加重")
_LESS = ("less", "fewer", "decrease", "reduce", "lower", "down", "soften",
         "少一点", "少一些", "更少", "减弱", "弱化", "淡化", "减轻")
_DROP = ("drop", "remove", "delete", "without", "exclude", "no",
         "去掉", "移除", "删除", "不要", "去掉", "别要")
_ADD = ("add", "also", "include", "加上", "加入", "再加", "补上")

_OP_WORDS = sorted(
    [(w, "more") for w in _MORE] + [(w, "less") for w in _LESS] +
    [(w, "drop") for w in _DROP] + [(w, "add") for w in _ADD],
    key=lambda p: -len(p[0]),
)

_TRAILING_AMOUNT = re.compile(r"^(?P<label>.*?)[\s:：]*"
                              r"(?P<amount>[0-9]+(?:\.[0-9]+)?)$")


# ---------------------------------------------------------------- 基础工具

def tag_key(label: str) -> str:
    """标签的匹配键：NFKC + casefold + 只留字母数字。

    用 `isalnum()` 而不是 `[^0-9a-z\\u4e00-\\u9fff]`：后者会把日文假名和韩文
    整个抹掉（这个仓库在别处刚修过同一类 bug，见 `am_playlist.best_song_match`）。
    """
    s = unicodedata.normalize("NFKC", str(label or "")).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def _clamp(weight) -> float:
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return BASE_WEIGHT
    if w != w:                      # NaN
        return BASE_WEIGHT
    return round(min(max(w, MIN_WEIGHT), MAX_WEIGHT), 3)


def _axis_of(raw: str) -> tuple:
    """拆掉 `context:` / `sonic:` 前缀，返回 (标签文本, 轴)。"""
    text = raw.strip()
    low = text.casefold()
    for prefix in AXIS_PREFIX:
        if low.startswith(prefix):
            return text[len(prefix):].strip(), prefix[:-1]
    return text, UNSPECIFIED


def _coerce(raw) -> tuple:
    """把 str 或 dict 变成 (label, axis, weight)。"""
    if isinstance(raw, dict):
        label = raw.get("label") or raw.get("name") or raw.get("tag") or ""
        axis = str(raw.get("axis") or "").strip().casefold()
        if axis not in (SONIC, CONTEXT):
            axis = UNSPECIFIED
        weight = raw.get("weight", BASE_WEIGHT)
        return str(label).strip(), axis, _clamp(weight)
    label, axis = _axis_of(str(raw or ""))
    return label, axis, BASE_WEIGHT


# ---------------------------------------------------------------- 校验

def normalize_tags(items) -> tuple:
    """校验一组标签，返回 (tags, problems)。

    `items` 每项可以是 `"night"`、`"context:recent-heavy-rotation"`，或
    `{"label": ..., "axis": "sonic", "weight": 1.5}`。

    problems 是给人看的说明，不是错误码——调用方应当把它们报告给用户，
    而不是静默改完继续。
    """
    by_key, order, problems = {}, [], []
    for raw in items or []:
        label, axis, weight = _coerce(raw)
        if not label:
            problems.append("跳过了一个没有名字的标签")
            continue
        key = tag_key(label)
        if not key:
            problems.append(f"标签「{label}」去掉符号后是空的，已跳过")
            continue
        if key in by_key:
            kept = by_key[key]
            if weight > kept["weight"]:
                kept["weight"] = weight
            if axis != UNSPECIFIED and kept["axis"] == UNSPECIFIED:
                kept["axis"] = axis
            elif axis != UNSPECIFIED and axis != kept["axis"]:
                problems.append(f"标签「{label}」给了两种轴（{kept['axis']} / {axis}），"
                                f"保留先出现的 {kept['axis']}")
            problems.append(f"标签「{label}」重复出现，合并为一个（权重取较大值）")
            continue
        if axis == UNSPECIFIED:
            problems.append(f"标签「{label}」没写轴；写 sonic: 或 context: 才能区分"
                            f"音乐属性与行为来源")
        by_key[key] = {"key": key, "label": label, "axis": axis, "weight": weight}
        order.append(key)

    tags = [by_key[k] for k in order]
    if len(tags) > MAX_TAGS:
        problems.append(f"给了 {len(tags)} 个标签，超过上限 {MAX_TAGS}；"
                        f"保留前 {MAX_TAGS} 个，其余请先合并再传"
                        f"（超出：{'、'.join(t['label'] for t in tags[MAX_TAGS:])}）")
        tags = tags[:MAX_TAGS]
    return tags, problems


# ---------------------------------------------------------------- 调整

def parse_adjustment(text) -> dict:
    """把 `more funk` / `少一点 disco` / `drop x` / `add y` 解析成结构化调整。

    解析不了就返回 None——调用方必须把它报成「没读懂」，不能当没说过。
    """
    if isinstance(text, dict):
        op = str(text.get("op") or "").strip().casefold()
        label = str(text.get("label") or text.get("tag") or "").strip()
        if op not in ("more", "less", "drop", "add") or not label:
            return None
        amount = text.get("amount")
        return {"op": op, "label": label,
                "amount": DEFAULT_STEP if amount is None else _step(amount)}

    raw = str(text or "").strip()
    if not raw:
        return None

    # 简写：+funk / -disco
    if raw[0] in "+-" and len(raw) > 1:
        return {"op": "more" if raw[0] == "+" else "less",
                "label": raw[1:].strip(), "amount": DEFAULT_STEP}

    low = raw.casefold()
    for word, op in _OP_WORDS:
        if low.startswith(word):
            rest = raw[len(word):].strip(" \t:：,，、")
            if not rest:
                return None
            amount = DEFAULT_STEP
            m = _TRAILING_AMOUNT.match(rest)
            if m and m.group("label").strip():
                rest, amount = m.group("label").strip(), _step(m.group("amount"))
            return {"op": op, "label": rest, "amount": amount}
    return None


def _step(amount) -> float:
    try:
        a = abs(float(amount))
    except (TypeError, ValueError):
        return DEFAULT_STEP
    if a != a or a == 0:
        return DEFAULT_STEP
    return round(min(a, MAX_WEIGHT), 3)


def apply_adjustments(tags, adjustments) -> tuple:
    """按用户的方向调整标签权重，返回 (tags, report)。

    语义（刻意做成简单可解释的记账）：

        more X   权重 +step（默认 0.5），封顶 MAX_WEIGHT
        less X   权重 -step，跌到 MIN_WEIGHT 就删掉（并说明）
        drop X   直接删掉
        add  X   不存在就补一个，权重 BASE_WEIGHT

    找不到的标签会报 `unknown`，**不会**当成「说过了但没效果」吞掉——
    用户说 more funk 而歌单里没有 funk 时，必须让他知道。
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
        adj = parse_adjustment(raw)
        if not adj:
            entry(str(raw), "unparsed",
                  "没读懂方向；用 more X / less X / drop X / add X 的写法")
            continue
        op, label = adj["op"], adj["label"]
        key = tag_key(label)
        step = adj.get("amount", DEFAULT_STEP)
        shown = label

        if op == "add":
            if key in by_key:
                entry(shown, "already-present",
                      f"「{shown}」已经在方向里，权重保持 {by_key[key]['weight']}")
                continue
            if len(current) >= MAX_TAGS:
                entry(shown, "rejected",
                      f"方向已有 {len(current)} 个标签，到上限 {MAX_TAGS}，"
                      f"删掉一个再加")
                continue
            new = {"key": key, "label": label, "axis": UNSPECIFIED,
                   "weight": BASE_WEIGHT}
            current.append(new)
            by_key[key] = new
            entry(shown, "added", f"新增「{shown}」，权重 {BASE_WEIGHT}（轴未指定）",
                  weight=BASE_WEIGHT)
            continue

        if key not in by_key:
            entry(shown, "unknown",
                  f"方向里没有「{shown}」，所以 {op} 没有作用；"
                  f"现有标签：{'、'.join(t['label'] for t in current) or '（空）'}")
            continue

        tag = by_key[key]
        before = tag["weight"]

        if op == "drop":
            current = [t for t in current if t["key"] != key]
            del by_key[key]
            entry(shown, "dropped", f"删掉「{shown}」（原权重 {before}）",
                  before=before, after=None)
            continue

        delta = step if op == "more" else -step
        after = _clamp(before + delta)
        if after <= MIN_WEIGHT:
            current = [t for t in current if t["key"] != key]
            del by_key[key]
            entry(shown, "dropped", f"「{shown}」权重降到 {MIN_WEIGHT}，已从方向里移除",
                  before=before, after=None)
            continue
        tag["weight"] = after
        entry(shown, "applied", f"「{shown}」{before} → {after}",
              before=before, after=after)

    return current, report


# ---------------------------------------------------------------- 呈现

def axis_summary(tags) -> dict:
    """按轴计数。宿主据此判断方向是否只描了音乐、没写行为来源（或反之）。"""
    out = {SONIC: 0, CONTEXT: 0, UNSPECIFIED: 0}
    for t in tags or []:
        out[t.get("axis", UNSPECIFIED)] = out.get(t.get("axis", UNSPECIFIED), 0) + 1
    return out


def _mark(tag) -> str:
    w = tag["weight"]
    if w > BASE_WEIGHT:
        return f"{tag['label']} ↑{w:g}"
    if w < BASE_WEIGHT:
        return f"{tag['label']} ↓{w:g}"
    return tag["label"]


def render_tags(tags, language: str = "en") -> str:
    """一行展示串，直接给用户看。"""
    if not tags:
        return ""
    groups = [(SONIC, "sonic"), (CONTEXT, "context"), (UNSPECIFIED, None)]
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

    刻意把「这不是 brief」写进输出本身：宿主模型读到的就是带边界的指令，
    不靠外部文档提醒。
    """
    if not tags:
        return ""
    body = "；".join(
        f"{t['label']}（{'音乐' if t['axis'] == SONIC else '行为' if t['axis'] == CONTEXT else '未标轴'}，"
        f"侧重 {t['weight']:g}）" for t in tags)
    if language.lower().startswith("zh"):
        return (f"方向标签（约 {TARGET_TAG_COUNT} 个）：{body}。"
                f"这些标签是给用户的操纵面，**不是 brief**：原始需求与策展契约仍然优先，"
                f"冲突时以 brief 为准；行为类标签必须有真实收听证据支持。")
    return (f"Direction tags (~{TARGET_TAG_COUNT}): {body}. "
            f"These tags are a user-facing steering surface, **not the brief**: the original "
            f"request and the curation contract stay authoritative, and the brief wins any "
            f"conflict. Context tags must be backed by real listening evidence.")


def summary(tags, problems=None, report=None, language: str = "zh") -> str:
    """给 MCP 工具用的紧凑文本报告。"""
    lines = []
    if not tags:
        lines.append("方向标签：空。")
    else:
        lines.append(f"方向标签（{len(tags)} 个，目标约 {TARGET_TAG_COUNT} 个）：")
        for t in tags:
            lines.append(f"  · {t['label']}  [轴={t['axis']}  权重={t['weight']:g}]")
        counts = axis_summary(tags)
        lines.append(f"  轴分布：音乐 {counts[SONIC]} / 行为 {counts[CONTEXT]} / "
                     f"未标 {counts[UNSPECIFIED]}")
        lines.append(f"  展示：{render_tags(tags)}")
    if problems:
        lines.append("校验说明：")
        lines.extend(f"  ! {p}" for p in problems)
    if report:
        lines.append("方向调整：")
        for r in report:
            lines.append(f"  · [{r['status']}] {r['detail']}")
    if tags:
        lines.append("")
        lines.append(direction_note(tags, language))
    return "\n".join(lines)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向标签（playlist_tags）的离线单元测试。

这些测试盯住四件事：

1. `tag_key` 必须保留所有文字系统——用 `[^0-9a-z\\u4e00-\\u9fff]` 会把日文假名和
   韩文整个抹掉，这个仓库在别处踩过一次。
2. 调整是**记账**，必须确定、可解释、且对找不到的标签出声——用户说 more funk
   而方向里没有 funk 时，静默无效果是最坏的结果。
3. **没有数值权重。** 侧重只有 soften/neutral/boost 三档定性状态，渲染结果里
   不该出现任何数字：数字会被读成精度，而这里没有精度。
4. 方向标签不得被表述成 brief 的替代品，也不得成为选曲依据。

`TestReviewerRegressions` 专门钉住第一轮 review 报出的三个可复现缺陷。

跑：
    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import playlist_tags as pt  # noqa: E402


class TestTagKey(unittest.TestCase):
    def test_ascii_and_case(self):
        self.assertEqual(pt.tag_key("Synthwave"), pt.tag_key("synthwave"))
        self.assertEqual(pt.tag_key("night"), "night")

    def test_kana_and_hangul_survive(self):
        """真实误伤：ASCII+CJK 汉字区间会把假名和韩文整个抹掉，键变成空串。"""
        self.assertEqual(pt.tag_key("夜のドライブ"), "夜のドライブ")
        self.assertEqual(pt.tag_key("밤드라이브"), "밤드라이브")
        self.assertNotEqual(pt.tag_key("アイドル"), "")

    def test_punctuation_and_width_are_folded(self):
        self.assertEqual(pt.tag_key("high-rotation"), "highrotation")
        self.assertEqual(pt.tag_key("ＦＵＮＫ"), "funk")

    def test_empty(self):
        self.assertEqual(pt.tag_key(""), "")
        self.assertEqual(pt.tag_key(None), "")


class TestNormalizeTags(unittest.TestCase):
    def test_plain_strings_default_to_unspecified_and_are_reported(self):
        tags, problems = pt.normalize_tags(["synthwave", "night", "dark"])
        self.assertEqual([t["label"] for t in tags], ["synthwave", "night", "dark"])
        self.assertTrue(all(t["axis"] == pt.UNSPECIFIED for t in tags))
        self.assertTrue(all(t["emphasis"] == pt.NEUTRAL for t in tags))
        self.assertEqual(len(problems), 3)          # 每个都缺轴
        self.assertTrue(all("没写轴" in p for p in problems))

    def test_axis_prefix(self):
        tags, problems = pt.normalize_tags(
            ["sonic:synthwave"])
        self.assertEqual([t["axis"] for t in tags], [pt.SONIC])
        self.assertEqual(tags[0]["label"], "synthwave")
        self.assertEqual(problems, [])

    def test_axis_prefix_on_a_context_tag_without_evidence_is_reported(self):
        """`context:` 前缀只解决「轴」，不解决「证据」——两者都要。"""
        tags, problems = pt.normalize_tags(["context:in-library"])
        self.assertEqual(tags[0]["axis"], pt.CONTEXT)
        self.assertIsNone(tags[0]["evidence"])
        self.assertTrue(any("没写 evidence" in p for p in problems))

    def test_dict_form_with_emphasis(self):
        tags, problems = pt.normalize_tags([
            {"label": "funk", "axis": "sonic", "emphasis": "boost"},
            {"label": "disco", "axis": "sonic", "emphasis": "soften"},
        ])
        self.assertEqual([t["emphasis"] for t in tags], [pt.BOOST, pt.SOFTEN])
        self.assertEqual(problems, [])

    def test_unknown_emphasis_is_reported_and_neutralized(self):
        tags, problems = pt.normalize_tags([{"label": "funk", "emphasis": "very much"}])
        self.assertEqual(tags[0]["emphasis"], pt.NEUTRAL)
        self.assertTrue(any("看不懂" in p for p in problems))

    def test_legacy_numeric_weight_is_rejected_with_a_reason(self):
        """第一版用 0.0–2.0 小数权重；评审指出那是假精度。传 weight 要说清原因。"""
        tags, problems = pt.normalize_tags([{"label": "funk", "weight": 1.5}])
        self.assertEqual(tags[0]["emphasis"], pt.NEUTRAL)
        self.assertTrue(any("weight 已废弃" in p for p in problems))
        self.assertTrue(any("假精度" in p or "有精度" in p for p in problems))

    def test_duplicates_keep_the_first_and_report(self):
        tags, problems = pt.normalize_tags(
            ["funk", {"label": "FUNK", "emphasis": "boost"}])
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["emphasis"], pt.NEUTRAL)   # 保留先出现的那条
        self.assertTrue(any("重复" in p for p in problems))

    def test_conflicting_axes_keep_the_first_and_report(self):
        tags, problems = pt.normalize_tags(
            [{"label": "night", "axis": "sonic"}, {"label": "night", "axis": "context"}])
        self.assertEqual(tags[0]["axis"], pt.SONIC)
        self.assertTrue(any("两种轴" in p for p in problems))

    def test_over_the_cap_keeps_the_first_and_names_the_rest(self):
        items = [f"tag{i}" for i in range(pt.MAX_TAGS + 2)]
        tags, problems = pt.normalize_tags(items)
        self.assertEqual(len(tags), pt.MAX_TAGS)
        self.assertTrue(any("超过上限" in p for p in problems))
        self.assertTrue(any("tag8" in p for p in problems))

    def test_empty_and_none(self):
        self.assertEqual(pt.normalize_tags([])[0], [])
        self.assertEqual(pt.normalize_tags(None)[0], [])
        tags, problems = pt.normalize_tags(["", "   "])
        self.assertEqual(tags, [])
        self.assertEqual(len(problems), 2)

    def test_punctuation_only_label_is_dropped_not_kept(self):
        tags, problems = pt.normalize_tags(["!!!"])
        self.assertEqual(tags, [])
        self.assertTrue(any("空的" in p for p in problems))


class TestParseAdjustment(unittest.TestCase):
    def test_english_ops(self):
        self.assertEqual(pt.parse_adjustment("more funk")["op"], "more")
        self.assertEqual(pt.parse_adjustment("less disco")["op"], "less")
        self.assertEqual(pt.parse_adjustment("drop dark")["op"], "drop")
        self.assertEqual(pt.parse_adjustment("add ambient")["op"], "add")
        self.assertEqual(pt.parse_adjustment("more funk")["label"], "funk")

    def test_shorthand_signs(self):
        self.assertEqual(pt.parse_adjustment("+funk")["op"], "more")
        self.assertEqual(pt.parse_adjustment("-disco")["op"], "less")

    def test_chinese_ops(self):
        self.assertEqual(pt.parse_adjustment("多一点 funk")["op"], "more")
        self.assertEqual(pt.parse_adjustment("少一点disco")["op"], "less")
        self.assertEqual(pt.parse_adjustment("去掉 dark")["op"], "drop")
        self.assertEqual(pt.parse_adjustment("加上 ambient")["op"], "add")

    def test_multiword_label_is_kept_whole(self):
        self.assertEqual(pt.parse_adjustment("more heavy rotation")["label"],
                         "heavy rotation")

    def test_dict_form(self):
        adj = pt.parse_adjustment({"op": "more", "label": "funk"})
        self.assertEqual(adj, {"op": "more", "label": "funk"})

    def test_unparseable_returns_none(self):
        for bad in ("", "   ", None, "funk", "more", {"op": "more"}, 42):
            self.assertIsNone(pt.parse_adjustment(bad), bad)


class TestReviewerRegressions(unittest.TestCase):
    """第一轮 review 报出的三个可复现缺陷，钉死。"""

    # --- [P1] 操作词匹配缺少词边界 -------------------------------------

    def test_operator_words_need_a_word_boundary(self):
        """`startswith()` 会把普通句子篡改成操作 + 一段残词。"""
        for text in ("nothing but jazz", "downbeat", "morello"):
            self.assertIsNone(pt.parse_adjustment(text), text)

    def test_boundary_only_blocks_glued_letters(self):
        """加了边界之后，正常写法必须照旧可用。"""
        self.assertEqual(pt.parse_adjustment("no disco")["op"], "drop")
        self.assertEqual(pt.parse_adjustment("no disco")["label"], "disco")
        self.assertEqual(pt.parse_adjustment("up tempo")["op"], "more")
        self.assertEqual(pt.parse_adjustment("more funk!")["label"], "funk!")

    def test_the_shadowed_comment_is_now_true(self):
        """注释里写着「no 不会抢走 nothing」，第一版并没有实现，现在是事实。"""
        self.assertIsNone(pt.parse_adjustment("nothing"))
        self.assertEqual(pt.parse_adjustment("no thing")["label"], "thing")

    # --- [P2] add 绕过规范化边界 ---------------------------------------

    def test_add_with_no_usable_characters_is_rejected(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        out, report = pt.apply_adjustments(tags, ["add !!!"])
        self.assertEqual(len(out), 1)
        self.assertEqual(report[0]["status"], "rejected")
        self.assertTrue(all(t["key"] for t in out))      # 没有空 key 混进来

    def test_add_strips_the_axis_prefix(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        out, report = pt.apply_adjustments(tags, ["add context:recent-heavy-rotation"])
        added = [t for t in out if t["label"] == "recent-heavy-rotation"][0]
        self.assertEqual(added["axis"], pt.CONTEXT)
        self.assertEqual(report[0]["status"], "added")

    def test_add_dedupes_against_the_normalized_key(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        out, report = pt.apply_adjustments(tags, ["add FUNK"])
        self.assertEqual(len(out), 1)
        self.assertEqual(report[0]["status"], "already-present")


class TestApplyAdjustments(unittest.TestCase):
    @staticmethod
    def _tags():
        return pt.normalize_tags(["sonic:funk", "sonic:disco", "context:night"])[0]

    def test_more_and_less_shift_one_qualitative_level(self):
        tags, report = pt.apply_adjustments(self._tags(), ["more funk", "less disco"])
        got = {t["label"]: t["emphasis"] for t in tags}
        self.assertEqual(got["funk"], pt.BOOST)
        self.assertEqual(got["disco"], pt.SOFTEN)
        self.assertEqual(got["night"], pt.NEUTRAL)          # 没提到的不动
        self.assertTrue(all(r["status"] == "applied" for r in report))

    def test_more_is_idempotent_at_the_top(self):
        """只有三档，所以重复 more 到 boost 就该停住并说明。"""
        tags, report = pt.apply_adjustments(self._tags(), ["more funk", "more funk"])
        got = {t["label"]: t["emphasis"] for t in tags}
        self.assertEqual(got["funk"], pt.BOOST)
        self.assertEqual(report[-1]["status"], "at-max")

    def test_more_twice_from_soften_reaches_neutral_then_boost(self):
        tags = pt.normalize_tags([{"label": "funk", "emphasis": "soften"}])[0]
        tags, _ = pt.apply_adjustments(tags, ["more funk"])
        self.assertEqual(tags[0]["emphasis"], pt.NEUTRAL)
        tags, _ = pt.apply_adjustments(tags, ["more funk"])
        self.assertEqual(tags[0]["emphasis"], pt.BOOST)

    def test_less_from_soften_drops_the_tag(self):
        tags = pt.normalize_tags([{"label": "funk", "emphasis": "soften"}])[0]
        out, report = pt.apply_adjustments(tags, ["less funk"])
        self.assertEqual(out, [])
        self.assertEqual(report[0]["status"], "dropped")

    def test_less_twice_from_neutral_drops_the_tag(self):
        tags, report = pt.apply_adjustments(
            self._tags(), ["less disco", "less disco"])
        self.assertNotIn("disco", [t["label"] for t in tags])
        self.assertEqual(report[-1]["status"], "dropped")

    def test_drop_removes(self):
        tags, _ = pt.apply_adjustments(self._tags(), ["drop disco"])
        self.assertNotIn("disco", [t["label"] for t in tags])

    def test_add_beyond_the_cap_is_rejected_not_silently_dropped(self):
        items = [f"tag{i}" for i in range(pt.MAX_TAGS)]
        tags, report = pt.apply_adjustments(pt.normalize_tags(items)[0], ["add extra"])
        self.assertEqual(len(tags), pt.MAX_TAGS)
        self.assertEqual(report[0]["status"], "rejected")

    def test_unknown_label_is_reported_with_the_existing_labels(self):
        """用户说 more techno 而方向里没有 techno —— 必须说出来，不能静默无效果。"""
        tags, report = pt.apply_adjustments(self._tags(), ["more techno"])
        self.assertEqual(report[0]["status"], "unknown")
        self.assertIn("techno", report[0]["detail"])     # 点出没找到的那个
        self.assertIn("disco", report[0]["detail"])      # 并列出实际有的
        self.assertEqual(len(tags), 3)                   # 什么都没变

    def test_unparseable_adjustment_is_reported(self):
        _, report = pt.apply_adjustments(self._tags(), ["请让它更好听"])
        self.assertEqual(report[0]["status"], "unparsed")

    def test_report_keeps_the_users_own_wording(self):
        """修订记录要留原话，否则用户看不出自己说过什么。"""
        _, report = pt.apply_adjustments(self._tags(), ["多一点 funk", "less disco"])
        self.assertEqual([r["input"] for r in report], ["多一点 funk", "less disco"])

    def test_distinct_labels_commute(self):
        a, _ = pt.apply_adjustments(self._tags(), ["more funk", "less disco"])
        b, _ = pt.apply_adjustments(self._tags(), ["less disco", "more funk"])
        self.assertEqual([(t["label"], t["emphasis"]) for t in a],
                         [(t["label"], t["emphasis"]) for t in b])

    def test_no_adjustments_changes_nothing(self):
        tags, report = pt.apply_adjustments(self._tags(), [])
        self.assertEqual(len(tags), 3)
        self.assertEqual(report, [])

    def test_axis_survives_adjustment(self):
        tags, _ = pt.apply_adjustments(self._tags(), ["more night"])
        by = {t["label"]: t for t in tags}
        self.assertEqual(by["night"]["axis"], pt.CONTEXT)
        self.assertEqual(by["night"]["emphasis"], pt.BOOST)


class TestPresentation(unittest.TestCase):
    @staticmethod
    def _tags():
        return pt.normalize_tags([{"label": "funk", "axis": "sonic", "emphasis": "boost"},
                                  {"label": "disco", "axis": "sonic", "emphasis": "soften"},
                                  {"label": "night", "axis": "context"}])[0]

    def test_render_uses_words_not_numbers(self):
        out = pt.render_tags(self._tags(), "zh")
        self.assertIn("funk（强调）", out)
        self.assertIn("disco（弱化）", out)
        self.assertIn("night", out)
        self.assertIn("行为", out)
        self.assertFalse(any(ch.isdigit() for ch in out),
                         f"展示串里不该出现数字（会被读成精度）：{out}")

    def test_direction_note_has_no_decimal_precision(self):
        """「约 5 个」这种计数可以有；小数不行——小数会被读成权重精度。"""
        import re
        note = pt.direction_note(self._tags(), "zh")
        self.assertIsNone(re.search(r"\d+\.\d+", note), note)

    def test_render_empty(self):
        self.assertEqual(pt.render_tags([]), "")

    def test_axis_summary(self):
        tags, _ = pt.normalize_tags(["sonic:a", "context:b", "c"])
        self.assertEqual(pt.axis_summary(tags),
                         {pt.SONIC: 1, pt.CONTEXT: 1, pt.UNSPECIFIED: 1})

    def test_direction_note_states_the_three_layer_boundary(self):
        """边界必须是三层，缺一层就会自相矛盾。

        第一版写「永不参与选曲」，评审指出那让 steer 在语义上失效：用户说 more funk
        也没法改变歌单。所以现在要同时说清「参与 / 不是数值 / 不越权」。
        """
        zh = pt.direction_note(self._tags(), "zh")
        self.assertIn("定性补充", zh)
        self.assertIn("参与下一轮候选比较", zh)      # 参与
        self.assertIn("不是数值评分", zh)            # 不是数值
        self.assertIn("不能推翻", zh)                # 不越权
        self.assertIn("以 brief 为准", zh)
        en = pt.direction_note(self._tags(), "en")
        self.assertIn("qualitative supplement", en)
        self.assertIn("take part in the", en)
        self.assertIn("not a numeric score", en)
        self.assertIn("cannot override", en)

    def test_direction_note_names_what_to_lean_toward(self):
        zh = pt.direction_note(self._tags(), "zh")
        self.assertIn("funk", zh)
        self.assertIn("disco", zh)

    def test_direction_note_empty_for_no_tags(self):
        self.assertEqual(pt.direction_note([]), "")

    def test_summary_reports_problems_and_the_revision_record(self):
        tags, problems = pt.normalize_tags(["funk", "disco"])
        tags, report = pt.apply_adjustments(tags, ["more funk", "more techno"])
        text = pt.summary(tags, problems, report)
        self.assertIn("方向标签", text)
        self.assertIn("[unknown]", text)
        self.assertIn("没写轴", text)
        self.assertIn("定性补充", text)
        self.assertIn("修订记录", text)
        self.assertIn("侧重=", text)
        self.assertNotIn("权重", text)

    def test_summary_echoes_the_brief_verbatim_and_first(self):
        """评审要求「原始 brief 仍应始终可见且优先」。

        提示词路径里 brief 本来就在标签之上；这里管的是**调整路径**——用户隔一轮
        只说 more X 时，模型手上不该只剩方向说明。
        """
        tags, _ = pt.normalize_tags(["sonic:funk"])
        brief = "深夜开车听的那种，霓虹感，偏冷。不要 Any Artist 的任何东西。"
        text = pt.summary(tags, None, None, "zh", brief)
        self.assertIn(brief, text)                     # 原样，一字不改
        self.assertLess(text.index(brief), text.index("方向标签（1 个"))  # 出现在标签之前
        self.assertIn("始终优先", text)                 # 回显块的抬头
        self.assertIn("定性补充", text)                 # 方向说明的边界仍在

    def test_summary_without_brief_has_no_brief_block(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        text = pt.summary(tags, None, None, "zh", "")
        # 用回显块的抬头判断，而不是「原始 brief」子串——方向说明里本来就有这个词。
        self.assertNotIn("始终优先", text)
        self.assertNotIn("原始 brief（", text)

    def test_summary_brief_blank_string_is_ignored(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        text = pt.summary(tags, None, None, "zh", "   \n  ")
        self.assertNotIn("始终优先", text)


class TestContextEvidence(unittest.TestCase):
    """`context` 轴描述的是「用户在听什么」，必须能说出**可核对的**来源。

    [P1] 评审：A non-empty string is not evidence. 第一版只检查「非空字符串」，
    于是 `in-library` 配 `evidence: "am_top_played"` 照样通过——而那个调用根本证明不了
    歌单成员关系。所以来源改成结构化 provenance 并**按断言校验**；自由文本仍接受，
    但只当作**未经校验的来源自述**展示，不当作证据。
    """

    @staticmethod
    def _ctx(evidence=None):
        item = {"label": "recent-heavy-rotation", "axis": "context"}
        if evidence is not None:
            item["evidence"] = evidence
        return item

    @staticmethod
    def _structured(basis, call, ref=""):
        return {"basis": basis, "call": call, "ref": ref}

    @staticmethod
    def _membership(evidence):
        """in-library 是「歌单成员关系」类断言，用来测「来源撑不住断言」。"""
        return {"label": "in-library", "axis": "context", "evidence": evidence}

    # --- 结构化来源：按断言校验 -------------------------------------

    def test_matching_structured_evidence_is_declared_not_verified(self):
        """[P1] 结构化来源也只算**声明**：标签是自由文本，无法核对它与 basis 是否相符。

        评审的绕过例子是 `{"label":"in-library","basis":"play-count"}`——上一版一路通过
        还被渲染成「证据」。既然标签分类不了，就不能声称「已核实」。
        """
        tags, problems = pt.normalize_tags(
            [self._ctx(self._structured("recent-listening", "am_recently_played",
                                        "kind=tracks"))])
        self.assertEqual(tags[0]["evidence"]["kind"], "structured")
        self.assertEqual(len(problems), 1)
        self.assertIn("声明", problems[0])
        self.assertIn("无法判断", problems[0])
        self.assertIn("不要说成已经核对过", problems[0])

    def test_label_is_never_silently_matched_against_the_basis(self):
        """评审的绕过：`in-library` + `basis=play-count` 曾经完全无问题、还被当证据。"""
        tags, problems = pt.normalize_tags(
            [self._membership(self._structured("play-count", "am_top_played", "year-2026"))])
        self.assertTrue(problems, "结构化来源必须至少留下「声明而非已核实」的说明")
        out = pt.render_tags(tags, "zh")
        self.assertIn("未与标签核对", out)
        self.assertNotIn("证据：", out)

    def test_source_that_cannot_support_the_claim_is_rejected(self):
        """评审举的原例：`in-library` 配 `am_top_played` 撑不住这条断言。"""
        tags, problems = pt.normalize_tags(
            [self._membership(self._structured("playlist-membership", "am_top_played"))])
        self.assertEqual(len(tags), 1)                      # 接受但报出来
        self.assertTrue(any("撑不住" in p for p in problems), problems)

    def test_playlist_membership_needs_am_show_playlist(self):
        """[P1] 评审：am_list_playlists 只列歌单名/ID，证明不了曲目在不在里面。"""
        _, problems = pt.normalize_tags(
            [self._membership(self._structured("playlist-membership",
                                               "am_show_playlist", "p.abc123"))])
        self.assertFalse([p for p in problems if "撑不住" in p], problems)

    def test_list_playlists_is_rejected_as_membership_evidence(self):
        _, problems = pt.normalize_tags(
            [self._membership(self._structured("playlist-membership",
                                               "am_list_playlists", "p.abc123"))])
        self.assertTrue(any("撑不住" in p for p in problems), problems)
        self.assertTrue(any("am_show_playlist" in p for p in problems), problems)

    def test_missing_ref_is_rejected_with_what_to_record(self):
        """[P1] 不记调用参数就无法复核。"""
        _, problems = pt.normalize_tags(
            [self._membership(self._structured("playlist-membership", "am_show_playlist"))])
        self.assertTrue(any("没记 ref" in p for p in problems), problems)

    def test_recent_listening_may_not_cite_kind_added(self):
        """[P1] kind=added 是「最近入库」，不能当「最近在听」。"""
        _, problems = pt.normalize_tags(
            [self._ctx(self._structured("recent-listening", "am_recently_played",
                                        "kind=added"))])
        self.assertTrue(any("入库" in p for p in problems), problems)

    def test_derived_basis_is_flagged_as_a_conclusion(self):
        _, problems = pt.normalize_tags(
            [self._ctx(self._structured("derived", "am_top_played",
                                        "firstPlayed/lastPlayed × playCount"))])
        self.assertTrue(any("推出来" in p for p in problems), problems)

    def test_unknown_basis_is_reported(self):
        _, problems = pt.normalize_tags(
            [self._ctx(self._structured("vibes", "am_top_played", "x"))])
        self.assertTrue(any("basis" in p and "不认识" in p for p in problems), problems)

    def test_free_text_is_an_unverified_claim_not_evidence(self):
        tags, problems = pt.normalize_tags([self._ctx("am_top_played year-2026")])
        self.assertEqual(tags[0]["evidence"]["kind"], "claim")
        self.assertTrue(any("未经校验" in p for p in problems))
        self.assertIn("未校验", pt.render_tags(tags, "zh"))

    def test_claim_is_never_rendered_as_verified_evidence(self):
        tags, _ = pt.normalize_tags([self._ctx("trust me")])
        out = pt.render_tags(tags, "zh")
        self.assertIn("来源自述", out)
        self.assertNotIn("证据：", out)

    # --- 缺失与其它轴 ---------------------------------------------

    def test_context_without_evidence_is_accepted_but_reported(self):
        tags, problems = pt.normalize_tags([self._ctx()])
        self.assertEqual(len(tags), 1)                      # 不阻断
        self.assertTrue(any("没写 evidence" in p for p in problems))
        self.assertTrue(any("模型推断" in p for p in problems))

    def test_sonic_with_evidence_is_flagged_as_superfluous(self):
        tags, problems = pt.normalize_tags(
            [{"label": "funk", "axis": "sonic", "evidence": "am_top_played"}])
        self.assertIsNotNone(tags[0]["evidence"])
        self.assertTrue(any("不起支撑作用" in p for p in problems))

    def test_missing_evidence_shows_up_in_the_display_line(self):
        """用户有权看见哪个行为标签没有依据——藏起来才是问题。"""
        tags, _ = pt.normalize_tags([self._ctx()])
        self.assertIn("证据缺失", pt.render_tags(tags, "zh"))

    def test_direction_note_carries_the_structured_evidence(self):
        tags, _ = pt.normalize_tags(
            [self._ctx(self._structured("play-count", "am_top_played", "year-2026"))])
        note = pt.direction_note(tags, "zh")
        self.assertIn("play-count", note)
        self.assertIn("am_top_played", note)

    def test_direction_note_warns_about_missing_evidence(self):
        tags, _ = pt.normalize_tags([self._ctx()])
        note = pt.direction_note(tags, "zh")
        self.assertIn("没有证据来源", note)
        self.assertIn("不要说成用户事实", note)

    def test_direction_note_separates_claims_from_evidence(self):
        tags, _ = pt.normalize_tags([self._ctx("trust me")])
        note = pt.direction_note(tags, "zh")
        self.assertIn("未经校验", note)
        self.assertIn("自述", note)

    def test_english_direction_note_mentions_no_evidence(self):
        tags, _ = pt.normalize_tags([self._ctx()])
        self.assertIn("no evidence", pt.direction_note(tags, "en"))

    def test_summary_marks_missing_evidence(self):
        tags, problems = pt.normalize_tags([self._ctx()])
        text = pt.summary(tags, problems, None)
        self.assertIn("证据缺失", text)
        self.assertIn("无证据的行为标签", text)

    # --- [P2] 去重之后才算证据诊断 ---------------------------------

    def test_duplicate_that_later_supplies_evidence_leaves_no_stale_warning(self):
        """[P2] 评审：先出现无证据、后来的重复项补上，那条「没写 evidence」必须消失，
        否则同一条标签会同时显示有效证据和缺证据警告。"""
        tags, problems = pt.normalize_tags([
            {"label": "in-library", "axis": "context"},
            {"label": "IN-LIBRARY", "axis": "context",
             "evidence": self._structured("playlist-membership", "am_list_playlists")}])
        self.assertEqual(len(tags), 1)
        self.assertIsNotNone(tags[0]["evidence"])
        self.assertFalse([p for p in problems if "没写 evidence" in p], problems)

    def test_duplicate_prefers_structured_over_free_text(self):
        tags, _ = pt.normalize_tags([
            {"label": "in-library", "axis": "context", "evidence": "trust me"},
            {"label": "IN-LIBRARY", "axis": "context",
             "evidence": self._structured("playlist-membership", "am_list_playlists")}])
        self.assertEqual(tags[0]["evidence"]["kind"], "structured")

    def test_duplicate_keeps_exactly_one_evidence_diagnostic(self):
        """两条重复项各自缺证据，最终只应留下针对**最终记录**的一份说明。"""
        _, problems = pt.normalize_tags([
            {"label": "in-library", "axis": "context"},
            {"label": "in-library", "axis": "context"}])
        self.assertEqual(len([p for p in problems if "没写 evidence" in p]), 1)

    # --- add 路径 --------------------------------------------------

    def test_add_without_evidence_reports_it_in_the_revision_record(self):
        tags, _ = pt.normalize_tags(["sonic:funk"])
        out, report = pt.apply_adjustments(tags, ["add context:in-library"])
        self.assertEqual(report[0]["status"], "added")
        self.assertIn("没写 evidence", report[0]["detail"])
        added = [t for t in out if t["label"] == "in-library"][0]
        self.assertIsNone(added["evidence"])


class TestInputHygiene(unittest.TestCase):
    """自查发现的一类问题：**静默丢数据 / 静默改写**。

    这个仓库拒绝「看起来生效了、其实没有」的行为，所以下面每一条都既要**修**，
    也要**报**——修而不报同样会让人误判。
    """

    def test_a_bare_string_is_one_label_not_characters(self):
        """`for raw in items` 会把字符串**逐字符**拆成多个标签。"""
        tags, problems = pt.normalize_tags("funk")
        self.assertEqual([t["label"] for t in tags], ["funk"])
        self.assertTrue(any("strings" in p or "字符串" in p for p in problems))

    def test_control_characters_and_newlines_are_collapsed_and_reported(self):
        """标签会被原样插进 MCP 提示词，含换行的标签能凭空多出一行。"""
        tags, problems = pt.normalize_tags(["sonic:a\nb", {"label": "x\u0000y",
                                                          "axis": "sonic"}])
        self.assertEqual([t["label"] for t in tags], ["a b", "x y"])
        self.assertTrue(any("控制字符" in p for p in problems))
        self.assertNotIn("\n", pt.render_tags(tags, "zh"))

    def test_overlong_labels_are_truncated_and_reported(self):
        tags, problems = pt.normalize_tags([{"label": "z" * 5000, "axis": "sonic"}])
        self.assertEqual(len(tags[0]["label"]), pt.MAX_LABEL_LEN)
        self.assertTrue(any("过长" in p for p in problems))

    def test_dict_label_with_axis_prefix_is_split_like_the_string_form(self):
        """两种写法必须一致：`{"label": "context:x"}` 不能把前缀留在标签里。"""
        as_dict, _ = pt.normalize_tags([{"label": "context:in-library"}])
        as_str, _ = pt.normalize_tags(["context:in-library"])
        self.assertEqual(as_dict[0]["label"], as_str[0]["label"])
        self.assertEqual(as_dict[0]["axis"], pt.CONTEXT)

    def test_explicit_axis_wins_over_the_label_prefix(self):
        tags, _ = pt.normalize_tags([{"label": "context:x", "axis": "sonic"}])
        self.assertEqual(tags[0]["label"], "x")
        self.assertEqual(tags[0]["axis"], pt.SONIC)

    def test_dict_adjustment_carries_evidence_instead_of_dropping_it(self):
        """上一版把 dict 形式带的 evidence **直接丢掉**，报告也不提。"""
        tags, _ = pt.normalize_tags([{"label": "funk", "axis": "sonic"}])
        out, report = pt.apply_adjustments(tags, [
            {"op": "add", "label": "in-library", "axis": "context",
             "evidence": {"basis": "playlist-membership", "call": "am_show_playlist",
                          "ref": "p.x"}}])
        added = [t for t in out if t["label"] == "in-library"][0]
        self.assertEqual(added["evidence"]["kind"], "structured")
        self.assertIn("am_show_playlist", added["evidence"]["call"])

    def test_evidence_without_an_axis_is_flagged(self):
        """带 evidence 却没写轴 → 必须提示，而不是含混地当成 sonic。"""
        tags, _ = pt.normalize_tags([{"label": "funk", "axis": "sonic"}])
        _, report = pt.apply_adjustments(tags, [
            {"op": "add", "label": "in-library",
             "evidence": {"basis": "playlist-membership", "call": "am_show_playlist",
                          "ref": "p.x"}}])
        self.assertIn("没写轴", report[0]["detail"])

    def test_evidence_on_a_non_add_adjustment_is_reported_not_ignored(self):
        tags, _ = pt.normalize_tags(["context:in-library"])
        _, report = pt.apply_adjustments(tags, [
            {"op": "more", "label": "in-library", "evidence": "x"}])
        self.assertTrue(any(r["status"] == "note" and "只对 add 有意义" in r["detail"]
                            for r in report), report)


class TestPromptRendering(unittest.TestCase):
    """[P1] prompt 里公开了 tags 却从不读取 —— 用 review 当时复现的原例钉死。

    review 原话：『实测传入 `sonic:nocturnal` 后，渲染结果完全不包含它。
    调用方会以为方向已经生效，实际歌单不受影响。』
    """

    def setUp(self):
        import am_mcp_server as srv
        self.srv = srv

    def _render(self, **extra):
        args = {"description": "a late-night drive", "name": "n",
                "track_count": "20", "language": "zh"}
        args.update(extra)
        return self.srv._render_playlist_prompt(args)

    def test_tags_argument_reaches_the_rendered_prompt(self):
        text = self._render(tags="sonic:nocturnal")
        self.assertIn("nocturnal", text)
        self.assertIn("sonic", text)

    def test_tags_argument_is_rendered_with_axis_and_emphasis(self):
        text = self._render(tags="sonic:night, context:in-library")
        self.assertIn("night", text)
        self.assertIn("in-library", text)
        self.assertIn("axis=", text)
        self.assertIn("emphasis=", text)

    def test_prompt_states_the_three_layer_boundary(self):
        text = self._render(tags="sonic:night")
        self.assertIn("am_tag_directions", text)
        self.assertIn("qualitative supplement", text)        # 参与
        self.assertIn("take part in that next round", text)
        self.assertIn("not a numeric score", text)           # 不是数值
        self.assertIn("cannot override", text)               # 不越权

    def test_steering_window_precedes_the_final_write(self):
        """[P1] 评审：方向窗口原先排在 `dry_run=false` **之后**，用户第一次看到
        可调方向时歌单已经写入了。所以顺序必须是「预演 → 定方向 → 写入」。"""
        text = self._render(tags="sonic:night")
        steering = text.index("Settle the direction with the user BEFORE anything is written")
        preview = text.index("dry_run=true")
        write = text.index("dry_run=false")
        self.assertLess(preview, steering, "方向窗口应在预演之后")
        self.assertLess(steering, write, "方向窗口必须在最终写入之前")

    def test_prompt_requires_recuration_after_an_adjustment(self):
        """[P1] 调整之后必须重做比较与排序，否则 more funk 改不了任何东西。"""
        text = self._render()
        self.assertIn("redo the candidate comparison", text)
        self.assertIn("and dry-run again", text)
        self.assertIn("Continue only once the direction is settled", text)

    def test_prompt_requires_passing_the_original_brief(self):
        """[P2] brief 必须原样带回，否则「始终可见」只在调用方自愿时成立。"""
        text = self._render()
        self.assertIn("always passing `brief` = the user's original description verbatim", text)

    def test_prompt_states_the_steering_step_even_without_tags(self):
        """没传 tags 时也要有这一段——否则模型不会主动给方向。"""
        text = self._render()
        self.assertIn("am_tag_directions", text)
        self.assertNotIn("Direction tags the caller supplied", text)

    def test_prompt_never_renders_a_numeric_weight(self):
        """要断言的是「没有数值权重模型」，不是「文本里没有 weight 这个词」——
        策展契约本身会正当地写下「不要把 brief 压成……数值权重」这样的禁令，
        用子串匹配会把那句禁令也判成违规。所以只查渲染出来的方向段。"""
        import re
        text = self._render(tags="sonic:night")
        block = text[text.index("Direction tags the caller supplied"):
                     text.index("Use the Apple Music MCP tools")]
        self.assertNotIn("weight=", block)
        self.assertIsNone(re.search(r"\d+\.\d+", block), block)
        self.assertIn("emphasis=", block)

    def test_prompt_reports_validation_problems(self):
        """没写轴的标签要连问题一起渲染，让宿主能告诉用户。"""
        text = self._render(tags="night")
        self.assertIn("Validation notes", text)
        self.assertIn("没写轴", text)

    def test_prompt_validation_accepts_a_string_tags_argument(self):
        err = self.srv._validate_prompt_arguments(
            {"description": "x", "tags": "sonic:night"})
        self.assertIsNone(err)

    def test_prompt_validation_rejects_unknown_arguments(self):
        err = self.srv._validate_prompt_arguments(
            {"description": "x", "nope": "y"})
        self.assertIn("unknown prompt argument", err or "")


class TestBriefIsRequired(unittest.TestCase):
    """[P2] 评审：`brief` 可选等于没有保证——不传就回到「原始需求被挤出上下文」。

    所以强制点在**工具契约层**：schema 里 required，handler 再挡一次。
    而且测试要**走 handler**，不是直接调 `summary()`——评审明确要求这一点。
    """

    def setUp(self):
        import am_mcp_server as srv
        self.srv = srv

    def _tool(self):
        return next(t for t in self.srv.TOOLS if t["name"] == "am_tag_directions")

    def test_schema_marks_brief_required(self):
        self.assertIn("brief", self._tool()["inputSchema"]["required"])

    def test_validator_rejects_a_call_without_brief(self):
        err = self.srv._validate_tool_arguments(
            "am_tag_directions", {"tags": ["sonic:funk"]})
        self.assertIn("brief", err or "")

    def test_handler_refuses_a_blank_brief_even_below_the_schema(self):
        got = self.srv.t_tag_directions({"tags": ["sonic:funk"], "brief": "   "})
        self.assertIn("缺少必填参数 brief", got)

    def test_handler_echoes_the_brief_through_the_real_call_path(self):
        brief = "深夜开车听的那种，霓虹感，偏冷。"
        got = self.srv.t_tag_directions(
            {"tags": [{"label": "in-library", "axis": "context",
                       "evidence": "am_list_playlists"}],
             "adjustments": ["more in-library"], "brief": brief})
        self.assertIn(brief, got)
        self.assertIn("始终优先", got)
        self.assertIn("「more in-library」→ [applied]", got)


if __name__ == "__main__":
    unittest.main(verbosity=2)

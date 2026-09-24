#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向标签（playlist_tags）的离线单元测试。

这些测试盯住三件事：

1. `tag_key` 必须保留所有文字系统——用 `[^0-9a-z\\u4e00-\\u9fff]` 会把日文假名和
   韩文整个抹掉，这个仓库在别处踩过一次。
2. 调整是**记账**，必须确定、可解释、且对找不到的标签出声——用户说 more funk
   而方向里没有 funk 时，静默无效果是最坏的结果。
3. 方向标签不得被表述成 brief 的替代品：`direction_note` 里必须写明边界。

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
        self.assertEqual(len(problems), 3)          # 每个都缺轴
        self.assertTrue(all("没写轴" in p for p in problems))

    def test_axis_prefix(self):
        tags, problems = pt.normalize_tags(
            ["sonic:synthwave", "context:recent-heavy-rotation"])
        self.assertEqual([t["axis"] for t in tags], [pt.SONIC, pt.CONTEXT])
        self.assertEqual(tags[1]["label"], "recent-heavy-rotation")
        self.assertEqual(problems, [])

    def test_dict_form_with_weight(self):
        tags, problems = pt.normalize_tags([
            {"label": "funk", "axis": "sonic", "weight": 1.5},
            {"label": "disco", "axis": "sonic", "weight": 0.5},
        ])
        self.assertEqual([t["weight"] for t in tags], [1.5, 0.5])
        self.assertEqual(problems, [])

    def test_duplicates_merge_and_are_reported(self):
        tags, problems = pt.normalize_tags(["funk", {"label": "FUNK", "weight": 1.5}])
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["weight"], 1.5)    # 取较大权重
        self.assertTrue(any("重复" in p for p in problems))

    def test_conflicting_axes_keep_the_first_and_report(self):
        tags, problems = pt.normalize_tags(
            [{"label": "night", "axis": "sonic"}, {"label": "night", "axis": "context"}])
        self.assertEqual(tags[0]["axis"], pt.SONIC)
        self.assertTrue(any("两种轴" in p for p in problems))

    def test_weight_is_clamped(self):
        tags, _ = pt.normalize_tags(
            [{"label": "a", "weight": 99}, {"label": "b", "weight": -5}])
        self.assertEqual(tags[0]["weight"], pt.MAX_WEIGHT)
        self.assertEqual(tags[1]["weight"], pt.MIN_WEIGHT)

    def test_bad_weight_falls_back_to_base(self):
        tags, _ = pt.normalize_tags([{"label": "a", "weight": "loud"}])
        self.assertEqual(tags[0]["weight"], pt.BASE_WEIGHT)

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

    def test_explicit_amount(self):
        adj = pt.parse_adjustment("more funk 0.25")
        self.assertEqual(adj["label"], "funk")
        self.assertEqual(adj["amount"], 0.25)

    def test_dict_form(self):
        adj = pt.parse_adjustment({"op": "more", "label": "funk", "amount": 0.25})
        self.assertEqual(adj, {"op": "more", "label": "funk", "amount": 0.25})

    def test_unparseable_returns_none(self):
        for bad in ("", "   ", None, "funk", "more", {"op": "more"}, 42):
            self.assertIsNone(pt.parse_adjustment(bad), bad)


class TestApplyAdjustments(unittest.TestCase):
    @staticmethod
    def _tags():
        return pt.normalize_tags(["sonic:funk", "sonic:disco", "context:night"])[0]

    def test_more_and_less_move_weights(self):
        tags, report = pt.apply_adjustments(self._tags(), ["more funk", "less disco"])
        got = {t["label"]: t["weight"] for t in tags}
        self.assertEqual(got["funk"], 1.5)
        self.assertEqual(got["disco"], 0.5)
        self.assertEqual(got["night"], 1.0)         # 没提到的不动
        self.assertTrue(all(r["status"] == "applied" for r in report))

    def test_less_that_reaches_zero_drops_the_tag(self):
        tags, report = pt.apply_adjustments(
            self._tags(), ["less disco", "less disco"])
        self.assertNotIn("disco", [t["label"] for t in tags])
        self.assertEqual(report[-1]["status"], "dropped")

    def test_drop_removes(self):
        tags, _ = pt.apply_adjustments(self._tags(), ["drop disco"])
        self.assertNotIn("disco", [t["label"] for t in tags])

    def test_add_appends(self):
        tags, report = pt.apply_adjustments(self._tags(), ["add ambient"])
        self.assertIn("ambient", [t["label"] for t in tags])
        self.assertEqual(report[0]["status"], "added")

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

    def test_more_clamps_at_the_ceiling(self):
        tags, _ = pt.apply_adjustments(pt.normalize_tags(
            [{"label": "funk", "weight": 1.9}])[0], ["more funk", "more funk"])
        self.assertEqual(tags[0]["weight"], pt.MAX_WEIGHT)

    def test_distinct_labels_commute(self):
        a, _ = pt.apply_adjustments(self._tags(), ["more funk", "less disco"])
        b, _ = pt.apply_adjustments(self._tags(), ["less disco", "more funk"])
        self.assertEqual([(t["label"], t["weight"]) for t in a],
                         [(t["label"], t["weight"]) for t in b])

    def test_no_adjustments_changes_nothing(self):
        tags, report = pt.apply_adjustments(self._tags(), [])
        self.assertEqual(len(tags), 3)
        self.assertEqual(report, [])

    def test_axis_survives_adjustment(self):
        tags, _ = pt.apply_adjustments(self._tags(), ["more night"])
        by = {t["label"]: t for t in tags}
        self.assertEqual(by["night"]["axis"], pt.CONTEXT)
        self.assertEqual(by["night"]["weight"], 1.5)


class TestPresentation(unittest.TestCase):
    def test_render_marks_emphasis(self):
        tags, _ = pt.normalize_tags([{"label": "funk", "axis": "sonic", "weight": 1.5},
                                     {"label": "disco", "axis": "sonic", "weight": 0.5},
                                     {"label": "night", "axis": "context"}])
        out = pt.render_tags(tags)
        self.assertIn("funk ↑1.5", out)
        self.assertIn("disco ↓0.5", out)
        self.assertIn("night", out)
        self.assertIn("context", out)

    def test_render_empty(self):
        self.assertEqual(pt.render_tags([]), "")

    def test_axis_summary(self):
        tags, _ = pt.normalize_tags(["sonic:a", "context:b", "c"])
        self.assertEqual(pt.axis_summary(tags),
                         {pt.SONIC: 1, pt.CONTEXT: 1, pt.UNSPECIFIED: 1})

    def test_direction_note_keeps_the_boundary(self):
        """方向说明必须自带「不是 brief」的边界，否则宿主模型会拿它当需求。"""
        tags, _ = pt.normalize_tags(["sonic:funk", "context:night"])
        zh = pt.direction_note(tags, "zh")
        self.assertIn("不是 brief", zh)
        self.assertIn("以 brief 为准", zh)
        en = pt.direction_note(tags, "en")
        self.assertIn("not the brief", en)

    def test_direction_note_empty_for_no_tags(self):
        self.assertEqual(pt.direction_note([]), "")

    def test_summary_reports_problems_and_adjustments(self):
        tags, problems = pt.normalize_tags(["funk", "disco"])
        tags, report = pt.apply_adjustments(tags, ["more funk", "more techno"])
        text = pt.summary(tags, problems, report)
        self.assertIn("方向标签", text)
        self.assertIn("[unknown]", text)
        self.assertIn("没写轴", text)
        self.assertIn("不是 brief", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相邻规则（playlist_core）的单元测试，以及"规则只能有一份定义"的结构性保证。

背景：体检器和优化器**曾经各自实现了一遍**这四条规则，而且"慢歌"的阈值不同
（体检器用 tempo 的 25 分位，优化器用固定 100BPM）。结果是工具用一套定义诊断
问题、用另一套定义修复问题。这些测试防止那件事重演。

跑：
    python -m unittest discover -s tests -v
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import playlist_core as core  # noqa: E402


def P(bpm, key="8B", energy=0.5, name="t"):
    return {"name": name, "bpm": bpm, "key": key, "energy": energy}


class TestCheckPair(unittest.TestCase):
    """每条规则单独触发，断言命中集合恰好只有它。"""

    def test_clean_pair_hits_nothing(self):
        # 120→125BPM（调性不兼容，所以不算"同时相似"）、能量相同、都不是慢歌
        self.assertEqual(core.check_pair(P(120, "8B"), P(125, "3A")), set())

    def test_two_slow(self):
        self.assertEqual(core.check_pair(P(95, "8B"), P(95, "3A")), {"two_slow"})

    def test_small_drop(self):
        self.assertEqual(core.check_pair(P(100, "8B"), P(95, "3A")), {"small_drop"})

    def test_both_similar(self):
        self.assertEqual(core.check_pair(P(120, "8B"), P(120, "8A")), {"both_similar"})

    def test_big_jump(self):
        self.assertEqual(core.check_pair(P(80, "8B"), P(130, "3A")), {"big_jump"})

    def test_energy_clash(self):
        self.assertEqual(core.check_pair(P(120, "8B", 0.9), P(120, "3A", 0.3)),
                         {"energy_clash"})

    def test_missing_features_yield_no_rules(self):
        """没有特征就不该凭空惩罚——这是四个规则共同的边界条件。"""
        for a, b in ((None, P(95)), (P(95), None), (P(0), P(0)),
                     (P(None), P(95)), (P(95), P(None))):
            self.assertEqual(core.check_pair(a, b), set(), f"{a} / {b}")

    def test_rule_names_match_the_weight_table(self):
        """core 的规则名必须和优化器的权重表键名一致，
        否则"命中了哪条"和"扣多少分"就对不上了。"""
        import playlist_optimize as po
        self.assertEqual(set(po.WEIGHTS), set(core.RULES))

    def test_every_rule_has_a_label(self):
        for r in core.RULES:
            self.assertIn(r, core.RULE_LABELS)
            self.assertTrue(core.RULE_LABELS[r].strip())


class TestScanAdjacency(unittest.TestCase):
    def test_position_is_one_based_on_the_second_track(self):
        seq = [P(95, "8B"), P(95, "3A"), P(120, "3A")]
        hits = core.scan_adjacency(seq)
        self.assertEqual([p for p, _ in hits["two_slow"]], [2])

    def test_result_always_covers_every_rule(self):
        self.assertEqual(set(core.scan_adjacency([P(95), P(95)])), set(core.RULES))

    def test_short_sequences(self):
        for seq in ([], [P(95)]):
            hits = core.scan_adjacency(seq)
            self.assertTrue(all(v == [] for v in hits.values()))

    def test_details_carry_the_percentage(self):
        _, d = core.scan_adjacency([P(100, "8B"), P(95, "3A")])["small_drop"][0]
        self.assertAlmostEqual(d["pct"], -5.0, places=6)


class TestSlowCutIsAbsolute(unittest.TestCase):
    def test_independent_of_input(self):
        """刻意与输入无关：优化器要在退火过程中对同一序列反复求值，
        阈值若随当前排列漂移，cost 就不稳定，退火收敛不到确定结果。"""
        self.assertEqual(core.slow_cut(), core.SLOW_BPM)
        self.assertEqual(core.slow_cut([60, 61, 62]), core.SLOW_BPM)
        self.assertEqual(core.slow_cut([140, 150, 155]), core.SLOW_BPM)

    def test_all_slow_playlist_flags_every_pair(self):
        """已知且刻意的后果：整张都是慢歌时，每一对相邻都会命中 two_slow。
        那是**真实的**（确实一路慢下去），但要意识到这是定义使然，
        不要把它当成排序失败。"""
        seq = [P(80, "8B", name=f"s{i}") for i in range(5)]
        hits = core.scan_adjacency(seq)
        self.assertEqual(len(hits["two_slow"]), 4)


class TestSingleSourceOfTruth(unittest.TestCase):
    """四条相邻规则只能有一份定义。"""

    def test_both_consumers_delegate_to_core(self):
        flow = (ROOT / "playlist_flow.py").read_text(encoding="utf-8")
        opt = (ROOT / "playlist_optimize.py").read_text(encoding="utf-8")
        self.assertIn("scan_adjacency", flow, "体检器必须走 core.scan_adjacency")
        self.assertIn("check_pair", opt, "优化器必须走 core.check_pair")

    def test_thresholds_are_not_redefined_elsewhere(self):
        """阈值散落在别处，就等于又埋了一套定义。"""
        for other in ("playlist_flow.py", "playlist_optimize.py"):
            src = (ROOT / other).read_text(encoding="utf-8")
            for name in ("SLOW_BPM", "SMALL_DROP_PCT", "SIMILAR_PCT",
                         "BIG_JUMP_PCT", "ENERGY_CLASH"):
                self.assertIsNone(re.search(rf"^{name}\s*=", src, re.M),
                                  f"{other} 里不该再定义 {name}")

    def test_core_is_platform_neutral(self):
        """playlist_core 必须零项目依赖、零第三方依赖——
        接第二个音乐平台时这一层要逐字不变。"""
        src = (ROOT / "playlist_core.py").read_text(encoding="utf-8")
        mods = {m.group(1).split(".")[0]
                for m in re.finditer(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)}
        self.assertEqual(mods - {"__future__", "re", "statistics"}, set(),
                         f"playlist_core 依赖了不该依赖的东西：{mods}")


class TestShapeTargets(unittest.TestCase):
    """目标形状（"朝哪个形状排"）—— 与形状识别共用 ARCHETYPES 那一份曲线。"""

    def test_short_names_resolve(self):
        for short in core.SHAPE_ALIASES:
            self.assertIn(core.resolve_shape(short), core.ARCHETYPES)

    def test_full_keys_also_accepted(self):
        for full in core.ARCHETYPES:
            self.assertEqual(core.resolve_shape(full), full)

    def test_unknown_name_raises_and_lists_options(self):
        with self.assertRaises(ValueError) as cm:
            core.resolve_shape("nope")
        self.assertIn("cinderella", str(cm.exception))

    def test_five_points_returns_the_ideal_curve(self):
        """5 点以内插 5 点必须原样返回，否则"朝某个形状排"本身就是偏的。"""
        for short, full in core.SHAPE_ALIASES.items():
            self.assertEqual(core.shape_target(short, 5), core.ARCHETYPES[full])

    def test_endpoints_are_preserved_when_interpolating(self):
        for short, full in core.SHAPE_ALIASES.items():
            ideal = core.ARCHETYPES[full]
            for n in (2, 3, 7, 30, 45):
                t = core.shape_target(short, n)
                self.assertEqual(len(t), n)
                self.assertAlmostEqual(t[0], ideal[0], places=9, msg=f"{short}/{n}")
                self.assertAlmostEqual(t[-1], ideal[-1], places=9, msg=f"{short}/{n}")

    def test_targets_stay_in_unit_range(self):
        for short in core.SHAPE_ALIASES:
            for n in (1, 2, 5, 13, 60):
                for v in core.shape_target(short, n):
                    self.assertGreaterEqual(v, 0.0)
                    self.assertLessEqual(v, 1.0)

    def test_degenerate_lengths(self):
        self.assertEqual(core.shape_target("cinderella", 0), [])
        self.assertEqual(len(core.shape_target("cinderella", 1)), 1)

    def test_tempo_target_is_inverted_u(self):
        t = core.tempo_target(5)
        self.assertAlmostEqual(t[0], 0.0)
        self.assertAlmostEqual(t[2], 1.0)          # 峰值在中间
        self.assertAlmostEqual(t[-1], 0.0)

    def test_tempo_target_does_not_depend_on_shape(self):
        """tempo 的目标只随长度变。它反映"快的放中段"这条排序惯例，
        和情绪走向是两件事，不该被搅在一起。"""
        self.assertEqual(core.tempo_target(9), core.tempo_target(9))
        import inspect
        self.assertEqual(list(inspect.signature(core.tempo_target).parameters), ["n"])

    def test_tempo_target_degenerate(self):
        self.assertEqual(core.tempo_target(0), [])
        self.assertEqual(core.tempo_target(1), [0.5])


class TestCoverageFunnel(unittest.TestCase):
    """特征覆盖漏斗：每一层**为什么**掉，都要能说出来。

    以前这是一个 `if not f or f.get("_miss") or "tempo" not in f: continue`——
    三种完全不同的原因压成一个笼统的"没特征"。接第二个平台时这个区别要命：
    网易云 / QQ 不返回 ISRC，no-isrc 会从 12% 逼近 100%，而那是换特征源
    **也解决不了**的，跟"特征源没收录"正好相反。
    """

    def test_each_stage(self):
        self.assertEqual(core.classify_coverage(has_id=False), "no-id")
        self.assertEqual(core.classify_coverage(has_meta=False), "no-meta")
        self.assertEqual(core.classify_coverage(isrc=None), "no-isrc")
        self.assertEqual(core.classify_coverage(isrc="X", in_cache=False), "not-in-cache")
        self.assertEqual(core.classify_coverage(isrc="X", feat={"_miss": True}), "source-miss")
        self.assertEqual(core.classify_coverage(isrc="X", feat={"energy": 0.5}), "no-features")
        self.assertEqual(core.classify_coverage(isrc="X", feat={"tempo": 120}), "ok")

    def test_no_isrc_outranks_source_miss(self):
        """顺序不能重排。缺 ISRC 是硬边界（换源无用），源没收录是可修的。"""
        self.assertEqual(core.classify_coverage(isrc=None, in_cache=False, feat=None),
                         "no-isrc")

    def test_meta_outranks_isrc(self):
        self.assertEqual(core.classify_coverage(has_meta=False, isrc=None), "no-meta")

    def test_vocabulary_and_labels_agree(self):
        for stage in core.COVERAGE_STAGES:
            self.assertIn(stage, core.COVERAGE_LABELS)
        self.assertEqual(core.COVERAGE_STAGES[-1], "ok", "ok 必须是最后一层")

    def test_every_declared_stage_is_reachable(self):
        produced = {
            core.classify_coverage(has_id=False),
            core.classify_coverage(has_meta=False),
            core.classify_coverage(isrc=None),
            core.classify_coverage(isrc="X", in_cache=False),
            core.classify_coverage(isrc="X", feat={"_miss": True}),
            core.classify_coverage(isrc="X", feat={}),
            core.classify_coverage(isrc="X", feat={"tempo": 1}),
        }
        self.assertEqual(produced, set(core.COVERAGE_STAGES))


class TestCoverageReport(unittest.TestCase):
    def test_percentage_and_reasons(self):
        txt = core.coverage_report({"ok": 88, "no-isrc": 7, "source-miss": 5}, 100)
        self.assertIn("88/100", txt)
        self.assertIn("88%", txt)
        self.assertIn("7 首", txt)
        self.assertIn("ISRC", txt)

    def test_warns_when_coverage_is_low(self):
        """这是重点：覆盖率低的时候，报告里的 cost 只描述了一部分曲目。"""
        txt = core.coverage_report({"ok": 60, "no-isrc": 40}, 100)
        self.assertIn("⚠️", txt)
        self.assertIn("只描述", txt)

    def test_no_warning_when_coverage_is_healthy(self):
        self.assertNotIn("⚠️", core.coverage_report({"ok": 98, "source-miss": 2}, 100))

    def test_zero_total_does_not_divide_by_zero(self):
        self.assertIn("没有曲目", core.coverage_report({}, 0))

    def test_missing_keys_are_treated_as_zero(self):
        self.assertIn("50/100", core.coverage_report({"ok": 50}, 100))


class TestMarkerHits(unittest.TestCase):
    """通用标记词匹配：拉丁词整词、CJK 子串。"""

    def test_latin_words_match_whole_only(self):
        words = ("live", "instrumental")
        self.assertEqual(core.marker_hits("Alive", words, ()), [])
        self.assertEqual(core.marker_hits("Olive Tree", words, ()), [])
        self.assertEqual(core.marker_hits("Delivery", words, ()), [])

    def test_latin_markers_hit(self):
        self.assertEqual(core.marker_hits("Song (Live)", ("live",), ()), ["live"])
        self.assertEqual(core.marker_hits("Song Instrumental", ("instrumental",), ()),
                         ["instrumental"])

    def test_cjk_markers_match_as_substring(self):
        self.assertEqual(core.marker_hits("某曲 现场版", (), ("现场",)), ["现场"])

    def test_empty_input(self):
        self.assertEqual(core.marker_hits("", ("live",), ("现场",)), [])
        self.assertEqual(core.marker_hits(None, ("live",), ("现场",)), [])


class TestFoldArtifactGating(unittest.TestCase):
    """折叠把一首歌推过「慢歌」阈值时，tempo 类规则不该把幽灵当事实。

    背景：`fold_tempo` 是取模映射，所以不保序。真实误伤——一首 160.1BPM 的曲子
    被折成 80，和同样被折的 176BPM 曲子一起被判「两首慢歌相邻」；而它和 150BPM
    的邻居（150 原样保留）被判「BPM 无理由大跳 -47%」。两条都是折叠造出来的。
    """

    @staticmethod
    def F(raw, folded, key="8B", energy=0.5):
        return {"name": "t", "bpm": folded, "raw_bpm": raw, "key": key, "energy": energy}

    def test_crossing_is_detected(self):
        self.assertTrue(core.fold_crosses_slow_cut(self.F(160.1, 80.0)))
        self.assertTrue(core.fold_crosses_slow_cut(self.F(176.0, 88.0)))
        # 向上折也可能跨线：55 被加倍成 110，从慢变快
        self.assertTrue(core.fold_crosses_slow_cut(self.F(55, 110.0)))

    def test_no_crossing_when_fold_keeps_the_side(self):
        self.assertFalse(core.fold_crosses_slow_cut(self.F(150.0, 150.0)))
        self.assertFalse(core.fold_crosses_slow_cut(self.F(82.5, 82.5)))
        self.assertFalse(core.fold_crosses_slow_cut(self.F(89.6, 89.6)))

    def test_missing_raw_bpm_is_backward_compatible(self):
        """老调用方不给 raw_bpm 时一律不判——行为必须与从前一致。"""
        self.assertFalse(core.fold_crosses_slow_cut(P(80)))
        self.assertFalse(core.fold_crosses_slow_cut(None))
        self.assertFalse(core.fold_crosses_slow_cut({"bpm": 80}))
        self.assertFalse(core.fold_crosses_slow_cut({"bpm": 0, "raw_bpm": 0}))

    def test_phantom_two_slow_is_suppressed(self):
        """160.1→176 生值都是快歌；折叠成 80→88 后被误报成两首慢歌。"""
        self.assertEqual(core.check_pair(self.F(160.1, 80.0), self.F(176.0, 88.0)), set())

    def test_phantom_big_jump_is_suppressed(self):
        """150→160.1 生值只差 7%；折叠成 150→80 后被误报成大跳 -47%。"""
        self.assertEqual(core.check_pair(self.F(150.0, 150.0), self.F(160.1, 80.0)), set())

    def test_genuine_two_slow_still_reported(self):
        """真的两首慢歌（折叠没动它们）照旧要报。"""
        self.assertEqual(core.check_pair(self.F(82.5, 82.5), self.F(89.6, 89.6)),
                         {"two_slow"})

    def test_energy_clash_survives_the_gate(self):
        """energy_clash 不看 tempo，扣留 tempo 判断时它必须照常生效。"""
        got = core.check_pair(self.F(160.1, 80.0, "8B", 0.9),
                              self.F(176.0, 88.0, "3A", 0.3))
        self.assertEqual(got, {"energy_clash"})

    def test_without_raw_bpm_the_old_rules_still_fire(self):
        self.assertEqual(core.check_pair(P(80, "8B"), P(130, "3A")), {"big_jump"})
        self.assertEqual(core.check_pair(P(95, "8B"), P(95, "3A")), {"two_slow"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

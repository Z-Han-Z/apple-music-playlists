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
        self.assertEqual(mods - {"__future__", "statistics"}, set(),
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

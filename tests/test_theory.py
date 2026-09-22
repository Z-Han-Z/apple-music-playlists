#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音乐理论层的单元测试（Camelot / BPM 折叠 / 弧线形状）。

**全部离线**，不碰网络、不需要 token。这是本项目测试的基线：
这些函数是"好听"判断的数学内核，将来接第二个音乐平台时它们必须逐字保持不变，
所以先用测试把当前行为钉死。

跑：
    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import playlist_flow as pf  # noqa: E402


class TestFoldTempo(unittest.TestCase):
    """BPM 倍频折叠：同一首歌可能被估成 90 或 180，比较前必须折进 [70,160)。"""

    def test_in_range_untouched(self):
        self.assertEqual(pf.fold_tempo(90), 90.0)
        self.assertEqual(pf.fold_tempo(120), 120.0)
        self.assertEqual(pf.fold_tempo(70), 70.0)
        self.assertEqual(pf.fold_tempo(159.9), 159.9)

    def test_halved_down(self):
        self.assertEqual(pf.fold_tempo(180), 90.0)
        self.assertEqual(pf.fold_tempo(160), 80.0)
        self.assertEqual(pf.fold_tempo(320), 80.0)

    def test_doubled_up(self):
        self.assertEqual(pf.fold_tempo(45), 90.0)
        self.assertEqual(pf.fold_tempo(69), 138.0)
        self.assertEqual(pf.fold_tempo(20), 80.0)

    def test_zero_and_negative_and_none(self):
        self.assertEqual(pf.fold_tempo(0), 0.0)
        self.assertEqual(pf.fold_tempo(-5), 0.0)
        self.assertEqual(pf.fold_tempo(None), 0.0)

    def test_octave_equivalents_outside_range_collide(self):
        """折叠存在的理由：倍频关系应落到同一个值，否则"两首慢歌"会误报。"""
        self.assertEqual(pf.fold_tempo(90), pf.fold_tempo(180))
        self.assertEqual(pf.fold_tempo(85), pf.fold_tempo(170))
        self.assertEqual(pf.fold_tempo(45), pf.fold_tempo(90))
        self.assertEqual(pf.fold_tempo(20), pf.fold_tempo(80))

    def test_fold_range_is_wider_than_one_octave_by_design(self):
        """**已知且有意的局限**：折叠区间是 [70,160)，宽 160/70 ≈ 2.29 个倍频，
        比一个八度宽——所以**两边都落在区间内**的倍频对不会被合并：75 和 150 保持不同。

        这不是疏忽。要合并它们就得把区间收成一个真正的八度（如 [80,160)），
        但那会把 70~79 BPM 的歌推到 140~158，于是**真正慢的歌会被判成快的**——
        而"两首慢歌相邻"这条规则恰恰依赖慢歌留在慢的区间里。
        感知正确性比倍频完美性更重要，所以维持现状。
        """
        self.assertEqual(pf.fold_tempo(75), 75.0)
        self.assertEqual(pf.fold_tempo(150), 150.0)
        self.assertNotEqual(pf.fold_tempo(75), pf.fold_tempo(150))

    def test_result_always_in_range(self):
        for raw in (30, 55, 70, 69.9, 100, 159.9, 160, 200, 400):
            got = pf.fold_tempo(raw)
            self.assertTrue(70 <= got < 160, f"{raw} → {got} 落到了 [70,160) 之外")


class TestCamelot(unittest.TestCase):
    def test_known_mappings(self):
        # 标准 Camelot：C 大调 = 8B，A 小调 = 8A，C 小调 = 5A，A 大调 = 11B
        self.assertEqual(pf.camelot(0, 1), "8B")
        self.assertEqual(pf.camelot(9, 0), "8A")
        self.assertEqual(pf.camelot(0, 0), "5A")
        self.assertEqual(pf.camelot(9, 1), "11B")

    def test_out_of_range_is_question_mark(self):
        self.assertEqual(pf.camelot(99, 0), "?")
        self.assertEqual(pf.camelot(-1, 1), "?")

    def test_all_24_codes_are_distinct(self):
        """12 个半音 × 大小调 = 24 个码且互不重复，这是 Camelot 轮的基本性质。"""
        codes = [pf.camelot(k, m) for k in range(12) for m in (0, 1)]
        self.assertEqual(len(codes), 24)
        self.assertEqual(len(set(codes)), 24)
        self.assertNotIn("?", codes)


class TestHarmonicOk(unittest.TestCase):
    def test_same_code(self):
        self.assertTrue(pf.harmonic_ok("8B", "8B"))

    def test_same_number_swaps_letter(self):
        self.assertTrue(pf.harmonic_ok("8B", "8A"))

    def test_adjacent_number_same_letter(self):
        self.assertTrue(pf.harmonic_ok("8A", "9A"))
        self.assertTrue(pf.harmonic_ok("8A", "7A"))

    def test_wraparound_1_and_12(self):
        self.assertTrue(pf.harmonic_ok("1A", "12A"))
        self.assertTrue(pf.harmonic_ok("12B", "1B"))

    def test_not_harmonic(self):
        self.assertFalse(pf.harmonic_ok("9A", "3A"))
        self.assertFalse(pf.harmonic_ok("8B", "9A"))
        self.assertFalse(pf.harmonic_ok("1A", "3A"))

    def test_unknown_never_harmonic(self):
        self.assertFalse(pf.harmonic_ok("?", "8B"))
        self.assertFalse(pf.harmonic_ok("8B", "?"))

    def test_symmetric(self):
        for a, b in [("8B", "9B"), ("5A", "5B"), ("12A", "1A"), ("2A", "7B")]:
            self.assertEqual(pf.harmonic_ok(a, b), pf.harmonic_ok(b, a))


class TestClassifyShape(unittest.TestCase):
    def test_archetypes_self_classify(self):
        """六种叙事弧的理想曲线，每一种都必须被认成自己（自检 6/6）。"""
        for name, ideal in pf.ARCHETYPES.items():
            got, _, _ = pf.classify_shape(list(ideal))
            self.assertEqual(got, name, f"{name} 被判成了 {got}")

    def test_archetypes_are_min0_max1(self):
        """理想曲线必须已归一化到 [0,1]——classify_shape 会把实际曲线 norm 到这个区间，
        两边不同尺度的话 MSE 比较就是错的。"""
        for name, ideal in pf.ARCHETYPES.items():
            self.assertAlmostEqual(min(ideal), 0.0, msg=name)
            self.assertAlmostEqual(max(ideal), 1.0, msg=name)

    def test_real_six_movement_curve_is_cinderella(self):
        """实测那张六幕歌单的五段 valence 均值。这条锁住当时报告里的数字，
        也防止有人把 5 段切分改回 3 段（3 段会把它误判成 Icarus）。
        """
        segs_in = [0.47, 0.83, 0.73, 0.41, 0.66]
        got, segs, scores = pf.classify_shape(segs_in)
        self.assertEqual(got, "Cinderella（起-落-起）")
        self.assertAlmostEqual(scores["Cinderella（起-落-起）"], 0.084, places=2)
        self.assertAlmostEqual(scores["Icarus（起-落）"], 0.169, places=2)
        self.assertLess(scores["Cinderella（起-落-起）"], scores["Icarus（起-落）"])

    def test_monotonic_rising_is_rags_to_riches(self):
        vals = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        got, _, _ = pf.classify_shape(vals)
        self.assertEqual(got, "Rags to riches（持续上升）")

    def test_monotonic_falling_is_tragedy(self):
        vals = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        got, _, _ = pf.classify_shape(vals)
        self.assertEqual(got, "Tragedy（持续下降）")

    def test_always_returns_five_segments(self):
        for n in (5, 6, 7, 10, 45, 47):
            _, segs, _ = pf.classify_shape([i / n for i in range(n)])
            self.assertEqual(len(segs), 5, f"n={n} 时段数不是 5")


class TestNorm(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(pf.norm([1, 2, 3]), [0.0, 0.5, 1.0])

    def test_all_equal_does_not_divide_by_zero(self):
        self.assertEqual(pf.norm([5, 5, 5]), [0.5, 0.5, 0.5])

    def test_output_in_unit_range(self):
        out = pf.norm([-3, 0, 7, 100])
        self.assertEqual(min(out), 0.0)
        self.assertEqual(max(out), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

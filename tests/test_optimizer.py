#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排序器（playlist_optimize.py）的单元测试。**全部离线**。

这里逐条隔离验证四项"硬性相邻规则"的惩罚项。隔离很重要：
如果两条规则同时触发而测试只断言总数，改动其中一条会被另一条掩盖。

跑：
    python -m unittest discover -s tests -v
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import playlist_core as core  # noqa: E402
import playlist_optimize as po  # noqa: E402


def T(bpm, key="8B", energy=0.5, valence=0.5, loud=-10.0,
      cid="x", block="A", has_feat=True):
    """造一个优化器认识的曲目 dict。

    has_feat=False 用来模拟"这首歌没抓到音频特征"——此时 cost 函数必须跳过它。
    """
    return {"cid": cid, "block": block, "name": cid,
            "bpm": bpm, "key": key, "energy": energy, "valence": valence, "loud": loud,
            "f": {"tempo": bpm} if has_feat else None}


class TestAdjacencyCostIsolated(unittest.TestCase):
    """每条规则单独触发，断言恰好等于它自己的权重。"""

    def test_clean_pair_costs_nothing(self):
        # 120→125BPM（幅度 4% 但调性不兼容）、能量相同、都不是慢歌
        self.assertEqual(po.adjacency_cost([T(120, "8B"), T(125, "3A")]), 0.0)

    def test_two_slow_only(self):
        # 两首都 <100、同 BPM、调性不兼容 → 只触发"两首慢歌"
        self.assertEqual(po.adjacency_cost([T(95, "8B"), T(95, "3A")]), po.W_TWO_SLOW)

    def test_small_drop_only(self):
        # 100→95 降 5%：起点不算慢歌（100 不小于 100）、调性不兼容 → 只触发"只慢一点"
        self.assertEqual(po.adjacency_cost([T(100, "8B"), T(95, "3A")]), po.W_SMALL_DROP)

    def test_both_similar_only(self):
        # 同 BPM 且 Camelot 兼容 → 只触发"节奏与调性同时相似"
        self.assertEqual(po.adjacency_cost([T(120, "8B"), T(120, "8A")]), po.W_BOTH_SIMILAR)

    def test_big_tempo_jump_only(self):
        # 80→130 是 +62.5%，超过 40% 阈值；80 不算慢歌（130 不 <100）
        self.assertEqual(po.adjacency_cost([T(80, "8B"), T(130, "3A")]), po.W_BIG_TEMPO_JUMP)

    def test_energy_clash_only(self):
        # 能量 0.9→0.3 骤变且调性不兼容 → 突兀
        self.assertEqual(
            po.adjacency_cost([T(120, "8B", energy=0.9), T(120, "3A", energy=0.3)]),
            po.W_ENERGY_CLASH)


class TestAdjacencyCostEdgeCases(unittest.TestCase):
    def test_missing_features_are_skipped(self):
        # 任一首没有特征，整个衔接就不参与惩罚（不能凭空猜）
        self.assertEqual(po.adjacency_cost([T(95, "8B", has_feat=False), T(95, "8B")]), 0.0)
        self.assertEqual(po.adjacency_cost([T(95, "8B"), T(95, "8B", has_feat=False)]), 0.0)

    def test_short_sequences(self):
        self.assertEqual(po.adjacency_cost([]), 0.0)
        self.assertEqual(po.adjacency_cost([T(95, "8B")]), 0.0)

    def test_penalties_accumulate(self):
        """两首歌同时踩多条规则时，惩罚应该相加而不是只算一条。"""
        pair = [T(95, "8B", energy=0.9), T(95, "8A", energy=0.3)]
        # 两首慢歌 + 同 BPM 且调性兼容 → 至少这两项之和
        self.assertGreaterEqual(po.adjacency_cost(pair), po.W_TWO_SLOW + po.W_BOTH_SIMILAR)


class TestArcCost(unittest.TestCase):
    def test_needs_at_least_five_featured_tracks(self):
        self.assertEqual(po.arc_cost([T(120) for _ in range(4)]), 0.0)
        self.assertEqual(po.arc_cost([]), 0.0)

    def test_non_negative(self):
        seq = [T(120, valence=v) for v in (0.1, 0.5, 0.9, 0.4, 0.2)]
        self.assertGreaterEqual(po.arc_cost(seq), 0.0)

    def test_valence_valley_late_beats_valley_centred(self):
        """valence 的目标是"先落再起"（谷底在 60% 处），倒 U 应该明显更贵。"""
        hole = [0.9, 0.4, 0.2, 0.5, 1.0]
        inverted = [0.2, 0.5, 0.9, 0.5, 0.2]
        a = po.arc_cost([T(120, valence=v) for v in hole])
        b = po.arc_cost([T(120, valence=v) for v in inverted])
        self.assertLess(a, b)

    def test_uniform_features_are_tolerated(self):
        """所有歌特征完全相同时，无法构成任何弧线，cost 应为确定值而非崩溃/除零。"""
        seq = [T(120, valence=0.5) for _ in range(6)]
        self.assertIsInstance(po.arc_cost(seq), float)


def _blocks():
    """两个各 8 首的块，特征刻意做得容易被重排。"""
    a = [T(95 + i, key="8B" if i % 2 else "3A", cid=f"A{i}", block="A") for i in range(8)]
    b = [T(120 + i, key="5A" if i % 2 else "9B", cid=f"B{i}", block="B") for i in range(8)]
    return [a, b]


class TestAnneal(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        """固定 seed 必须完全可复现——否则报告里的 cost 数字没有意义。"""
        s1, c1 = po.anneal(_blocks(), iters=3000, seed=42)
        s2, c2 = po.anneal(_blocks(), iters=3000, seed=42)
        self.assertEqual(c1, c2)
        self.assertEqual([t["cid"] for t in s1], [t["cid"] for t in s2])

    def test_block_order_is_preserved(self):
        """硬约束：主题分块顺序不能为了顺耳被打乱，只能组内重排。"""
        seq, _ = po.anneal(_blocks(), iters=3000, seed=7)
        self.assertEqual([t["block"] for t in seq], ["A"] * 8 + ["B"] * 8)
        self.assertEqual({t["cid"] for t in seq if t["block"] == "A"},
                         {f"A{i}" for i in range(8)})
        self.assertEqual({t["cid"] for t in seq if t["block"] == "B"},
                         {f"B{i}" for i in range(8)})

    def test_never_worse_than_input_order(self):
        blocks = _blocks()
        start = po.total_cost([t for b in blocks for t in b])
        _, best = po.anneal(blocks, iters=3000, seed=7)
        self.assertLessEqual(best, start + 1e-9)

    def test_reported_cost_matches_recomputed(self):
        seq, best = po.anneal(_blocks(), iters=500, seed=3)
        self.assertAlmostEqual(po.total_cost(seq), best, places=6)

    def test_all_tracks_survive(self):
        seq, _ = po.anneal(_blocks(), iters=1000, seed=5)
        self.assertEqual(len(seq), 16)
        self.assertEqual(len({t["cid"] for t in seq}), 16)


class TestParseSpec(unittest.TestCase):
    def test_blocks(self):
        spec = po.parse_spec({"blocks": [{"id": "A", "title": "起", "tracks": ["1", "2"]}]})
        self.assertEqual(spec, [{"id": "A", "title": "起", "tracks": ["1", "2"]}])

    def test_flat_is_wrapped_into_one_block(self):
        spec = po.parse_spec({"tracks": ["1", "2"]})
        self.assertEqual(len(spec), 1)
        self.assertEqual(spec[0]["tracks"], ["1", "2"])

    def test_missing_id_is_generated(self):
        self.assertEqual(po.parse_spec({"blocks": [{"tracks": ["1"]}]})[0]["id"], "B1")

    def test_empty_raises_value_error(self):
        for bad in ({}, {"blocks": []}, {"tracks": []}):
            with self.assertRaises(ValueError):
                po.parse_spec(bad)


class TestTotalCost(unittest.TestCase):
    def test_is_sum_of_parts(self):
        seq = [T(95 + i, cid=f"c{i}", valence=(i % 5) / 4) for i in range(10)]
        self.assertAlmostEqual(
            po.total_cost(seq), po.adjacency_cost(seq) + po.arc_cost(seq), places=9)

    def test_weights_are_positive(self):
        for name in ("W_TWO_SLOW", "W_SMALL_DROP", "W_BOTH_SIMILAR",
                     "W_BIG_TEMPO_JUMP", "W_ENERGY_CLASH", "W_ARC"):
            self.assertGreater(getattr(po, name), 0.0, name)


class TestArcCostHonoursTheChosenShape(unittest.TestCase):
    """arc_cost 必须真的朝**选定**的形状排。

    以前它把 man-in-a-hole 硬编码在函数体里（valence 谷底固定在 60%），
    而策划文档把"先选一个形状"列为第一步——那一步当时只有诊断价值，
    工具并没有兑现它自己写的流程。
    """

    @staticmethod
    def _ideal_seq(shape_name):
        """把某个形状的理想曲线直接造成一串曲目（valence/energy/loudness 都跟着它）。"""
        vals = core.shape_target(shape_name, 5)
        return [T(120, key=f"{i + 1}B", energy=v, valence=v,
                  loud=v * 20 - 20, cid=f"c{i}")
                for i, v in enumerate(vals)]

    def test_matching_shape_is_cheaper_than_a_mismatched_one(self):
        seq = self._ideal_seq("cinderella")
        self.assertLess(po.arc_cost(seq, "cinderella"),
                        po.arc_cost(seq, "icarus"))

    def test_every_shape_prefers_its_own_curve(self):
        """每个形状的理想序列，在自己那套目标下都该是最便宜的。

        tempo 那一项与形状无关，所以它在各形状下相同；情绪三项在自己那套目标下
        距离为 0。于是"自己最便宜"是可以严格断言的，不是近似。
        """
        for name in core.SHAPE_ALIASES:
            seq = self._ideal_seq(name)
            own = po.arc_cost(seq, name)
            others = [po.arc_cost(seq, other)
                      for other in core.SHAPE_ALIASES if other != name]
            self.assertLessEqual(own, min(others) + 1e-9,
                                 f"{name} 的理想序列在别的形状下反而更便宜")

    def test_default_shape_is_man_in_a_hole(self):
        seq = self._ideal_seq("man-in-a-hole")
        self.assertAlmostEqual(po.arc_cost(seq),
                               po.arc_cost(seq, core.DEFAULT_SHAPE), places=12)

    def test_default_shape_is_not_all_slow_or_empty(self):
        """默认值不该是个占位符：它必须是六个之一，而且确实是"落-起"。"""
        self.assertIn(core.DEFAULT_SHAPE, core.SHAPE_ALIASES)
        ideal = core.ARCHETYPES[core.resolve_shape(core.DEFAULT_SHAPE)]
        self.assertLess(min(ideal), ideal[0])      # 中间比开头低
        self.assertGreater(ideal[-1], ideal[0])    # 结尾比起步高

    def test_unknown_shape_raises(self):
        with self.assertRaises(ValueError):
            po.arc_cost(self._ideal_seq("icarus"), "not-a-shape")

    def test_total_cost_threads_the_shape_through(self):
        seq = self._ideal_seq("cinderella")
        self.assertAlmostEqual(po.total_cost(seq, "cinderella"),
                               po.adjacency_cost(seq) + po.arc_cost(seq, "cinderella"),
                               places=9)

    def test_anneal_accepts_a_shape(self):
        """退火必须把 shape 一路传下去，否则目标形状在中途被丢掉。"""
        blocks = _blocks()
        s1, c1 = po.anneal(blocks, iters=800, seed=11, shape="cinderella")
        self.assertAlmostEqual(po.total_cost(s1, "cinderella"), c1, places=6)


class TestOptimizerRecordsCoverageReasons(unittest.TestCase):
    """优化器必须记下每首曲子**为什么**没特征，而不是只留一个 None。

    没有这个，"优化后 cost = 1.15"这类数字就没法解释它描述了多少曲目：
    覆盖率 60% 时，四成位置其实没被评估过。
    """

    def test_load_tracks_tags_each_missing_reason(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "feats.json").write_text(_json.dumps({
                "a": {"_cid": "1", "_name": "ok", "tempo": 120, "key": 0, "mode": 1,
                      "energy": 0.5, "valence": 0.5, "loudness": -10},
                "b": {"_cid": "2", "_name": "miss", "_miss": True},
                "c": {"_cid": "3", "_name": "notempo", "energy": 0.5},
            }), encoding="utf-8")
            (td / "spec.json").write_text(
                _json.dumps({"tracks": ["1", "2", "3", "4"]}), encoding="utf-8")

            _, tracks = po.load_tracks(str(td / "spec.json"), str(td / "feats.json"))
            stages = {t["cid"]: t["stage"] for t in tracks}
            self.assertEqual(stages["1"], "ok")
            self.assertEqual(stages["2"], "source-miss")
            self.assertEqual(stages["3"], "no-features")
            self.assertEqual(stages["4"], "not-in-cache")

    def test_coverage_report_counts_match_the_tracks(self):
        counts = Counter(t.get("stage", "ok") for t in [
            {"stage": "ok"}, {"stage": "ok"}, {"stage": "source-miss"}])
        txt = po.coverage_report(counts, 3)
        self.assertIn("2/3", txt)
        self.assertIn("⚠️", txt)          # 67% < 90%


if __name__ == "__main__":
    unittest.main(verbosity=2)

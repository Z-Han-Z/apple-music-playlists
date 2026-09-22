#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`am_lyrics`（LRCLIB 客户端）与它在人声判定里的接入。

**全部离线**：注入假 opener，不出网。真实契约是手动实测过的
（`/api/search` 模糊命中 8/12；`/api/get` 要求 duration 精确，0/8），
这里只锁行为。
"""

import json
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import am_lyrics as ly  # noqa: E402
import playlist_core as core  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Opener:
    """按 URL 片段返回预设载荷，并记录调用过的 URL。"""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def open(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        for frag, payload in self.mapping.items():
            if frag in url:
                if isinstance(payload, Exception):
                    raise payload
                return _Resp(payload)
        raise AssertionError(f"没预设这个 URL: {url}")


def _rec(instrumental=False, plain="", synced="", duration=200):
    return {"instrumental": instrumental, "plainLyrics": plain,
            "syncedLyrics": synced, "duration": duration}


class TestLookup(unittest.TestCase):
    def test_search_hit_returns_signals_but_never_lyrics(self):
        op = _Opener({"/api/search": [_rec(plain="la la", synced="[00:01]la")]})
        r = ly.lookup("T", "A", opener=op, use_cache=False)
        self.assertTrue(r["found"])
        self.assertTrue(r["has_plain"])
        self.assertEqual(r["match"], "search")
        # 正文绝不能混进结构里
        self.assertNotIn("plainLyrics", r)
        self.assertNotIn("syncedLyrics", r)

    def test_instrumental_flag_is_surfaced(self):
        op = _Opener({"/api/search": [_rec(instrumental=True)]})
        r = ly.lookup("T", "A", opener=op, use_cache=False)
        self.assertTrue(r["instrumental"])
        self.assertFalse(r["has_plain"])

    def test_search_miss_without_duration_stops_there(self):
        op = _Opener({"/api/search": []})
        r = ly.lookup("T", "A", opener=op, use_cache=False)
        self.assertFalse(r["found"])
        self.assertEqual(len(op.calls), 1, "没有 duration 就不该再试 /api/get")

    def test_search_miss_with_duration_tries_get(self):
        op = _Opener({"/api/search": [], "/api/get": _rec(plain="x")})
        r = ly.lookup("T", "A", duration_ms=200_000, opener=op, use_cache=False)
        self.assertTrue(r["found"])
        self.assertEqual(r["match"], "get")

    def test_network_failure_degrades_gracefully(self):
        """查不到歌词不该让整个工具崩掉——它只是一条弱证据。"""
        op = _Opener({"/api/search": urllib.error.URLError("down")})
        r = ly.lookup("T", "A", opener=op, use_cache=False)
        self.assertFalse(r["found"])

    def test_picks_the_closest_duration_among_hits(self):
        """同名不同版本很常见，有时间就用它挑最接近的那条。"""
        op = _Opener({"/api/search": [_rec(instrumental=False, plain="a", duration=400),
                                      _rec(instrumental=True, duration=201)]})
        r = ly.lookup("T", "A", duration_ms=200_000, opener=op, use_cache=False)
        self.assertTrue(r["instrumental"], "应挑时长 201 那条")

    def test_signals_helper_never_copies_text(self):
        s = ly.signals({"instrumental": False, "plainLyrics": "secret", "syncedLyrics": "s"})
        self.assertEqual(set(s), {"instrumental", "has_plain", "has_synced"})


class TestClassifyWithLrclib(unittest.TestCase):
    def test_lrclib_flag_is_decisive(self):
        self.assertEqual(core.classify_vocality("Normal", lrclib_instrumental=True),
                         core.INSTRUMENTAL_FLAGGED)

    def test_title_marker_outranks_the_library_flag(self):
        self.assertEqual(
            core.classify_vocality("Song (Instrumental)", lrclib_instrumental=True),
            core.INSTRUMENTAL_MARKED)

    def test_declared_marker_outranks_a_fuzzy_lyrics_hit(self):
        """标记与歌词打架时，站在声明这一边。

        理由不是"标记更准"，而是**LRCLIB 的搜索是模糊的**——一条"命中"可能属于
        另一首同名曲。而标题/乐器标记说的是**这一首**。
        """
        self.assertEqual(
            core.classify_vocality("Normal", lrclib_instrumental=True, lyrics_found=True),
            core.INSTRUMENTAL_FLAGGED)

    def test_flag_false_alone_proves_nothing(self):
        """`instrumental=False` 只说明"不是器乐"，仍需歌词来证明有人声。"""
        self.assertEqual(core.classify_vocality("Normal", lrclib_instrumental=False),
                         core.UNKNOWN)

    def test_new_stage_has_a_label_and_counts_as_excludable(self):
        self.assertIn(core.INSTRUMENTAL_FLAGGED, core.VOCALITY_LABELS)
        txt = core.vocality_report({core.VOCAL: 10, core.INSTRUMENTAL_FLAGGED: 2}, 12)
        self.assertIn("可排除上面 2 首", txt)
        self.assertIn("instrumental", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)

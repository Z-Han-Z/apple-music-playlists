#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构性回归测试。

这里测的不是"某个函数算得对不对"，而是"**某类 bug 有没有被重新引入**"。
每一条都对应一个真实踩过的坑，注释里写了它对应哪一次。

跑：
    python -m unittest discover -s tests -v
"""

import os
import py_compile
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCES = sorted(p for p in ROOT.glob("*.py"))
# make_day_playlist.py 是本地私人脚本（已 gitignore），别人的 clone 里根本没有。
# build_pool.py 曾经也在这里（整段逻辑写在模块顶层，import 就会执行）——
# 改造成正规 CLI 之后它就应该是可 import 的，所以从这个名单里去掉了。
NOT_IMPORTABLE = {"make_day_playlist.py"}


def _code_lines(path: Path):
    """逐行产出 (行号, 内容)，跳过整行注释和文档字符串界定行之外的东西。

    只跳过"以 # 开头"的行——足够挡住注释里提到的历史 bug 示例，
    又不至于把真正的代码漏掉。
    """
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield i, line


class TestNoHardcodedStorefront(unittest.TestCase):
    """地区码被写死过**两次**：playlist_audit 的默认参数、playlist_flow 的内联字符串。

    两次的表现完全一样——非 cn 账号静默拿回空元数据，然后体检降级成
    "只能做基础统计"或"有效曲目太少，无法分析"。这种故障最难查，
    因为它不报错。所以用测试把它挡住。
    """

    def test_no_literal_catalog_region(self):
        bad = []
        for p in SOURCES:
            for i, line in _code_lines(p):
                if re.search(r"catalog/(?:cn|us|jp|gb)\b", line):
                    bad.append(f"{p.name}:{i}: {line.strip()}")
        self.assertEqual(bad, [], "出现写死的 catalog 地区：\n" + "\n".join(bad))

    def test_catalog_meta_has_exactly_one_implementation(self):
        defs = []
        for p in SOURCES:
            for i, line in _code_lines(p):
                if re.match(r"\s*def catalog_meta\b", line):
                    defs.append(f"{p.name}:{i}")
        self.assertEqual(len(defs), 1,
                         f"catalog_meta 只应有一份实现，实际找到 {len(defs)} 份：{defs}")

    def test_every_catalog_meta_call_passes_a_storefront(self):
        """sf 是必填参数，但调用方仍可能传一个字面量。检查参数个数。"""
        for p in SOURCES:
            if p.name == "am_meta.py":
                continue
            for i, line in _code_lines(p):
                m = re.search(r"catalog_meta\(([^)]*)\)", line)
                if m and "def " not in line:
                    args = [a for a in m.group(1).split(",") if a.strip()]
                    self.assertGreaterEqual(
                        len(args), 3, f"{p.name}:{i} 调用 catalog_meta 少了 sf 参数")


class TestNoHardcodedStorefrontDefaults(unittest.TestCase):
    """`--storefront` 的默认值必须是 None。

    曾经 search 子命令写成 default="us"，于是 resolve_storefront() 里
    "显式参数优先"那一支永远先命中，配置里记住的账号地区形同虚设。
    这是"写死地区"的第三种变体——不是路径里写死，而是默认值里写死。
    """

    def test_storefront_cli_arg_defaults_to_none(self):
        src = (ROOT / "am_playlist.py").read_text(encoding="utf-8")
        found = list(re.finditer(
            r'add_argument\(\s*"--storefront"\s*,\s*default=([^,)]+)', src))
        self.assertTrue(found, "没找到 --storefront 的参数定义，测试本身可能失效了")
        for m in found:
            self.assertEqual(m.group(1).strip(), "None",
                             f"--storefront 的默认值不是 None：{m.group(0)}")


def _project_imports(path: Path) -> set[str]:
    """文件里**真正** import 的顶层模块名。

    只解析 import 语句，不做子串搜索——本文件的文档字符串里就写着
    "一个模块如果需要 import am_playlist…"，子串搜索会把这句说明当成真依赖。
    """
    src = path.read_text(encoding="utf-8")
    return {m.group(1).split(".")[0]
            for m in re.finditer(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)}


PROJECT_MODULES = {
    "am_paths", "am_playlist", "am_meta", "playlist_flow", "playlist_optimize",
    "playlist_audit", "playlist_core", "listening_stats", "profile_library",
    "am_mcp_server", "build_pool",
}


class TestPlatformNeutralCore(unittest.TestCase):
    """am_paths 必须保持平台无关——否则纯算法层会间接依赖某个音乐平台的代码。"""

    def test_am_paths_imports_no_project_module(self):
        bad = _project_imports(ROOT / "am_paths.py") & PROJECT_MODULES
        self.assertEqual(bad, set(), f"am_paths 不该 import 项目内模块：{bad}")

    def test_am_paths_imports_only_stdlib(self):
        allowed = {"os", "sys", "pathlib", "typing", "json", "__future__"}
        bad = _project_imports(ROOT / "am_paths.py") - allowed
        self.assertEqual(bad, set(), f"am_paths 引入了非标准库依赖：{bad}")

    def test_optimizer_does_not_import_apple_layer(self):
        """优化器必须是纯算法层。

        既不能直接依赖 Apple 层，也不能**经由** playlist_flow 间接依赖
        （playlist_flow 会 import am_playlist）。以前它正是从 playlist_flow
        取 camelot/fold_tempo/harmonic_ok 的——那等于让算法层认识某个平台。
        """
        imported = _project_imports(ROOT / "playlist_optimize.py")
        for banned in ("am_playlist", "am_meta", "playlist_flow", "playlist_audit"):
            self.assertNotIn(banned, imported, f"优化器不该 import {banned}")
        self.assertIn("playlist_core", imported,
                      "优化器应该只依赖平台无关的 playlist_core")


class TestPaths(unittest.TestCase):
    def test_config_dir_is_stable(self):
        """config.json 里是用户的 token。路径一改，所有人都得重新登录。"""
        import am_paths
        self.assertEqual(am_paths.config_dir().name, "am-playlist")

    def test_cache_dir_is_separate_from_config_dir(self):
        import am_paths
        self.assertNotEqual(am_paths.cache_dir(), am_paths.config_dir(),
                            "缓存目录不该等于配置目录——缓存要能随手删掉")

    def test_cache_dir_is_outside_the_repo(self):
        import am_paths
        repo = Path(am_paths.REPO_DIR).resolve()
        cache = am_paths.cache_dir().resolve()
        self.assertFalse(str(cache).startswith(str(repo)),
                         f"缓存目录 {cache} 落在仓库 {repo} 内")

    def test_read_dirs_put_user_cache_first(self):
        import am_paths
        dirs = am_paths.read_dirs()
        self.assertGreaterEqual(len(dirs), 2)
        self.assertEqual(dirs[0], am_paths.cache_dir(),
                         "用户缓存目录必须是第一优先，旧 refs/ 只作回退")
        self.assertEqual(dirs[-1], am_paths.legacy_cache_dir())


class TestSourcesCompile(unittest.TestCase):
    def test_every_source_compiles(self):
        bad = []
        with tempfile.TemporaryDirectory() as td:
            for p in SOURCES:
                try:
                    py_compile.compile(str(p), doraise=True,
                                       cfile=os.path.join(td, p.stem + ".pyc"))
                except py_compile.PyCompileError as e:
                    bad.append(f"{p.name}: {e}")
        self.assertEqual(bad, [], "有文件编译不过：\n" + "\n".join(bad))

    def test_every_source_imports(self):
        import importlib
        for p in SOURCES:
            if p.name in NOT_IMPORTABLE or p.name.startswith("test_"):
                continue
            try:
                importlib.import_module(p.stem)
            except Exception as e:      # noqa: BLE001
                self.fail(f"{p.name} 无法 import: {type(e).__name__}: {e}")


class TestBuildPoolIsDistributable(unittest.TestCase):
    """build_pool.py 曾经有两个让人根本跑不起来的问题：

      1. 整段逻辑写在模块顶层（没有 main()、没有 __main__ 守卫），import 就执行；
      2. 读 refs/library-songs.json —— 而**仓库里没有任何代码生成过这个文件**，
         它还被 gitignore 了。于是对新克隆的人来说必然 FileNotFoundError。

    现在它必须是：可 import、有 main()、用 argparse、不依赖仓库内 refs/。
    """

    def setUp(self):
        self.src = (ROOT / "build_pool.py").read_text(encoding="utf-8")

    def test_is_a_proper_cli(self):
        self.assertIn("def main(", self.src)
        self.assertIn('if __name__ == "__main__":', self.src)
        self.assertIn("argparse.ArgumentParser", self.src)

    def test_import_is_side_effect_free(self):
        """import 就能跑完整个流程的话，测试和下游模块都别想用这个文件。"""
        import importlib
        importlib.import_module("build_pool")   # 不抛异常即通过

    def test_no_repo_local_refs_path(self):
        for line in self.src.splitlines():
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn('"refs"', line,
                             f"build_pool 不该再用仓库内的 refs/：{line.strip()}")

    def test_uses_the_shared_library_accessor(self):
        """缓存文件名必须由 am_library 决定，不能在这里再拼一次。"""
        self.assertIn("import am_library", self.src)
        for line in self.src.splitlines():
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn("library-songs.json", line,
                             f"缓存文件名不该在 build_pool 里硬编码：{line.strip()}")


class TestCliEntryPoints(unittest.TestCase):
    """每个命令行入口要么用 argparse，要么自己处理 -h/--help。

    以前 `python playlist_audit.py --help` 会把 "--help" 当成歌单名，
    回一句"找不到歌单: --help"——对一个要给别人用的工具来说太糙了。
    另外 `SystemExit(__doc__)` 本身就是错的：传字符串给 SystemExit 会
    退出码 1 并把文档打到 stderr，不是打印用法。
    """

    def test_audit_help_and_usage(self):
        import playlist_audit as pa
        self.assertEqual(pa.main(["--help"]), 0)
        self.assertEqual(pa.main(["-h"]), 0)
        self.assertEqual(pa.main([]), 2)

    def test_optimizer_help_and_usage(self):
        import playlist_optimize as po
        self.assertEqual(po.main([]), 2)
        self.assertEqual(po.main(["--help"]), 0)
        self.assertEqual(po.main(["--list-shapes"]), 0)

    def test_flow_help_and_usage(self):
        import playlist_flow as pf
        self.assertEqual(pf.main([]), 2)
        self.assertEqual(pf.main(["--help"]), 0)
        self.assertEqual(pf.main(["-h"]), 0)

    def test_no_source_raises_systemexit_with_a_string(self):
        """SystemExit(<文档字符串>) 是个容易复发的写法。"""
        for p in SOURCES:
            src = p.read_text(encoding="utf-8")
            self.assertNotIn("SystemExit(__doc__)", src, f"{p.name} 又用了 SystemExit(__doc__)")


class TestUtf8Output(unittest.TestCase):
    """每个命令行入口都必须开 UTF-8 输出。

    实测依据：同一条命令里，调用过它的脚本中文正常，没调用的打印出一串乱码。
    "有的调了、有的没调"本身就是 bug——而在 Windows 上中文乱码会让整个
    报告没法读。
    """

    ENTRY_POINTS = ("am_playlist.py", "playlist_audit.py", "playlist_flow.py",
                    "playlist_optimize.py", "listening_stats.py",
                    "profile_library.py", "build_pool.py")

    def test_every_entry_point_enables_utf8(self):
        for name in self.ENTRY_POINTS:
            src = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("enable_utf8_stdout", src,
                          f"{name} 没有开 UTF-8 输出（Windows 上中文会乱码）")

    def test_reconfigure_logic_lives_in_one_place(self):
        """reconfigure 只该在 am_paths 里出现一次，别的文件只调用它。"""
        hits = [p.name for p in SOURCES
                if "reconfigure(encoding" in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, ["am_paths.py"],
                         f"reconfigure 的实现在别的文件里也出现了：{hits}")


class TestDocsDoNotLie(unittest.TestCase):
    """文档里的数字会腐烂。能守住的就守，不值得守的干脆别写。

    这一轮实测抓到两处，都不是假想问题：

      · README 和 SKILL 写着"104 项测试"，实际早已是 139——因为我在**同一个
        session 里加了三次测试，三次都没回头改文档**。
      · 更糟的一处：docs/platform-adapters.md 先写"这 12% 现在是被静默丢掉的"，
        十行之后又写"这一条已经落地了"——自相矛盾。原因是我在同一次编辑里补了
        修复，却没有回头调和上面那段。

    第一版的修法是"把数字改对，并加一条断言钉住它"。断言立刻失败了——
    因为它自己也是三个测试，实际数量又变了。这恰好说明：**写进文档的测试数量
    本身就是个负资产**，它一变就要改两处，而它对读者几乎没有价值。
    所以现在的处理是：测试数量从文档里删掉，工具数量保留并用断言守住
    （它很少变，而且确实告诉读者该期待什么）。
    """

    # 这些不是仓库文件，而是使用者侧的产物或示例输入名
    EXTERNAL = {"config.json", "tracks.json", "stack.json", "blocks.json",
                "features.json", "pool.json", "order.json"}

    def _claim(self, rel: str, pattern: str) -> int:
        src = (ROOT / rel).read_text(encoding="utf-8")
        m = re.search(pattern, src)
        self.assertIsNotNone(m, f"{rel} 里找不到该声明（pattern={pattern}）")
        return int(m.group(1))

    def test_documented_tool_counts_match_reality(self):
        import am_mcp_server as srv
        actual = len(srv.TOOLS)
        claims = [("README.md", r"\*\*(\d+) tools\*\*"),
                  ("skill/SKILL.md", r"MCP 工具（(\d+) 个）")]
        for rel, pat in claims:
            self.assertEqual(self._claim(rel, pat), actual,
                             f"{rel} 写的 MCP 工具数与实际（{actual}）不符")

    def test_docs_do_not_hardcode_a_test_count(self):
        """测试数量不该出现在文档里——它会腐烂，而且没人靠它做决定。"""
        for rel in ("README.md", "skill/SKILL.md"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\d+\s*(?:tests\b|项测试)", src),
                f"{rel} 又把测试数量写进去了；它一定会过期")

    def test_claimed_paths_exist(self):
        """文档里用反引号括起来的仓库内路径必须真的存在。

        解析顺序：**先按该文件所在目录**，再按仓库根目录。
        `skill/SKILL.md` 里写 `reference.md` 指的是同目录的兄弟文件
        （skill 部署出去时这两个文件是平铺在一起的），
        但 skill 正文里也会引用仓库根部的 `docs/...`、`SETUP.md`。
        两种都要能解析。
        """
        for rel in ("README.md", "skill/SKILL.md", "docs/platform-adapters.md"):
            here = (ROOT / rel).parent
            src = (ROOT / rel).read_text(encoding="utf-8")
            for m in re.finditer(r"`([A-Za-z0-9_./-]+\.(?:py|md|json|yml))`", src):
                ref = m.group(1)
                if ref.startswith(("http", "/abs")) or Path(ref).name in self.EXTERNAL:
                    continue
                self.assertTrue((here / ref).exists() or (ROOT / ref).exists(),
                                f"{rel} 提到了不存在的文件：{ref}")


class TestMcpServerConsistency(unittest.TestCase):
    """声明了工具却没接上 handler（或反过来）是这类服务器的经典 bug。"""

    def setUp(self):
        import am_mcp_server as srv
        self.srv = srv

    def test_tool_names_are_unique(self):
        names = [t["name"] for t in self.srv.TOOLS]
        self.assertEqual(len(names), len(set(names)), f"工具有重名：{names}")

    def test_every_tool_has_a_handler(self):
        missing = [t["name"] for t in self.srv.TOOLS if t["name"] not in self.srv.HANDLERS]
        self.assertEqual(missing, [], f"这些工具没接 handler：{missing}")

    def test_every_handler_is_a_declared_tool(self):
        declared = {t["name"] for t in self.srv.TOOLS}
        extra = [k for k in self.srv.HANDLERS if k not in declared]
        self.assertEqual(extra, [], f"这些 handler 没有对应的工具声明：{extra}")

    def test_tool_schemas_are_wellformed(self):
        for t in self.srv.TOOLS:
            self.assertIn("description", t, t["name"])
            self.assertTrue(t["description"].strip(), t["name"])
            schema = t["inputSchema"]
            self.assertEqual(schema["type"], "object", t["name"])
            self.assertIn("properties", schema, t["name"])

    def test_server_version_matches_package_version(self):
        import am_paths
        self.assertEqual(self.srv.SERVER_INFO["version"], am_paths.VERSION)


class TestCleanUserToken(unittest.TestCase):
    """用户会粘贴整行 cookie、带引号、带前缀——都得能容错。"""

    def setUp(self):
        import am_playlist as am
        self.am = am

    def test_plain(self):
        self.assertEqual(self.am.clean_user_token("ABC123"), "ABC123")

    def test_cookie_line(self):
        self.assertEqual(
            self.am.clean_user_token("media-user-token=ABC123; path=/; HttpOnly"),
            "ABC123")

    def test_quotes_and_whitespace(self):
        self.assertEqual(self.am.clean_user_token('  "ABC123"  '), "ABC123")
        self.assertEqual(self.am.clean_user_token("'ABC123'"), "ABC123")

    def test_empty(self):
        self.assertEqual(self.am.clean_user_token(""), "")
        self.assertEqual(self.am.clean_user_token(None), "")


class TestVersionNoiseMatching(unittest.TestCase):
    """版本后缀扣分：拉丁词必须**整词**匹配，CJK 只能子串匹配。"""

    def setUp(self):
        import am_playlist as am
        self.am = am

    def test_live_is_detected(self):
        self.assertIn("live", self.am.version_noise_hits("Song (Live)"))
        self.assertIn("live", self.am.version_noise_hits("Song - Live Version"))

    def test_alive_is_not_live(self):
        """真实误伤：子串匹配会把 "Alive"/"Olive"/"Deliver" 当成现场版扣分。"""
        self.assertEqual(self.am.version_noise_hits("Alive"), [])
        self.assertEqual(self.am.version_noise_hits("Olive Tree"), [])
        self.assertEqual(self.am.version_noise_hits("Deliver Me"), [])

    def test_remix_is_still_detected(self):
        """"mix" 单独按整词列会漏掉 "Remix"，所以合成词要显式进表。"""
        self.assertIn("remix", self.am.version_noise_hits("Song (Remix)"))

    def test_cjk_uses_substring(self):
        self.assertIn("现场", self.am.version_noise_hits("某曲 现场版"))
        self.assertIn("伴奏", self.am.version_noise_hits("某曲（伴奏）"))

    def test_clean_title_has_no_hits(self):
        self.assertEqual(self.am.version_noise_hits("普通の曲名"), [])
        self.assertEqual(self.am.version_noise_hits("Plain Song Title"), [])
        self.assertEqual(self.am.version_noise_hits(""), [])


class TestBestSongMatch(unittest.TestCase):
    def setUp(self):
        import am_playlist as am
        self.am = am

    @staticmethod
    def _song(name, artist):
        return {"id": name, "attributes": {"name": name, "artistName": artist}}

    def test_prefers_the_studio_version(self):
        songs = [self._song("Alive (Live)", "X"), self._song("Alive", "X")]
        got = self.am.best_song_match("Alive - X", songs)
        self.assertEqual(got["attributes"]["name"], "Alive")

    def test_penalizes_unrequested_live(self):
        songs = [self._song("Song (Live)", "X"), self._song("Song", "X")]
        got = self.am.best_song_match("Song - X", songs)
        self.assertEqual(got["attributes"]["name"], "Song")

    def test_requested_live_is_not_penalized(self):
        songs = [self._song("Song (Live)", "X"), self._song("Song", "X")]
        got = self.am.best_song_match("Song Live - X", songs)
        self.assertEqual(got["attributes"]["name"], "Song (Live)")

    def test_empty_returns_none(self):
        self.assertIsNone(self.am.best_song_match("anything", []))

    def test_falls_back_to_first_result(self):
        songs = [self._song("完全无关", "Y"), self._song("也无关", "Z")]
        self.assertIs(self.am.best_song_match("Something - Someone", songs), songs[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

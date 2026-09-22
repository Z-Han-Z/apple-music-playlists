#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_paths.py — 与音乐平台无关的路径与版本常量。

刻意**不** import 任何项目内其他模块。这条约束有两个具体用处：

  · am_playlist.py 在 import 期就要算 CONFIG_PATH，所以这里不能反过来依赖它；
  · playlist_optimize.py 这类纯算法模块可以保持完全离线、零平台依赖——
    将来接第二个音乐平台时，算法层不需要认识任何一个平台的代码。

判断标准很简单：**一个模块如果需要 import am_playlist，它就不是"平台无关"的。**
"""

from __future__ import annotations

import os
from pathlib import Path

APP = "am-playlist"
VERSION = "1.1.0"

# 仓库根目录（= 本文件所在目录）。只作为**读**回退，绝不往这里写新文件。
REPO_DIR = Path(__file__).resolve().parent


def _env_path(var: str, fallback: Path) -> Path:
    v = os.environ.get(var)
    return Path(v) if v else fallback


def config_dir() -> Path:
    """配置目录。Windows 用 APPDATA(Roaming)，POSIX 用 XDG_CONFIG_HOME。

    ⚠️ **这个路径不能改。** 用户的 developer token 与 music-user-token
    就存在这里的 config.json；改掉等于让所有已登录的人重来一遍。
    """
    if os.name == "nt":
        base = _env_path("APPDATA", Path.home() / "AppData" / "Roaming")
    else:
        base = _env_path("XDG_CONFIG_HOME", Path.home() / ".config")
    return base / APP


def cache_dir() -> Path:
    """缓存 / 导出 / 中间产物目录（每用户一份，不污染仓库）。

    与 config_dir 分开是有意的：**缓存可以随手删，配置不能。**
    Windows 用 LOCALAPPDATA，POSIX 用 XDG_CACHE_HOME。
    """
    if os.name == "nt":
        base = _env_path("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    else:
        base = _env_path("XDG_CACHE_HOME", Path.home() / ".cache")
    return base / APP


def legacy_cache_dir() -> Path:
    """旧版把缓存写在仓库内的 refs/。保留为**只读**回退，别再往这里写。"""
    return REPO_DIR / "refs"


def read_dirs() -> list[Path]:
    """按优先级列出"去哪里找已有缓存"：先用户目录，再旧的仓库内 refs/。

    这样旧缓存仍然可用（不必重抓特征），但新缓存一律写到用户目录。
    """
    return [cache_dir(), legacy_cache_dir()]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_meta.py — Apple catalog 元数据的**唯一**获取实现。

为什么单独拆一个模块：这段循环曾经在 playlist_audit.py / profile_library.py /
build_pool.py 里各写了一遍，然后在 playlist_flow.py 里又内联了一遍。其中两份把
地区码写死成 "cn" —— 于是同一个 bug 被复制了两次。**重复实现就是 bug 的复制器。**

现在全项目只有这一份，并且 `sf` 是**必填**位置参数。这不是形式主义：
Apple 对错误地区**不报错**，只会返回空的 `data`，调用方于是静默降级。
把 sf 变成必填，是为了让"忘记解析地区"在调用处就暴露成 TypeError。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402

# Apple 的 ids 查询每批上限（实测 100 安全）
BATCH = 100


def catalog_meta(ids: list[str], dev: str, sf: str) -> dict:
    """批量取 catalog 元数据 → {catalog_id: attributes}。

    sf: 地区码，**必填**。请用 am.resolve_storefront() 解析后传入，
        不要传字面量。传错地区不会抛异常，只会静默返回 {}。
    """
    out: dict[str, dict] = {}
    clean = [str(i) for i in ids if i]
    for i in range(0, len(clean), BATCH):
        chunk = clean[i:i + BATCH]
        try:
            _, body = am.api("GET", f"/catalog/{sf}/songs", dev=dev,
                             query={"ids": ",".join(chunk)})
            for s in json.loads(body).get("data", []):
                out[s["id"]] = s.get("attributes", {})
        except am.ApiError as e:
            # 单批失败不该让整个体检崩掉；其余批次继续。
            print(f"  ! 元数据批次失败 HTTP {e.status}", file=sys.stderr)
    return out

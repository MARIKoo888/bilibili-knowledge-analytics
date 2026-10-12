#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""==========================================================================
参考实现：B站 wbi 签名（**卡住超过 90 分钟再看这个**）

先说规矩（这是给你自己的规矩，不是给我的）：
  1. 第6周周三先自己写。自己写不出来才看这里 —— 目标是"能调试"，不是"能抄"。
  2. 只抄签名部分（下面 3 个纯函数），采集逻辑（翻页/断点/入库）自己写。
  3. 抄完必须能回答：为什么第二页才开始报 403？参数为什么要按字典序排？

签名三步（缺一不可）：
  ① GET https://api.bilibili.com/x/web-interface/nav  → data.wbi_img.img_url / sub_url
     从两个 URL 的文件名（去掉 .png）取出 img_key、sub_key
  ② mixin_key = 把 img_key + sub_key 拼成 64 字符串，按混排表取 32 位
  ③ 把请求参数（不含 w_rid）按 key 字典序拼成 k=v&k=v，末尾追加 mixin_key，整体取 MD5 → w_rid
     同时带上 wts = 当前 unix 时间戳

常见错误码：-352 频率过高/key过期；-403 签名错或 IP 风控；-101 缺 Cookie
key 有效期约 24 小时，**不能硬编码**，每次任务启动重新拉。
==========================================================================
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from typing import Any

# Windows 控制台默认 GBK，中文会乱码 —— 强制 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com",
}


# ---------------------------------------------------------------- ③ 签名
def get_mixin_key(img_key: str, sub_key: str) -> str:
    """② 混排得到 32 位 mixin_key。

    注意：混排表有 64 项，但只取结果的**前 32 位**（这一点最容易写错，
    写成 64 位后签名永远算不对，接口只会回 -403，很难看出原因）。
    """
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB if i < len(raw))[:32]


def sign_params(params: dict[str, Any], mixin_key: str, wts: int | None = None) -> dict[str, Any]:
    """③ 给参数加签名，返回含 w_rid / wts 的新 dict（不改原参数）。"""
    signed = dict(params)
    signed["wts"] = int(time.time()) if wts is None else wts
    raw = "&".join(f"{k}={signed[k]}" for k in sorted(signed))     # 必须字典序
    signed["w_rid"] = hashlib.md5((raw + mixin_key).encode()).hexdigest()
    return signed


def key_from_url(url: str) -> str:
    """从 wbi 图片 URL 提取 key（文件名去扩展名）。"""
    return url.rsplit("/", 1)[-1].split(".")[0]


def fetch_wbi_keys(session) -> tuple[str, str]:
    """① 拉取当前有效的 img_key / sub_key（有效期约 24h，每次任务启动重新调）。"""
    r = session.get("https://api.bilibili.com/x/web-interface/nav",
                    headers=HEADERS, timeout=20)
    data = r.json()["data"]["wbi_img"]
    return key_from_url(data["img_url"]), key_from_url(data["sub_url"])


# ---------------------------------------------------------------- 自检
def _self_test() -> None:
    """黄金值自检：不联网。

    用公开文档里的示例 key 对做断言 —— **你自己的实现如果算不出下面这两个值，
    就是错的，别急着发请求**（接口只会给你 -403，看不出原因）。
    """
    img_key, sub_key = "7cd084941338484aae1ad9425b84077b", "4932caff0ff746eab6f01bf08b70ac45"
    mk = get_mixin_key(img_key, sub_key)
    GOLDEN_MIXIN = "ea1db124af3b7062474693fa704f4ff8"
    assert mk == GOLDEN_MIXIN, f"mixin_key 应为 {GOLDEN_MIXIN}，实际 {mk}（检查：是否漏了 [:32]）"

    params = {"host_mid": 123456, "offset": "", "timezone_offset": -480}
    a = sign_params(params, mk, wts=1723000000)
    GOLDEN_WRID = "39d7b96663207857ab3ed02dba92782d"
    assert a["w_rid"] == GOLDEN_WRID, f"w_rid 应为 {GOLDEN_WRID}，实际 {a['w_rid']}"
    assert a["wts"] == 1723000000

    b = sign_params({**params, "offset": "1_2"}, mk, wts=1723000000)
    assert b["w_rid"] != a["w_rid"], "参数变了签名必须变（这就是第二页要重新签名的原因）"
    assert sign_params(params, mk, wts=1723000000) == a, "同参数同签名"

    print("[PASS] mixin_key 黄金值一致 =", mk)
    print("[PASS] w_rid 黄金值一致 =", GOLDEN_WRID)
    print("[PASS] 同参数同签名、改参数必换签名（翻页必须重新签名的原理）")
    print("\n下一步自己写：fetch 搜索结果 → 翻页 → 落盘 data/raw/sample.json")


def _live_test() -> None:
    """真实请求一次（会联网，注意频率）。"""
    import requests
    s = requests.Session()
    s.get("https://www.bilibili.com", headers=HEADERS, timeout=20)   # 拿基础 Cookie，避免 -101
    img_key, sub_key = fetch_wbi_keys(s)
    mk = get_mixin_key(img_key, sub_key)
    params = {"search_type": "video", "keyword": "数据分析", "page": 1, "page_size": 20}
    r = s.get("https://api.bilibili.com/x/web-interface/wbi/search/type",
              headers=HEADERS, params=sign_params(params, mk), timeout=20)
    j = r.json()
    print("code =", j.get("code"), "message =", j.get("message"))
    if j.get("code") == 0:
        results = j["data"].get("result") or []
        print("拿到", len(results), "条；示例标题：",
              (results[0].get("title") if results else "—"))
        out = json.loads(json.dumps(j, ensure_ascii=False))
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "data" / "raw" / "sample.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已落盘", p)
    else:
        print("失败排查：-352 → 降频/刷新 key；-403 → 检查字典序；-101 → 先访问首页拿 Cookie")


if __name__ == "__main__":
    import sys
    _self_test()
    if "--live" in sys.argv:
        _live_test()
    else:
        print("\n（加 --live 可发一次真实请求：python reference/wbi_sign_reference.py --live）")

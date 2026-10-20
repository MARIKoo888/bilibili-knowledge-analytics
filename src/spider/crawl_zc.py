"""S3：为「职场」垂类取数 —— newlist 取种子 + related 滚雪球

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.spider.crawl_zc

为什么是这个结构（面试可讲）：
  - 原计划用 space/wbi/arc/search 拉 UP 主投稿扩量，实测返回 -352 风控校验失败；
    search/type 也返回只有 v_voucher 的空数据。
  - 实测 archive/related 从「职业职场」种子出发，40 条相关推荐里有 31 条仍是职业职场
    （命中率 77%），且都是真实播放量的存量视频，适合做分析。
  - 所以改成 BFS 滚雪球：种子 -> 相关推荐 -> 筛出同细分 -> 入队继续扩 -> 去重。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reference"))
sys.path.insert(0, str(ROOT))

from wbi_sign_reference import (  # noqa: E402
    HEADERS,
    fetch_wbi_keys,
    get_mixin_key,
    sign_params,
)
from src.spider.search import flatten  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

OUT = ROOT / "data" / "raw" / "videos_zc.json"
ZC = "职业职场"
TARGET = 100        # 目标条数
MAX_REQ = 40        # 最多请求多少次（防跑飞、防风控）
SLEEP = 2.0         # 每次请求间隔秒数

NEWLIST = "https://api.bilibili.com/x/web-interface/newlist"
RELATED = "https://api.bilibili.com/x/web-interface/archive/related"


def get_json(session: requests.Session, url: str, params: dict, tries: int = 3) -> dict:
    """带重试的 GET -> JSON。"""
    last: Exception | None = None
    for i in range(1, tries + 1):
        try:
            return session.get(url, params=params, timeout=20).json()
        except Exception as e:
            last = e
            if i < tries:
                print(f"[retry {i}/{tries}] {type(e).__name__}: {str(e)[:60]}")
                time.sleep(2 * i)
    raise RuntimeError(f"请求失败（已重试 {tries} 次）: {type(last).__name__}: {last}") from last


def row_of(v: dict, src: str) -> dict:
    """复用 search.py 的 flatten，只改来源标记。"""
    r = flatten(v)
    r["source_keyword"] = src
    return r


def main() -> int:
    s = requests.Session()
    s.headers.update(HEADERS)

    s.get("https://www.bilibili.com", timeout=20)          # 拿 Cookie
    img_key, sub_key = fetch_wbi_keys(s)                   # wbi key 有效期约 24h
    mk = get_mixin_key(img_key, sub_key)
    print("[wbi] key 已获取")
    time.sleep(1.5)

    # ---------- 1) 种子：newlist 里筛出「职业职场」 ----------
    j = get_json(s, NEWLIST, sign_params({"rid": 36, "pn": 1, "ps": 50}, mk))
    arcs = (j.get("data") or {}).get("archives") or []
    print(f"[seed] newlist 拿到 {len(arcs)} 条")

    seeds = []
    # TODO 1：只保留 tname == ZC 的，append 进 seeds
    for a in arcs:
        if a.get("tname") == ZC:
            seeds.append(a)

    print(f"[seed] 其中 {ZC} = {len(seeds)} 条")

    # ---------- 2) 滚雪球 ----------
    rows: dict[str, dict] = {}
    for a in seeds:
        rows[a["bvid"]] = row_of(a, "newlist_36")

    queue = [a["bvid"] for a in seeds]
    req = 0

    # TODO 2：BFS 主循环（把下面每一行的 "    # " 删掉，注意缩进）
    #   while queue and len(rows) < TARGET and req < MAX_REQ:
    #       bvid = queue.pop(0)
    #       j2 = get_json(s, RELATED, {"bvid": bvid})
    #       rel = j2.get("data") or []
    #       req += 1
    #       new = 0
    #       for v in rel:
    #           if v.get("tname") != ZC:
    #               continue
    #           if v.get("bvid") in rows:
    #               continue
    #           rows[v["bvid"]] = row_of(v, f"related:{bvid}")
    #           queue.append(v["bvid"])
    #           new += 1
    #       print(f"[{req:02d}] {bvid} -> 相关 {len(rel)} 条，新增 {ZC} {new} 条，累计 {len(rows)}")
    #       time.sleep(SLEEP)

    while queue and len(rows) <TARGET and req<MAX_REQ:
        bvid=queue.pop(0)
        j2 = get_json(s, RELATED, {"bvid": bvid})
        rel = j2.get("data") or []
        req += 1
        new=0
        for v in rel:
            if v.get("tname")!= ZC:
                continue
            if v.get("bvid") in rows:
                continue
            rows[v["bvid"]] = row_of(v,f"related:{bvid}")
            queue.append(v["bvid"])
            new += 1
        print(f"[{req:02d}] {bvid} -> 相关 {len(rel)} 条，新增 {ZC} {new} 条，累计 {len(rows)}")
        time.sleep(SLEEP)



    # ---------- 3) 落盘 ----------
    out = list(rows.values())
    import json as _json
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[done] 写入 {OUT}")
    print(f"[done] 条数 = {len(out)}（目标 {TARGET}）")
    print(f"[done] 请求次数 = {req}")
    if out:
        plays = sorted((r.get("view_cnt") or 0) for r in out)
        mid = plays[len(plays) // 2]
        print(f"[done] 播放中位数 = {mid}")
    else:
        print("[warn] 0 条 —— TODO 还没填吧？")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

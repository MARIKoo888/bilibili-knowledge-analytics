#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""==========================================================================
接口可行性探测（诊断工具，**不是**你的采集代码）

用法：
    python reference/probe_endpoints.py

它回答一个问题：**在不需要登录的前提下，哪些接口现在能真正拿到数据？**
依次尝试：设备指纹 → 分区排行 → 综合热门 → 分区最新 → 关键词搜索 → 视频详情
每个接口输出：code / message / 拿到几条 / 样本标题 / 是否被风控（v_voucher）

为什么需要它：B站搜索接口在"无设备 Cookie"时不会报错，而是**返回 code=0 但
data 里只有一个 v_voucher（风控凭证）**——看起来成功、实际 0 条数据。这是最容易
让人误判"爬虫写好了"的坑。跑完这个脚本，第6周周三就不用再摸索一遍。

注意：只读公开接口、限速 1.5s、单个关键词。诊断用，别拿它当采集器。
==========================================================================
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

ROOT = Path(__file__).resolve().parents[1]
INTERVAL = 1.5

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
]

results: list[tuple[str, str, str]] = []


# ------------------------------------------------------------------ 签名
def mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB if i < len(raw))[:32]


def sign(params: dict[str, Any], mk: str) -> dict[str, Any]:
    p = dict(params)
    p["wts"] = int(time.time())
    raw = "&".join(f"{k}={p[k]}" for k in sorted(p))
    p["w_rid"] = hashlib.md5((raw + mk).encode()).hexdigest()
    return p


# ------------------------------------------------------------------ 工具
def first_list(data: Any) -> list:
    """在 data 里找第一个"由 dict 组成的列表"（不同接口字段名不一样）。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        for v in data.values():                      # 再深一层
            if isinstance(v, dict):
                got = first_list(v)
                if got:
                    return got
    return []


def title_of(item: dict) -> str:
    for k in ("title", "name", "bvid"):
        v = item.get(k)
        if isinstance(v, str) and v:
            return v.replace("<em class=\"keyword\">", "").replace("</em>", "")[:40]
    return "—"


def probe(name: str, url: str, params: dict, mk: str | None, signed: bool) -> dict | None:
    q = sign(params, mk) if (signed and mk) else params
    try:
        r = requests.get(url, headers=HEADERS, params=q, timeout=20)
        j = r.json()
    except Exception as e:                                      # noqa: BLE001
        results.append(("FAIL", name, f"{type(e).__name__}: {e}"))
        return None
    code = j.get("code")
    msg = j.get("message")
    data = j.get("data")
    if isinstance(data, dict) and "v_voucher" in data:
        results.append(("RISK", name, f"code={code} 只返回 v_voucher（风控拦截，需设备 Cookie）"))
        return j
    items = first_list(data)
    if code == 0 and items:
        results.append(("OK", name, f"code=0 拿到 {len(items)} 条 | 样本：{title_of(items[0])}"))
    elif code == 0:
        keys = list(data.keys())[:6] if isinstance(data, dict) else type(data).__name__
        results.append(("EMPTY", name, f"code=0 但无列表数据，data keys={keys}"))
    else:
        results.append(("FAIL", name, f"code={code} message={msg}"))
    return j


def prepare_session() -> tuple[requests.Session, str | None]:
    """建会话：访问首页 → 取 buvid3 设备指纹 → 取 wbi key。**顺序不能换。**"""
    s = requests.Session()
    try:
        s.get("https://www.bilibili.com", headers=HEADERS, timeout=20)
        time.sleep(INTERVAL)
        r = s.get("https://api.bilibili.com/x/frontend/finger/spi", headers=HEADERS, timeout=20)
        j = r.json()
        b3, b4 = j.get("data", {}).get("b_3"), j.get("data", {}).get("b_4")
        if b3:
            s.cookies.set("buvid3", b3, domain=".bilibili.com")
            s.cookies.set("buvid4", b4 or "", domain=".bilibili.com")
            results.append(("OK", "设备指纹 buvid3", f"spi 接口拿到 buvid3={b3[:12]}…"))
        else:
            results.append(("FAIL", "设备指纹 buvid3", f"spi 未返回 b_3: {j}"))
    except Exception as e:                                      # noqa: BLE001
        results.append(("FAIL", "设备指纹 buvid3", f"{type(e).__name__}: {e}"))
    time.sleep(INTERVAL)

    mk = None
    try:
        r = s.get("https://api.bilibili.com/x/web-interface/nav", headers=HEADERS, timeout=20)
        wbi = r.json()["data"]["wbi_img"]
        ik = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sk = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        mk = mixin_key(ik, sk)
        results.append(("OK", "wbi key", f"img_key={ik[:10]}… mixin_key={mk[:10]}…"))
    except Exception as e:                                      # noqa: BLE001
        results.append(("FAIL", "wbi key", f"{type(e).__name__}: {e}"))
    time.sleep(INTERVAL)
    return s, mk


def map_zone_tids(rid: int = 36) -> int:
    """聚合 tid → 二级分区名 映射。

    踩过的坑：**不能拿二级分区 id 去当 `newlist` 的 rid 参数**（只接受一级分区，
    传二级会返回 code=0 但列表为空，看起来像"这个分区没内容"）。
    正确做法：用一级分区（知识区 rid=36）拉一批内容，再读每条视频自带的 `tid`/`tname`。
    """
    s, mk = prepare_session()
    pairs: dict[int, dict] = {}
    sources = [
        ("ranking/v2", "https://api.bilibili.com/x/web-interface/ranking/v2", {"rid": rid, "type": "all"}),
        ("newlist", "https://api.bilibili.com/x/web-interface/newlist", {"rid": rid, "ps": 50, "pn": 1}),
    ]
    for label, url, params in sources:
        try:
            r = s.get(url, headers=HEADERS, params=sign(params, mk), timeout=20)
            items = first_list(r.json().get("data"))
            for it in items:
                tid, tname = it.get("tid"), it.get("tname")
                if tid:
                    e = pairs.setdefault(int(tid), {"tname": tname or "?", "count": 0,
                                                     "sample": title_of(it)})
                    e["count"] += 1
            print(f"  {label:<12} 取得 {len(items)} 条")
        except Exception as e:                                  # noqa: BLE001
            print(f"  {label:<12} 错误 {type(e).__name__}: {e}")
        time.sleep(INTERVAL)

    print(f"\n{'tid':>7}  {'二级分区':<18} {'样本数':>5}  样本标题")
    print("-" * 78)
    for tid, e in sorted(pairs.items(), key=lambda kv: -kv[1]["count"]):
        print(f"{tid:>7}  {e['tname']:<18} {e['count']:>5}  {e['sample']}")

    out = ROOT / "data" / "raw" / "tid_map.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([{"tid": k, **v} for k, v in sorted(pairs.items())],
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共 {len(pairs)} 个二级分区，已落盘 {out.relative_to(ROOT)}")
    print("→ 把样本数靠前的几个 tid 填进 config.yaml，按细分分区取数（回答 Q1 供需）。")
    return 0


def probe_comments(ps: int = 20) -> int:
    """评论接口可行性：不登录能翻几页、每页几条、总量多少。

    为什么单独探测：评论是第10周情感分析的地基（计划要 2 万条），
    而评论接口的翻页游标与风控比视频接口严格得多。**先知道上限，再定分析范围**，
    否则第10周才发现"只能拿 20 条/视频"，计划就得返工。
    """
    s, mk = prepare_session()

    # ① 先拿一个高播放视频的 aid
    r = s.get("https://api.bilibili.com/x/web-interface/ranking/v2",
              headers=HEADERS, params=sign({"rid": 36, "type": "all"}, mk), timeout=20)
    items = first_list(r.json().get("data"))
    if not items:
        print("[FAIL] 拿不到视频列表，无法探测评论")
        return 1
    it = items[0]
    aid, bvid, title = it.get("aid"), it.get("bvid"), title_of(it)
    stat = it.get("stat") or {}
    print(f"目标视频：{title}\n  aid={aid} bvid={bvid} 播放={stat.get('view')} 评论数={stat.get('reply')}")
    time.sleep(INTERVAL)

    # 评论获取方式矩阵：一次跑清楚"哪种方式能拿到多少条"
    WBI = "https://api.bilibili.com/x/v2/reply/wbi/main"
    OLD = "https://api.bilibili.com/x/v2/reply"
    WL = "1315875"
    cur_json = json.dumps({"offset": ""}, ensure_ascii=False)
    variants = [
        ("wbi/main mode3 + pn=1（无游标）", WBI,
         {"oid": aid, "type": 1, "mode": 3, "ps": ps, "pn": 1, "web_location": WL}),
        ("wbi/main mode3 + pn=2（无游标）", WBI,
         {"oid": aid, "type": 1, "mode": 3, "ps": ps, "pn": 2, "web_location": WL}),
        ("wbi/main mode2 + 游标 offset=''", WBI,
         {"oid": aid, "type": 1, "mode": 2, "ps": ps, "pagination_str": cur_json, "web_location": WL}),
        ("wbi/main mode3 + 游标 offset=''", WBI,
         {"oid": aid, "type": 1, "mode": 3, "ps": ps, "pagination_str": cur_json, "web_location": WL}),
        ("旧接口 sort=0 pn=1", OLD, {"oid": aid, "type": 1, "pn": 1, "ps": ps, "sort": 0}),
        ("旧接口 sort=0 pn=2", OLD, {"oid": aid, "type": 1, "pn": 2, "ps": ps, "sort": 0}),
        ("旧接口 sort=2 pn=1", OLD, {"oid": aid, "type": 1, "pn": 1, "ps": ps, "sort": 2}),
    ]
    print(f"\n{'获取方式':<34}{'code':>6}{'一级评论':>9}{'all_count':>11}{'is_end':>8}  说明")
    print("-" * 100)
    best, preview_only = 0, False
    for label, u, p in variants:
        try:
            rr = s.get(u, headers=HEADERS, params=sign(p, mk), timeout=20)
            jj = rr.json()
        except Exception as e:                                    # noqa: BLE001
            print(f"{label:<34}{'ERR':>6}{'-':>9}{'-':>11}{'-':>8}  {type(e).__name__}: {e}")
            continue
        dd = jj.get("data") or {}
        reps = dd.get("replies") or []
        cur = dd.get("cursor") or {}
        note = ""
        if jj.get("code") != 0:
            note = str(jj.get("message"))
            if jj.get("code") == -403:
                note = "-403 权限/风控：匿名翻页被拒"
                preview_only = True
        elif "v_voucher" in dd:
            note = "风控凭证（缺 buvid3）"
        elif len(reps) <= ps and cur.get("is_end") and (cur.get("all_count") or 0) > len(reps):
            note = "只给预览，is_end 却是 True"
        best = max(best, len(reps))
        print(f"{label:<34}{jj.get('code'):>6}{len(reps):>9}"
              f"{str(cur.get('all_count')):>11}{str(cur.get('is_end')):>8}  {note}")
        time.sleep(INTERVAL)

    # 弹幕作为备选文本源（评论区受限时的 Plan B）
    cid = it.get("cid")
    if cid:
        time.sleep(INTERVAL)
        try:
            rr = s.get("https://api.bilibili.com/x/v1/dm/list.so",
                       headers={**HEADERS, "Referer": f"https://www.bilibili.com/video/{bvid}"},
                       params={"oid": cid}, timeout=20)
            body = rr.content
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                import zlib
                text = zlib.decompress(body, -zlib.MAX_WBITS).decode("utf-8")
            n_dm = text.count("<d p=")
            sample = ""
            m = re.search(r"<d p=\"[^\"]*\">(.*?)</d>", text)
            if m:
                sample = m.group(1)[:40]
            print(f"\n{'弹幕 /x/v1/dm/list.so':<34}{rr.status_code:>6}{n_dm:>9}{'-':>11}{'-':>8}  样本：{sample}")
        except Exception as e:                                    # noqa: BLE001
            print(f"\n{'弹幕 /x/v1/dm/list.so':<34}{'ERR':>6}{'-':>9}{'-':>11}{'-':>8}  {type(e).__name__}: {e}")

    print("\n怎么据此定方案：")
    if preview_only and best <= ps:
        print("  · 匿名只能拿到「少量热门评论预览」，翻页被 -403 拦 → **不要把 2 万条评论当硬指标**")
        print("    方案A（推荐）：文本分析改用**弹幕**（上面那行条数通常几千条/视频，且无需登录）")
        print("    方案B：每视频取预览的 3–20 条热门评论 × 500+ 视频 ≈ 3000–8000 条，报告里声明抽样偏差")
        print("    方案C：在 .env 放自己的 SESSDATA 登录 Cookie（能翻页，但有账号风险且会过期，别写进仓库）")
    else:
        print("  · 评论可翻页 → 按「单视频实测条数 × 视频数」估总量，目标 1–2 万条")
    return 0


def probe_depth() -> int:
    """翻页深度探测：回答"M1 里程碑要的 3000 条视频，怎么凑出来？"

    已踩的坑：`page_size=50` 会让搜索接口**静默返回 0 条**（上限 20）；
    `newlist` 的 `pn` 基本不翻页（每次都是同一页）。所以体积不能靠"傻翻页"，
    要靠 ① 多关键词搜索 ② 相关推荐滚雪球 ③ 按 UP 主拉全部投稿。
    """
    s, mk = prepare_session()

    # 0) 种子：从排行拿一个视频 + 一个 UP 主 mid
    r = s.get("https://api.bilibili.com/x/web-interface/ranking/v2",
              headers=HEADERS, params=sign({"rid": 36, "type": "all"}, mk), timeout=20)
    seeds = first_list(r.json().get("data"))
    seed_bvid = seeds[0].get("bvid") if seeds else None
    seed_mid = seeds[0].get("owner", {}).get("mid") if seeds else None
    print(f"种子：bvid={seed_bvid} mid={seed_mid}（排行共 {len(seeds)} 条）")
    time.sleep(INTERVAL)

    est: dict[str, int] = {}

    # 1) newlist 是否真的翻页（ps=20）
    print("\n--- ① newlist (rid=36, ps=20) ---")
    seen: set = set()
    for pn in (1, 2, 3, 5, 10):
        r = s.get("https://api.bilibili.com/x/web-interface/newlist",
                  headers=HEADERS, params=sign({"rid": 36, "ps": 20, "pn": pn}, mk), timeout=20)
        j = r.json()
        items = first_list(j.get("data"))
        bv = [x.get("bvid") for x in items if x.get("bvid")]
        fresh = [b for b in bv if b not in seen]
        seen.update(bv)
        print(f"  pn={pn:<3} 返回 {len(items):>3} 条 | 新增 {len(fresh):>3} | 累计去重 {len(seen):>4}")
        time.sleep(INTERVAL)
    est["newlist"] = len(seen)

    # 2) 搜索深度（ps 保持 20）
    print("\n--- ② 搜索 (keyword=数据分析, page_size=20) ---")
    seen2: set = set()
    for page in (1, 2, 3, 5, 10, 20, 30):
        r = s.get("https://api.bilibili.com/x/web-interface/wbi/search/type", headers=HEADERS,
                  params=sign({"search_type": "video", "keyword": "数据分析",
                               "page": page, "page_size": 20}, mk), timeout=20)
        j = r.json()
        items = first_list(j.get("data"))
        bv = [x.get("bvid") for x in items if x.get("bvid")]
        fresh = [b for b in bv if b not in seen2]
        seen2.update(bv)
        print(f"  page={page:<3} code={j.get('code'):<4} 返回 {len(items):>3} 条 | 新增 {len(fresh):>3}"
              f" | 累计去重 {len(seen2):>4}")
        if j.get("code") != 0 or not items:
            print(f"          └ 到此为止（{j.get('message')}）")
            break
        time.sleep(INTERVAL)
    est["search_per_kw"] = len(seen2)

    # 3) 相关推荐（滚雪球：从一个视频扩出几十个）
    print("\n--- ③ 相关推荐 archive/related（滚雪球） ---")
    if seed_bvid:
        try:
            r = s.get("https://api.bilibili.com/x/web-interface/archive/related",
                      headers=HEADERS, params={"bvid": seed_bvid}, timeout=20)
            j = r.json()
            items = first_list(j.get("data"))
            est["related"] = len(items)
            print(f"  code={j.get('code')} 单个视频可扩出 {len(items)} 条相关视频")
        except Exception as e:                                    # noqa: BLE001
            print(f"  {type(e).__name__}: {e}")
        time.sleep(INTERVAL)

    # 4) UP 主投稿列表（最稳的堆量来源）
    print("\n--- ④ UP主投稿 space/wbi/arc/search ---")
    if seed_mid:
        try:
            r = s.get("https://api.bilibili.com/x/space/wbi/arc/search", headers=HEADERS,
                      params=sign({"mid": seed_mid, "ps": 30, "pn": 1,
                                   "order": "pubdate", "platform": "web",
                                   "web_location": "1550101"}, mk), timeout=20)
            j = r.json()
            dd = j.get("data") or {}
            vlist = ((dd.get("list") or {}).get("vlist")) or []
            est["space_per_up"] = len(vlist)
            total = ((dd.get("page") or {}).get("count"))
            print(f"  code={j.get('code')} 本页 {len(vlist)} 条 | 该 UP 主投稿总数 count={total}")
            if vlist:
                print(f"  样本：{str(vlist[0].get('title'))[:40]}")
        except Exception as e:                                    # noqa: BLE001
            print(f"  {type(e).__name__}: {e}")
        time.sleep(INTERVAL)

    # 5) 凑量方案
    n_kw = 14
    print("\n--- 结论：M1（≥3000 条视频）的凑量方案 ---")
    n_news = est.get("newlist", 0)
    n_search = est.get("search_per_kw", 0)
    n_rel = est.get("related", 0)
    n_space = est.get("space_per_up", 0)
    print(f"  newlist 实际可用        : ~{n_news} 条（{'能翻页' if n_news > 25 else '几乎不翻页，别指望它堆量'}）")
    print(f"  搜索 单关键词          : ~{n_search} 条 → {n_kw} 个词约 {n_search * n_kw} 条（有重叠）")
    print(f"  相关推荐 单视频        : ~{n_rel} 条 → 95 个种子扩充一轮约 {n_rel * 95} 条（重叠较多）")
    print(f"  UP主投稿 单个UP         : ~{n_space} 条/页 → 200 个 UP 主 ≈ {n_space * 200} 条（**最稳**）")
    plan_total = n_search * n_kw + n_rel * 95 + n_space * 200
    print(f"\n  推荐配比（按可靠性排序）：")
    print(f"    1. UP主投稿列表：从排行/搜索拿到 200+ 个 mid，逐个拉投稿 → 主力")
    print(f"    2. 关键词搜索：{n_kw} 个词 × 可用页数 → 保证主题覆盖")
    print(f"    3. 分区排行：8 个分区各取一轮 → 保证头部样本")
    print(f"    4. 相关推荐：对种子做一轮扩充 → 补充长尾")
    print(f"    粗估可达 {plan_total}+ 条（去重前）→ "
          f"{'✅ 够 3000 条' if plan_total >= 3000 else '⚠️ 仍不足，需扩展分区或时间窗口'}")
    print("  采集时以「拿到多少条」为准，不要预设页数 —— 接口上限会变。")
    return 0


def search_check(rounds: int = 3, wait: float = 5.0) -> int:
    """搜索接口健康检查：判断"返回 0 条"是代码问题还是被临时限流。

    为什么要它：搜索接口在连续请求后会**静默返回 0 条**（不是报错！）。
    采集脚本必须能区分"我没写对"和"现在被限流了"——否则你会对着正确的代码调一晚上。
    """
    s, mk = prepare_session()
    print(f"搜索接口健康检查：连打 {rounds} 轮，间隔 {wait}s")
    ok = 0
    for i in range(rounds):
        r = s.get("https://api.bilibili.com/x/web-interface/wbi/search/type", headers=HEADERS,
                  params=sign({"search_type": "video", "keyword": "数据分析",
                               "page": 1, "page_size": 20}, mk), timeout=20)
        j = r.json()
        d = j.get("data") or {}
        n = len(first_list(d))
        risk = "v_voucher" in d
        print(f"  #{i + 1} code={j.get('code')} 条数={n} data_keys={list(d.keys())[:6]}"
              + ("   ← v_voucher：被风控/限流" if risk else ""))
        ok += 1 if n else 0
        time.sleep(wait)
    print(f"\n{rounds} 轮中 {ok} 轮拿到数据。")
    if ok:
        print("接口目前可用。")
    else:
        print("接口当前被限流 → 等 10–30 分钟或换网络。**采集脚本必须容忍这种情况**：")
        print("  重试 + 退避 + 跳过该关键词 + 断点续爬，绝不要因为一轮 0 条就判定'代码错了'。")
    return 0 if ok else 1


def main() -> int:
    print("=" * 74)
    print("B站接口可行性探测（诊断，非采集）")
    print("=" * 74)
    s, mk = prepare_session()

    # ---- ③ 候选接口（rid=36 是知识区）
    ranking = probe("分区排行 ranking/v2 (rid=36)", "https://api.bilibili.com/x/web-interface/ranking/v2",
                    {"rid": 36, "type": "all"}, mk, signed=True)
    time.sleep(INTERVAL)
    probe("综合热门 popular", "https://api.bilibili.com/x/web-interface/popular",
          {"ps": 20, "pn": 1}, mk, signed=True)
    time.sleep(INTERVAL)
    probe("分区最新 newlist (rid=36)", "https://api.bilibili.com/x/web-interface/newlist",
          {"rid": 36, "ps": 20, "pn": 1}, mk, signed=True)
    time.sleep(INTERVAL)
    probe("关键词搜索 search/type（带 buvid3）",
          "https://api.bilibili.com/x/web-interface/wbi/search/type",
          {"search_type": "video", "keyword": "数据分析", "page": 1, "page_size": 20}, mk, signed=True)
    time.sleep(INTERVAL)

    # ---- ④ 用排行里的 bvid 试视频详情
    bvid = None
    if ranking:
        items = first_list(ranking.get("data"))
        if items:
            bvid = items[0].get("bvid")
    if bvid:
        probe(f"视频详情 view ({bvid})", "https://api.bilibili.com/x/web-interface/view",
              {"bvid": bvid}, mk, signed=False)
    else:
        results.append(("SKIP", "视频详情 view", "没拿到 bvid（排行接口未成功），稍后再试"))

    # ---- 汇总
    print()
    icon = {"OK": "[OK]   ", "RISK": "[RISK] ", "EMPTY": "[EMPTY]", "FAIL": "[FAIL] ", "SKIP": "[SKIP] "}
    for st, name, detail in results:
        print(f"{icon[st]} {name}\n         {detail}")

    ok = [r for r in results if r[0] == "OK"]
    print("-" * 74)
    print(f"可用接口 {len(ok)} 个 / 风险或失败 {len(results) - len(ok)} 个")
    print("\n怎么用这个结果定采集方案：拿 [OK] 的接口当主力，[RISK] 的当成备选；")
    print("如果只有排行/热门可用 → 就按「按分区取头部内容」的思路设计样本，一样能回答 4 个业务问题。")

    out = ROOT / "data" / "raw" / "probe_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([{"status": a, "api": b, "detail": c} for a, b, c in results],
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已落盘 {out.relative_to(ROOT)}（可写进 docs/踩坑记录.md）")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="B站接口可行性探测 / 分区 tid 映射")
    ap.add_argument("--map-tids", type=int, nargs="?", const=36, metavar="RID",
                    help="聚合 tid→二级分区名 映射，默认知识区 rid=36")
    ap.add_argument("--comments", action="store_true",
                    help="探测评论接口：不登录能翻几页、每页几条、总量多少")
    ap.add_argument("--depth", action="store_true",
                    help="探测翻页深度：估算最多能采到多少条视频（决定 M1 怎么凑量）")
    ap.add_argument("--search-check", action="store_true",
                    help="搜索接口健康检查：判断 0 条是代码问题还是被限流")
    a = ap.parse_args()
    if a.search_check:
        raise SystemExit(search_check())
    if a.depth:
        raise SystemExit(probe_depth())
    if a.comments:
        raise SystemExit(probe_comments())
    if a.map_tids is not None:
        raise SystemExit(map_zone_tids(a.map_tids))
    raise SystemExit(main())

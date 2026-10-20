"""S3b：按关键词抓「求职/职场」内容 —— 走 search/all/v2 聚合搜索接口

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.spider.search_kw

为什么用这个接口（面试可讲）：
  - wbi 签名的 `search/type` 接口连续请求后被风控（code=0 但只回 v_voucher）；
    带 buvid3/buvid4 指纹、换 session、等数小时都无效。
  - 实测 `x/web-interface/search/all/v2`（网页聚合搜索用）不需要签名、未被限流，
    返回 12 个聚合块，其中 result_type == "video" 的那块就是视频列表（20 条/页，50 页）。
  - 这个接口返回的字段和 ranking/newlist 完全不同：标题带 <em> 高亮标签、
    duration 是 "10:51" 字符串、播放叫 play、二级分区叫 typename —— 必须单独打平。
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

OUT = ROOT / "data" / "raw" / "videos_kw.json"
API = "https://api.bilibili.com/x/web-interface/search/all/v2"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://search.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
}

# 你要抓的关键词（改这里就能换选题方向）
KEYWORDS = ["求职面试", "简历修改", "转行", "应届生求职", "职场沟通"]
PAGES_PER_KW = 3      # 每个词抓几页（每页 20 条）
SLEEP = 4.0           # 每次请求间隔（这个接口虽然没被拦，但还是别打太快）


# ============================================================
#  TODO A：把 "10:51" 转成 651 秒，"1:02:03" 转成 3723 秒
#  提示：先 s.split(":") 得到 ["10","51"]，再按位数乘 60
#       2 段 = 分:秒 ；3 段 = 时:分:秒
#  解析不出来时返回 None（别让脏数据搞崩整个程序）
# ============================================================
def parse_duration(s: str) -> int | None:
    """'10:51' -> 651 ; '1:02:03' -> 3723 ; 失败 -> None"""
    try:
        parts = str(s).split(":")
        nums = [int(p) for p in parts]
    except (ValueError, AttributeError):
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


# ============================================================
#  TODO B：去掉标题里的 HTML 高亮标签
#  输入：'<em class="keyword">面试</em>高频题拆解'
#  输出：'面试高频题拆解'
#  提示：用正则 re.sub(r"<[^>]+>", "", s) 一次干掉所有 <...>
# ============================================================
def clean_title(s: str) -> str:
    """去掉 <em class="keyword"> 这类标签"""
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def flatten_search(v: dict, keyword: str) -> dict:
    """把聚合搜索的视频条目打平成和 ranking 一致的字段。"""
    pub = datetime.fromtimestamp(int(v.get("pubdate") or 0)) if v.get("pubdate") else None
    return {
        "bvid": v.get("bvid"),
        "aid": v.get("aid"),
        "title": clean_title(v.get("title")),
        "description": (v.get("description") or v.get("desc") or "")[:500],
        "mid": v.get("mid"),
        "up_name": v.get("author"),
        "zone": "知识",
        "sub_zone": v.get("typename"),
        "duration_sec": parse_duration(v.get("duration")),
        "pub_time": pub.strftime("%Y-%m-%d %H:%M:%S") if pub else None,
        "pub_hour": pub.hour if pub else None,
        "pub_weekday": pub.isoweekday() if pub else None,
        "view_cnt": v.get("play"),
        "like_cnt": v.get("like"),
        "coin_cnt": None,          # 搜索接口不给投币数（已知缺口，报告里要写）
        "fav_cnt": v.get("favorites"),
        "danmaku_cnt": v.get("video_review"),
        "reply_cnt": v.get("review"),
        "share_cnt": None,         # 同上
        "tag_list": v.get("tag"),
        "source_keyword": f"kw:{keyword}",
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_json(session: requests.Session, params: dict, tries: int = 3) -> dict:
    last: Exception | None = None
    for i in range(1, tries + 1):
        try:
            return session.get(API, params=params, timeout=20).json()
        except Exception as e:
            last = e
            if i < tries:
                print(f"[retry {i}/{tries}] {type(e).__name__}: {str(e)[:60]}")
                time.sleep(3 * i)
    raise RuntimeError(f"请求失败: {type(last).__name__}: {last}") from last


def pick_video_block(payload: dict) -> list:
    """从 12 个聚合块里挑出 result_type == 'video' 的那块。"""
    for blk in (payload.get("data") or {}).get("result") or []:
        if blk.get("result_type") == "video":
            return blk.get("data") or []
    return []


def main() -> int:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.bilibili.com", timeout=20)
    time.sleep(1.5)

    rows: dict[str, dict] = {}
    req = 0

    # ============================================================
    #  TODO C：双层循环 —— 外层关键词，内层页码
    #  伪代码：
    #    for kw in KEYWORDS:
    #        for page in range(1, PAGES_PER_KW + 1):
    #            j = get_json(s, {"keyword": kw, "page": page})
    #            vids = pick_video_block(j)
    #            req += 1
    #            new = 0
    #            for v in vids:
    #                if v.get("bvid") in rows:
    #                    continue
    #                rows[v["bvid"]] = flatten_search(v, kw)
    #                new += 1
    #            print(f"[{kw} p{page}] 拿到 {len(vids)} 条，新增 {new}，累计 {len(rows)}")
    #            time.sleep(SLEEP)
    # ============================================================

    for kw in KEYWORDS:
        for page in range(1, PAGES_PER_KW + 1):
            j = get_json(s, {"keyword": kw, "page": page})
            vids = pick_video_block(j)
            req += 1
            new = 0
            for v in vids:
                if v.get("bvid") in rows:
                    continue
                rows[v["bvid"]] = flatten_search(v, kw)
                new += 1
            print(f"[{kw} p{page}] 拿到 {len(vids)} 条，新增 {new}，累计 {len(rows)}")
            time.sleep(SLEEP)


    out = list(rows.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[done] 写入 {OUT}")
    print(f"[done] 条数 = {len(out)} | 请求 {req} 次")
    if out:
        bad = sum(1 for r in out if r["duration_sec"] is None)
        print(f"[done] 时长解析失败 = {bad} 条")
        kw = {}
        for r in out:
            kw[r["source_keyword"]] = kw.get(r["source_keyword"], 0) + 1
        print("[done] 各关键词条数 =", kw)
    else:
        print("[warn] 0 条 —— TODO C 还没填吧？")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

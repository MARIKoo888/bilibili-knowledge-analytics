"""采集弹幕 —— 第10周核心任务

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.spider.fetch_danmaku

前置：video 表必须有 cid（已由 src/spider/fetch_cid.py 补齐 431 条）

接口：GET https://api.bilibili.com/x/v1/dm/list.so?oid=<cid>
  - 无需登录，返回 text/xml
  - 单个视频几百到几千条，实测 "面试高频题拆解" 有 961 条

XML 结构：
  <d p="出现秒,模式,字号,颜色,时间戳,弹幕池,用户哈希,弹幕ID,权重">弹幕内容</d>
    下标:   0     1   2    3      4      5      6       7     8

设计要点（面试可讲）：
  1. 按 (bvid, 内容) 去重并记录 dup_count —— 刷屏"哈哈哈哈×200"会污染词频，
     去重后 dup_count 本身就是有价值的指标（刷屏强度）
  2. dmid 是主键，但去重后同一文本只留第一条，所以用"首次出现的 dmid"
  3. 限速 + 重试 + 单个视频失败不影响整批
  4. 按播放量降序取视频（播放高的弹幕多，性价比高）
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import db_url  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DM_API = "https://api.bilibili.com/x/v1/dm/list.so"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
}

LIMIT_VIDEOS = 300      # 取播放量最高的前 N 个视频
SUB_ZONE = "职业职场"    # 只采这个分区的弹幕；设为 None 则采全部分区
SLEEP = 3.0             # 每次请求间隔（实测 1.5s 会被 412 限流）
RETRY_WAIT = (10, 30, 60)  # 重试等待阶梯（限流时需要更长冷却）

# 匹配 <d p="...">内容</d>
DM_PATTERN = re.compile(r'<d p="([^"]+)">([^<]*)</d>')
# 过滤纯符号/空白（保留长度>=1 的实际文本，空白和纯符号单独处理）
SYMBOL_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)


def parse_danmaku(xml: str, bvid: str, cid: int) -> tuple[list[dict], int]:
    """解析 XML，按内容去重，返回 (待插入行, 原始条数)。"""
    raw_items = DM_PATTERN.findall(xml)
    total = len(raw_items)

    # 内容 -> (首次出现的 dmid, 出现次数, 其他字段)
    seen: dict[str, dict] = Counter()          # 只用来数次数
    first: dict[str, dict] = {}                # 只存第一次出现的完整记录

    for p, content in raw_items:
        content = content.strip()
        if not content:
            continue
        try:
            parts = p.split(",")
            send_sec = int(float(parts[0]))
            mode = int(parts[1])
            font_size = int(parts[2])
            color = int(parts[3])
            ts = int(parts[4])
            dmid = int(parts[7])
        except (IndexError, ValueError):
            continue

        key = content
        seen[key] += 1
        if key not in first:
            first[key] = {
                "dmid": dmid,
                "cid": cid,
                "bvid": bvid,
                "content": content[:200],
                "send_time_sec": send_sec,
                "mode": mode,
                "font_size": font_size,
                "color": color,
                "ctime": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            }

    rows = []
    for key, rec in first.items():
        rec["dup_count"] = seen[key]
        rows.append(rec)
    return rows, total


def main() -> int:
    engine = create_engine(db_url(), pool_pre_ping=True)

    # 取播放最高的若干视频（cid 必须已补齐）；可按分区限定；跳过已采过的（可断点续跑）
    sql = ("SELECT bvid, cid, view_cnt, sub_zone FROM video v "
           "WHERE cid IS NOT NULL "
           "AND v.bvid NOT IN (SELECT DISTINCT bvid FROM danmaku)")
    params: dict = {"n": LIMIT_VIDEOS}
    if SUB_ZONE:
        sql += " AND sub_zone = :z"
        params["z"] = SUB_ZONE
    sql += " ORDER BY view_cnt DESC LIMIT :n"
    with engine.connect() as conn:
        vids = conn.execute(text(sql), params).fetchall()
    print(f"[plan] 目标视频 {len(vids)} 个" + (f"（分区={SUB_ZONE}）" if SUB_ZONE else "（全部分区）"))

    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.bilibili.com", timeout=20)

    t0 = time.time()
    total_raw = total_kept = 0
    ok_videos = 0
    all_rows: list[dict] = []

    for i, (bvid, cid, view_cnt, sub_zone) in enumerate(vids, 1):
        xml = None
        for attempt, wait in enumerate((0,) + RETRY_WAIT, 1):
            if wait:
                print(f"   [retry {attempt-1}] {bvid} 等待 {wait}s（疑似限流）")
                time.sleep(wait)
            try:
                r = s.get(DM_API, params={"oid": cid}, timeout=20)
                if r.status_code == 200 and r.content:
                    xml = r.content.decode("utf-8", "replace")
                    break
                if r.status_code in (412, 429, 403):
                    continue          # 限流/风控 -> 走更长冷却后重试
                print(f"   [skip] {bvid} HTTP {r.status_code} len={len(r.content)}")
                break                 # 空响应（该视频真没弹幕）-> 不重试
            except Exception as e:
                print(f"   [err] {bvid} {type(e).__name__}: {str(e)[:40]}")
                continue

        if not xml:
            print(f"[{i}/{len(vids)}] {bvid} 失败，跳过")
            time.sleep(SLEEP)
            continue

        rows, raw_n = parse_danmaku(xml, bvid, cid)
        total_raw += raw_n
        total_kept += len(rows)
        all_rows.extend(rows)
        ok_videos += 1

        if i % 10 == 0 or i == len(vids):
            el = time.time() - t0
            print(f"[{i}/{len(vids)}] 原始 {total_raw} 条 → 去重后 {total_kept} 条 "
                  f"| 已用 {el:.0f}s")

        time.sleep(SLEEP)

    print(f"\n[collect] 成功视频 {ok_videos}/{len(vids)}")
    print(f"[collect] 原始弹幕 {total_raw} → 去重后 {total_kept}")

    if not all_rows:
        print("[error] 一条都没抓到")
        return 1

    # 清掉这些视频已有的旧数据，避免重复跑时主键冲突
    bvids = sorted({r["bvid"] for r in all_rows})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM danmaku WHERE bvid IN :bs").bindparams(
            __import__("sqlalchemy").bindparam("bs", expanding=True)), {"bs": bvids})

    # 批量插入
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO danmaku (dmid, cid, bvid, content, send_time_sec, mode, "
            "font_size, color, ctime, dup_count) VALUES "
            "(:dmid, :cid, :bvid, :content, :send_time_sec, :mode, "
            ":font_size, :color, :ctime, :dup_count)"
        ), all_rows)

    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM danmaku")).scalar()
        nv = conn.execute(text("SELECT COUNT(DISTINCT bvid) FROM danmaku")).scalar()
    print(f"[db] danmaku 表共 {n} 条，覆盖 {nv} 个视频")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

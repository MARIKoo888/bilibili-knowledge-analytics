"""补采 cid（弹幕池 id）—— 第10周弹幕分析的前置步骤

用法：
    $env:PYTHONUTF8=1
    # 先补列（只需执行一次）
    #   ALTER TABLE video ADD COLUMN cid BIGINT COMMENT '弹幕池id' AFTER aid;
    .\\.venv\\Scripts\\python.exe -m src.spider.fetch_cid

为什么需要这一步：
  - 弹幕接口 /x/v1/dm/list.so 只认 cid(=弹幕池id)，不认 bvid
  - 我们前面三个爬虫的 flatten() 没抽 cid，所以库里没有 → 只能回头补
  - 用 /x/web-interface/view?bvid=  一次拿一个 cid（顺便也能拿到最新播放数）

设计：
  - 只补 cid 为空的视频，已补过的跳过（可反复中断续跑）
  - 限速 1.2s + 重试，遇 -352/-412 就等待后继续，绝不整批崩掉
  - 每 20 条打印一次进度，方便估时间
"""
from __future__ import annotations

import sys
import time

import requests
from sqlalchemy import create_engine, text

ROOT_PARENT = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_PARENT))

from src.config import db_url  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
}
SLEEP = 1.2          # 每次请求间隔
RETRY_WAIT = (5, 15)  # 失败等待阶梯


def main() -> int:
    engine = create_engine(db_url(), pool_pre_ping=True)

    # 取还缺 cid 的视频，优先取播放高的（弹幕多的视频更值得抓）
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT bvid FROM video WHERE cid IS NULL ORDER BY view_cnt DESC"
        )).fetchall()
    todo = [r[0] for r in rows]
    print(f"[todo] 待补 cid = {len(todo)} 条")
    if not todo:
        print("[done] 已经全部补完，无需再跑")
        return 0

    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.bilibili.com", timeout=20)

    ok = fail = 0
    t0 = time.time()
    for i, bvid in enumerate(todo, 1):
        cid = None
        for attempt, wait in enumerate((0,) + RETRY_WAIT, 1):
            if wait:
                print(f"   [retry {attempt-1}] {bvid} 等待 {wait}s")
                time.sleep(wait)
            try:
                j = s.get(VIEW_API, params={"bvid": bvid}, timeout=20).json()
                code = j.get("code")
                if code == 0:
                    cid = (j.get("data") or {}).get("cid")
                    break
                if code in (-352, -412, -509):
                    continue          # 风控/限流 -> 走重试
                print(f"   [skip] {bvid} code={code} msg={j.get('message')}")
                break
            except Exception as e:     # 网络抖动
                print(f"   [err] {bvid} {type(e).__name__}: {str(e)[:50]}")
                continue

        if cid:
            with engine.begin() as conn:
                conn.execute(text("UPDATE video SET cid=:c WHERE bvid=:b"),
                             {"c": cid, "b": bvid})
            ok += 1
        else:
            fail += 1

        if i % 20 == 0 or i == len(todo):
            el = time.time() - t0
            eta = el / i * (len(todo) - i)
            print(f"[{i}/{len(todo)}] 成功 {ok} 失败 {fail} | 已用 {el:.0f}s 预计还需 {eta:.0f}s")

        time.sleep(SLEEP)

    print(f"\n[done] 成功 {ok} / 失败 {fail}")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(cid) FROM video")).scalar()
    print(f"[done] video 表中已有 cid 的行数 = {n}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""采集 v0：知识区排行榜 -> data/raw/sample.json

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe src\\spider\\search.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# 强制 UTF-8，否则 Windows 控制台中文会变乱码（踩坑记录 #3）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "sample.json"
API = "https://api.bilibili.com/x/web-interface/ranking/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.bilibili.com/",
}


MAX_TRY = 3
BACKOFF = (2, 5, 10)  # 每次失败后等 2s / 5s / 10s


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    """请求并返回 JSON。失败按 BACKOFF 退避重试，仍失败才抛异常。

    面试可讲：网络重置/限流是常态，不是故障。采集脚本必须"重试→跳过→继续"，
    而不是让整个任务崩掉。
    """
    last_err: Exception | None = None
    for attempt in range(1, MAX_TRY + 1):
        try:
            r = session.get(url, params=params, timeout=15)
            return r.json()
        except Exception as e:          # 网络层错误 / JSON 解析错误
            last_err = e
            wait = BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]
            if attempt < MAX_TRY:
                print(f"[retry {attempt}/{MAX_TRY}] {type(e).__name__}: {str(e)[:70]} -> {wait}s 后重试")
                time.sleep(wait)
    raise RuntimeError(
        f"请求失败（已重试 {MAX_TRY} 次）: {type(last_err).__name__}: {last_err}"
    ) from last_err


def fetch(session: requests.Session, rid: int = 36) -> list:
    """请求一次排行榜，返回原始 list（95 条）。"""
    payload = get_json(session, API, params={"rid": rid, "type": "all"})
    if payload.get("code") != 0:
        raise RuntimeError(f"接口返回错误 code={payload.get('code')} msg={payload.get('message')}")
    videos = payload["data"]["list"]
    print(f"[fetch] 拿到 {len(videos)} 条")
    return videos


def flatten(v: dict) -> dict:
    """把豆瓣式嵌套结构压平成一行（字段和 MySQL 表对应）。"""
    st = v.get("stat") or {}
    ow = v.get("owner") or {}
    pub = datetime.fromtimestamp(v["pubdate"])
    return {
        "bvid": v.get("bvid"),
        "aid": v.get("aid"),
        "title": v.get("title"),
        "description": (v.get("desc") or "")[:500],
        "mid": ow.get("mid"),
        "up_name": ow.get("name"),
        "zone": "知识",
        "sub_zone": v.get("tname"),
        "duration_sec": v.get("duration"),
        "pub_time": pub.strftime("%Y-%m-%d %H:%M:%S"),
        "pub_hour": pub.hour,
        "pub_weekday": pub.isoweekday(),
        "view_cnt": st.get("view"),
        "like_cnt": st.get("like"),
        "coin_cnt": st.get("coin"),
        "fav_cnt": st.get("favorite"),
        "danmaku_cnt": st.get("danmaku"),
        "reply_cnt": st.get("reply"),
        "share_cnt": st.get("share"),
        "source_keyword": "ranking_36",
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main() -> int:
    session = requests.Session()
    session.headers.update(HEADERS)

    # 先访问主站拿基础 Cookie，防 -101（失败也不致命，继续往下走）
    try:
        session.get("https://www.bilibili.com", timeout=15)
        print("[cookie] 主站已访问")
    except Exception as e:
        print(f"[cookie] 主站访问失败但不影响后续: {type(e).__name__}")
    time.sleep(1.5)  # 限速

    raw = fetch(session)

    # TODO 1：raw 是一个"列表"（95 个 dict）。遍历它，每条调用 flatten()
    #         把结果收进下面这个空列表里。
    rows = []

    # TODO 2：把循环写在这里（缩进 4 个空格）
    for v in raw:
        rows.append(flatten(v))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[done] 写入 {OUT}")
    print(f"[done] 条数 = {len(rows)}")
    if rows:
        print(f"[done] 首条 = {rows[0]['title'][:40]} | 播放 {rows[0]['view_cnt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

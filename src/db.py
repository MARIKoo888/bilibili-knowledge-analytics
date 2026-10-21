"""入库：data/processed/videos.csv -> MySQL bili 库

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.db

三件事：
  1. 读 CSV
  2. 拆成两张表：up_author（UP主，去重）/ video（视频，主键 bvid）
  3. 写入 MySQL，并用 SELECT COUNT(*) 验证

踩过的坑（重要）：
  - pandas 的 Int64 可空类型带 pd.NA，直接 to_sql 会报错 -> 必须转成 None
  - MySQL 开了 STRICT_TRANS_TABLES：字段超长直接报错，不会自动截断 -> 必须自己 truncate
  - pub_time 是字符串，要让 MySQL 认成 datetime -> 显式 pd.to_datetime
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import db_url  # noqa: E402

CSV = ROOT / "data" / "processed" / "videos.csv"

# video 表的列（顺序必须和 DDL 一致；up_name 不在这里，它进 up_author）
VIDEO_COLS = [
    "bvid", "aid", "title", "description", "mid", "zone", "sub_zone", "tag_list",
    "duration_sec", "pub_time", "pub_hour", "pub_weekday",
    "view_cnt", "like_cnt", "coin_cnt", "fav_cnt", "danmaku_cnt", "reply_cnt",
    "share_cnt", "is_duration_outlier", "source_keyword", "crawled_at",
]

# 文本字段的长度上限（对齐 DDL，超长要截断，否则严格模式报错）
MAX_LEN = {
    "bvid": 20,
    "title": 300,
    "sub_zone": 64,
    "zone": 64,
    "tag_list": 500,
    "source_keyword": 64,
}


def to_none(x):
    """把 pd.NA / NaN / Int64 里的空值统一成 Python None。"""
    if pd.isna(x):
        return None
    return x


def main() -> int:
    if not CSV.exists():
        print(f"[error] 找不到 {CSV}，先跑 python -m src.clean")
        return 1

    df = pd.read_csv(CSV, dtype={"bvid": str})
    print(f"[read] {CSV.name}: {len(df)} 行，{len(df.columns)} 列")

    # ---------- 1) 准备 video 表 ----------
    v = df[VIDEO_COLS].copy()

    # 文本截断
    for col, n in MAX_LEN.items():
        if col in v.columns:
            v[col] = v[col].astype("string").str.slice(0, n)

    # 时间列
    v["pub_time"] = pd.to_datetime(v["pub_time"], errors="coerce")
    v["crawled_at"] = pd.to_datetime(v["crawled_at"], errors="coerce")

    # 所有空值 -> None（否则 MySQL 驱动会报 nan/NA 无法转换）
    v = v.astype(object).where(pd.notna(v), None)

    print(f"[video] 待写入 {len(v)} 行")
    print(f"[video] bvid 唯一 = {v['bvid'].nunique()}")

    # ---------- 2) 准备 up_author 表 ----------
    u = (df[["mid", "up_name", "crawled_at"]]
         .dropna(subset=["mid"])
         .drop_duplicates(subset=["mid"])
         .rename(columns={"up_name": "name"}))
    u["name"] = u["name"].astype("string").str.slice(0, 128)
    u["mid"] = u["mid"].astype("int64")
    u["crawled_at"] = pd.to_datetime(u["crawled_at"], errors="coerce")
    u = u.astype(object).where(pd.notna(u), None)
    print(f"[up_author] 待写入 {len(u)} 行（去重后 UP主数）")

    # ---------- 3) 写入 ----------
    engine = create_engine(db_url(), pool_pre_ping=True)

    # 先清空，避免重复跑时主键冲突（458 行的小表，直接重灌最省事）
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM video"))
        conn.execute(text("DELETE FROM up_author"))

    u.to_sql("up_author", engine, if_exists="append", index=False, method="multi", chunksize=500)
    print("[db] up_author 写入完成")

    v.to_sql("video", engine, if_exists="append", index=False, method="multi", chunksize=500)
    print("[db] video 写入完成")

    # ---------- 4) 验证 ----------
    print("\n===== 入库验证 =====")
    with engine.connect() as conn:
        n_video = conn.execute(text("SELECT COUNT(*) FROM video")).scalar()
        n_up = conn.execute(text("SELECT COUNT(*) FROM up_author")).scalar()
        n_zone = conn.execute(text(
            "SELECT COUNT(DISTINCT sub_zone) FROM video")).scalar()
        med = conn.execute(text(
            "SELECT AVG(view_cnt) FROM ("
            "  SELECT view_cnt, ROW_NUMBER() OVER (ORDER BY view_cnt) rn,"
            "         COUNT(*) OVER () cnt FROM video WHERE is_duration_outlier=0"
            ") t WHERE rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))")).scalar()

    print(f"video     行数 = {n_video}（CSV 里是 {len(v)}）")
    print(f"up_author 行数 = {n_up}")
    print(f"二级分区数 = {n_zone}")
    print(f"播放中位数（排除时长异常）= {int(med) if med else None}")

    ok = (n_video == len(v))
    print("\n结果:", "✅ 一致，M1 达成" if ok else "❌ 行数不一致，检查错误日志")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

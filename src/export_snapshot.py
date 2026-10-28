"""导出云端快照：把 MySQL 里的分析数据导成小 CSV，供 Streamlit Cloud 使用

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.export_snapshot

产出（data/snapshot/，会推到 GitHub）：
    video.csv            458 行 × 22 列（看板所有"按视频算"的指标都基于它）
    danmaku_zone.csv     各分区弹幕聚合（云端不需要 8 万条原始弹幕）
    cluster_topics.csv   主题聚类汇总
    meta.json            数据截面、导出时间、行数（看板用于显示"当前数据版本"）

为什么这样做（面试可讲）：
  云端部署的看板连不到本机 MySQL。有两种解法：
    A. 把数据导出成 CSV 一起进仓库（本方案）—— 快、免费、数据量小
    B. 用云数据库（Aiven/TiDB Cloud）—— 真实但配置麻烦、易过期
  本项目选 A，因为看板只需要 458 行视频 + 几个聚合表；
  原始的 8 万条弹幕只用于离线分析，不进云端。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import db_url  # noqa: E402

OUT_DIR = ROOT / "data" / "snapshot"

# 看板需要的所有"按视频算"的列
VIDEO_COLS = """
    bvid, aid, cid, title, mid, zone, sub_zone, tag_list,
    duration_sec, pub_time, pub_hour, pub_weekday,
    view_cnt, like_cnt, fav_cnt, danmaku_cnt, reply_cnt,
    is_duration_outlier, source_keyword, crawled_at
"""

DANMAKU_ZONE_SQL = """
    SELECT v.sub_zone AS sub_zone,
           COUNT(DISTINCT d.bvid) AS video_cnt,
           COUNT(*)               AS danmaku_cnt,
           ROUND(COUNT(*)/COUNT(DISTINCT d.bvid), 0) AS danmaku_per_video
    FROM danmaku d JOIN video v ON d.bvid = v.bvid
    GROUP BY v.sub_zone
    ORDER BY danmaku_cnt DESC
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url(), pool_pre_ping=True)

    # 1) 视频明细
    with engine.connect() as conn:
        v = pd.read_sql(text(f"SELECT {VIDEO_COLS} FROM video"), conn)
    v.to_csv(OUT_DIR / "video.csv", index=False, encoding="utf-8-sig")
    print(f"[export] video.csv           {len(v)} 行 × {len(v.columns)} 列")

    # 2) 弹幕分区聚合
    with engine.connect() as conn:
        d = pd.read_sql(text(DANMAKU_ZONE_SQL), conn)
    d.to_csv(OUT_DIR / "danmaku_zone.csv", index=False, encoding="utf-8-sig")
    print(f"[export] danmaku_zone.csv    {len(d)} 行")

    # 3) 主题聚类汇总（从本地 clusters.csv 汇总，不依赖 MySQL）
    cl_path = ROOT / "data" / "processed" / "clusters.csv"
    if cl_path.exists():
        cl = pd.read_csv(cl_path)
        if "topic_name" in cl.columns:
            g = (cl.groupby(["cluster", "topic_name"]).size()
                 .reset_index(name="n").sort_values("n", ascending=False))
            g["pct"] = (g["n"] / len(cl) * 100).round(1)
            g.to_csv(OUT_DIR / "cluster_topics.csv", index=False, encoding="utf-8-sig")
            print(f"[export] cluster_topics.csv  {len(g)} 行")
        else:
            print("[skip ] clusters.csv 没有 topic_name 列，先重跑 src.nlp.cluster")
    else:
        print("[skip ] 没有 clusters.csv，跳过主题汇总")

    # 4) 元信息
    meta = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_snapshot": "2026-10-19 ~ 2026-10-27",
        "video_rows": int(len(v)),
        "zones": int(v["sub_zone"].nunique()),
        "up_count": int(v["mid"].nunique()),
        "danmaku_total": int(d["danmaku_cnt"].sum()) if len(d) else 0,
        "note": "云端看板读此快照；8 万条原始弹幕仅用于离线分析，不入库",
    }
    (OUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] meta.json")

    total_kb = sum(f.stat().st_size for f in OUT_DIR.glob('*')) / 1024
    print(f"\n[done] 快照共 {total_kb:.0f} KB → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

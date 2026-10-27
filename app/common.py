"""看板共享层：数据库连接 + 缓存查询 + 类型清洗

按 Streamlit 最佳实践：
  - @st.cache_resource 放"连接"（不该重复创建的对象）
  - @st.cache_data    放"数据"（可序列化结果）
  - 业务逻辑集中在模块里，页面文件保持"直接脚本"
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from src.config import db_url  # noqa: E402

TTL = 600  # 缓存 10 分钟


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(db_url(), pool_pre_ping=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """MySQL 的 AVG/ROUND 返回 decimal.Decimal，Streamlit 画图会 TypeError -> 转 float。"""
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda x: float(x) if isinstance(x, Decimal) else x)
    return df


def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        res = conn.execute(text(sql), params or {})
        df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    return _clean(df)


def query_one(sql: str, params: dict | None = None) -> dict:
    with get_engine().connect() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


# ---------------------------------------------------------------- 查询
@st.cache_data(ttl=TTL)
def kpi() -> dict:
    return query_one("""
        SELECT COUNT(*)                          AS 视频数,
               COUNT(DISTINCT mid)               AS UP主数,
               COUNT(DISTINCT sub_zone)          AS 分区数,
               ROUND(AVG(view_cnt))              AS 均值播放,
               SUM(is_duration_outlier)          AS 异常条数,
               (SELECT COUNT(*) FROM danmaku)    AS 弹幕数
        FROM video
    """)


@st.cache_data(ttl=TTL)
def median_by(dim: str) -> pd.DataFrame:
    """按指定维度算播放中位数。dim 只允许白名单值（防注入）。"""
    allowed = {"sub_zone", "source_keyword", "pub_weekday"}
    if dim not in allowed:
        raise ValueError(f"不支持的维度: {dim}")
    return query_df(f"""
        WITH r AS (
            SELECT {dim} AS dim, view_cnt,
                   ROW_NUMBER() OVER (PARTITION BY {dim} ORDER BY view_cnt) AS rn,
                   COUNT(*)     OVER (PARTITION BY {dim})                   AS cnt
            FROM video WHERE is_duration_outlier = 0
        )
        SELECT dim AS 维度,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                              THEN view_cnt END)) AS 播放中位数,
               MAX(cnt) AS 样本量
        FROM r GROUP BY dim HAVING MAX(cnt) >= 10
        ORDER BY 播放中位数 DESC
    """)


@st.cache_data(ttl=TTL)
def month_trend() -> pd.DataFrame:
    return query_df("""
        WITH r AS (
            SELECT DATE_FORMAT(pub_time,'%%Y-%%m') AS ym, view_cnt,
                   ROW_NUMBER() OVER (PARTITION BY DATE_FORMAT(pub_time,'%%Y-%%m')
                                      ORDER BY view_cnt) AS rn,
                   COUNT(*) OVER (PARTITION BY DATE_FORMAT(pub_time,'%%Y-%%m')) AS cnt
            FROM video WHERE is_duration_outlier = 0 AND pub_time IS NOT NULL
        )
        SELECT ym AS 月份, MAX(cnt) AS 视频数,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                              THEN view_cnt END)) AS 播放中位数
        FROM r GROUP BY ym ORDER BY ym
    """)


@st.cache_data(ttl=TTL)
def duration_bins(only_zc: bool) -> pd.DataFrame:
    extra = "AND sub_zone = '职业职场'" if only_zc else ""
    return query_df(f"""
        WITH b AS (
            SELECT view_cnt,
                   CASE WHEN duration_sec < 180  THEN '1_<3分'
                        WHEN duration_sec < 480  THEN '2_3-8分'
                        WHEN duration_sec < 900  THEN '3_8-15分'
                        WHEN duration_sec < 1800 THEN '4_15-30分'
                        ELSE '5_>30分' END AS bucket
            FROM video WHERE is_duration_outlier = 0 {extra}
        ), r AS (
            SELECT bucket, view_cnt,
                   ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY view_cnt) AS rn,
                   COUNT(*) OVER (PARTITION BY bucket) AS cnt
            FROM b
        )
        SELECT bucket AS 时长桶,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                              THEN view_cnt END)) AS 播放中位数,
               MAX(cnt) AS 样本量
        FROM r GROUP BY bucket ORDER BY bucket
    """)


@st.cache_data(ttl=TTL)
def weekday_hour() -> pd.DataFrame:
    return query_df("""
        SELECT pub_weekday AS 星期,
               CASE WHEN pub_hour < 12 THEN '上午' WHEN pub_hour < 18 THEN '下午'
                    ELSE '晚间' END AS 时段,
               COUNT(*) AS 视频数
        FROM video WHERE is_duration_outlier = 0 AND pub_hour >= 6
        GROUP BY 星期, 时段 ORDER BY 星期, 时段
    """)


@st.cache_data(ttl=TTL)
def fav_like_by_zone() -> pd.DataFrame:
    return query_df("""
        SELECT sub_zone AS 分区,
               ROUND(AVG(fav_cnt/NULLIF(view_cnt,0))*100, 2)  AS 收藏率,
               ROUND(AVG(like_cnt/NULLIF(view_cnt,0))*100, 2) AS 点赞率,
               COUNT(*) AS 样本量
        FROM video WHERE is_duration_outlier=0 AND view_cnt > 1000
        GROUP BY sub_zone HAVING COUNT(*) >= 10
        ORDER BY 收藏率 DESC
    """)


@st.cache_data(ttl=TTL)
def concentration() -> pd.DataFrame:
    return query_df("""
        WITH r AS (
            SELECT source_keyword, view_cnt,
                   ROW_NUMBER() OVER (PARTITION BY source_keyword ORDER BY view_cnt) rn,
                   COUNT(*) OVER (PARTITION BY source_keyword) cnt
            FROM video WHERE is_duration_outlier=0 AND source_keyword LIKE 'kw:%'
        )
        SELECT REPLACE(source_keyword,'kw:','') AS 选题,
               MAX(cnt) AS 样本量,
               ROUND(AVG(CASE WHEN rn = FLOOR(cnt*0.9) THEN view_cnt END)) AS P90播放,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                              THEN view_cnt END)) AS 播放中位数
        FROM r GROUP BY source_keyword
    """).assign(集中度=lambda d: (d["P90播放"] / d["播放中位数"]).round(1)).sort_values(
        "集中度", ascending=False)


@st.cache_data(ttl=TTL)
def danmaku_by_zone() -> pd.DataFrame:
    return query_df("""
        SELECT v.sub_zone AS 分区, COUNT(DISTINCT d.bvid) AS 视频数, COUNT(*) AS 弹幕数,
               ROUND(COUNT(*)/COUNT(DISTINCT d.bvid), 0) AS 每视频弹幕
        FROM danmaku d JOIN video v ON d.bvid = v.bvid
        GROUP BY v.sub_zone ORDER BY 弹幕数 DESC
    """)


@st.cache_data(ttl=TTL)
def cluster_topics() -> pd.DataFrame:
    p = ROOT / "data" / "processed" / "clusters.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    if "topic_name" not in df.columns:
        return pd.DataFrame()
    g = (df.groupby(["cluster", "topic_name"]).size()
         .reset_index(name="条数").sort_values("条数", ascending=False))
    g["占比%"] = (g["条数"] / len(df) * 100).round(1)
    return g

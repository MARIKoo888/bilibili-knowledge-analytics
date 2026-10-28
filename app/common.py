"""看板共享层：数据加载（双模式：本地 MySQL / 云端 CSV 快照）

═══════════════════════════════════════════════════════════
为什么是双模式
═══════════════════════════════════════════════════════════
- 本地开发：连 MySQL，数据实时
- 部署到 Streamlit Cloud：云端连不到你本机的 MySQL
  -> 自动降级读 data/snapshot/*.csv（由 src/export_snapshot.py 导出）

判断顺序：
  1. 环境变量 DSH_DATA_SOURCE=csv / mysql 可强制指定
  2. 否则尝试连 MySQL（2 秒超时），成功走 SQL，失败走 CSV
═══════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

SNAP = ROOT / "data" / "snapshot"
TTL = 600


# ---------------------------------------------------------------- 模式探测
@st.cache_resource
def _detect_mode() -> str:
    forced = os.getenv("DSH_DATA_SOURCE", "").strip().lower()
    if forced in {"csv", "mysql"}:
        return forced
    # 没装 pymysql / 没有 .env 时，直接走 CSV
    if not (ROOT / ".env").exists():
        return "csv"
    try:
        from sqlalchemy import create_engine, text

        from src.config import db_url

        eng = create_engine(db_url(), pool_pre_ping=True,
                            connect_args={"connect_timeout": 2})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "mysql"
    except Exception:
        return "csv"


def mode() -> str:
    return _detect_mode()


@st.cache_resource
def _engine():
    from sqlalchemy import create_engine

    from src.config import db_url

    return create_engine(db_url(), pool_pre_ping=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """MySQL 的 AVG/ROUND 返回 decimal.Decimal -> 转 float（否则画图 TypeError）。"""
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda x: float(x) if isinstance(x, Decimal) else x)
    return df


def _sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    from sqlalchemy import text

    with _engine().connect() as conn:
        res = conn.execute(text(sql), params or {})
        df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    return _clean(df)


# ---------------------------------------------------------------- 原始数据
@st.cache_data(ttl=TTL)
def videos() -> pd.DataFrame:
    """视频明细。MySQL 与 CSV 两种来源，列名保持一致。"""
    if mode() == "mysql":
        df = _sql("""
            SELECT bvid, aid, title, mid, sub_zone, duration_sec, pub_time,
                   pub_hour, pub_weekday, view_cnt, like_cnt, fav_cnt,
                   danmaku_cnt, reply_cnt, is_duration_outlier, source_keyword
            FROM video
        """)
    else:
        p = SNAP / "video.csv"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_csv(p)
    df["pub_time"] = pd.to_datetime(df.get("pub_time"), errors="coerce")
    df["pub_month"] = df["pub_time"].dt.strftime("%Y-%m")
    return df


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    """统一的有效样本：排除 >3 小时直播回放/课程合集。"""
    if df.empty:
        return df
    return df[df["is_duration_outlier"].fillna(0).astype(int) == 0]


@st.cache_data(ttl=TTL)
def meta() -> dict:
    p = SNAP / "meta.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ---------------------------------------------------------------- 各指标
@st.cache_data(ttl=TTL)
def kpi() -> dict:
    v = videos()
    if v.empty:
        return {"视频数": 0, "UP主数": 0, "分区数": 0, "均值播放": 0,
                "异常条数": 0, "弹幕数": 0}
    m = meta()
    return {
        "视频数": int(len(v)),
        "UP主数": int(v["mid"].nunique()),
        "分区数": int(v["sub_zone"].nunique()),
        "均值播放": float(v["view_cnt"].mean()),
        "异常条数": int(v["is_duration_outlier"].fillna(0).sum()),
        "弹幕数": int(m.get("danmaku_total", 0)) or int(v["danmaku_cnt"].fillna(0).sum()),
    }


DIM_LABEL = {"sub_zone": "二级分区", "source_keyword": "采集来源", "pub_weekday": "星期"}


@st.cache_data(ttl=TTL)
def median_by(dim: str) -> pd.DataFrame:
    """按维度算播放中位数（仅纳入样本 >= 10 的组）。"""
    v = _valid(videos())
    if v.empty:
        return pd.DataFrame(columns=["维度", "播放中位数", "样本量"])
    g = (v.groupby(dim)["view_cnt"]
         .agg(["median", "count"]).reset_index()
         .rename(columns={dim: "维度", "median": "播放中位数", "count": "样本量"}))
    g = g[g["样本量"] >= 10].sort_values("播放中位数", ascending=False)
    g["播放中位数"] = g["播放中位数"].round(0)
    return _clean(g.reset_index(drop=True))


@st.cache_data(ttl=TTL)
def month_trend() -> pd.DataFrame:
    v = _valid(videos())
    if v.empty:
        return pd.DataFrame(columns=["月份", "视频数", "播放中位数"])
    g = (v.dropna(subset=["pub_month"])
         .groupby("pub_month")["view_cnt"]
         .agg(["median", "count"]).reset_index()
         .rename(columns={"pub_month": "月份", "median": "播放中位数", "count": "视频数"}))
    g = g.sort_values("月份")
    g["播放中位数"] = g["播放中位数"].round(0)
    return _clean(g.reset_index(drop=True))


@st.cache_data(ttl=TTL)
def duration_bins(only_zc: bool) -> pd.DataFrame:
    v = _valid(videos())
    if only_zc:
        v = v[v["sub_zone"] == "职业职场"]
    if v.empty:
        return pd.DataFrame(columns=["时长桶", "播放中位数", "样本量"])
    bins = [0, 180, 480, 900, 1800, 10**9]
    labels = ["1_<3分", "2_3-8分", "3_8-15分", "4_15-30分", "5_>30分"]
    v = v.dropna(subset=["duration_sec"]).copy()
    v["时长桶"] = pd.cut(v["duration_sec"], bins=bins, labels=labels, right=False)
    g = (v.groupby("时长桶", observed=False)["view_cnt"]
         .agg(["median", "count"]).reset_index()
         .rename(columns={"median": "播放中位数", "count": "样本量"}))
    g = g[g["样本量"] > 0]
    g["播放中位数"] = g["播放中位数"].round(0)
    return _clean(g.reset_index(drop=True))


@st.cache_data(ttl=TTL)
def weekday_hour() -> pd.DataFrame:
    v = _valid(videos())
    v = v[v["pub_hour"].fillna(-1) >= 6]
    if v.empty:
        return pd.DataFrame(columns=["星期", "时段", "视频数"])
    v = v.copy()
    v["时段"] = pd.cut(v["pub_hour"], bins=[5, 11, 17, 24],
                     labels=["上午", "下午", "晚间"])
    g = (v.groupby(["pub_weekday", "时段"], observed=False).size()
         .reset_index(name="视频数")
         .rename(columns={"pub_weekday": "星期"}))
    return _clean(g)


@st.cache_data(ttl=TTL)
def fav_like_by_zone() -> pd.DataFrame:
    v = _valid(videos())
    v = v[v["view_cnt"] > 1000].copy()
    if v.empty:
        return pd.DataFrame(columns=["分区", "收藏率", "点赞率", "样本量"])
    v["收藏率"] = v["fav_cnt"] / v["view_cnt"] * 100
    v["点赞率"] = v["like_cnt"] / v["view_cnt"] * 100
    g = (v.groupby("sub_zone")[["收藏率", "点赞率"]].mean().reset_index()
         .rename(columns={"sub_zone": "分区"}))
    n = v.groupby("sub_zone").size().reset_index(name="样本量").rename(
        columns={"sub_zone": "分区"})
    g = g.merge(n, on="分区")
    g = g[g["样本量"] >= 10].sort_values("收藏率", ascending=False)
    for c in ("收藏率", "点赞率"):
        g[c] = g[c].round(2)
    return _clean(g.reset_index(drop=True))


@st.cache_data(ttl=TTL)
def concentration() -> pd.DataFrame:
    v = _valid(videos())
    v = v[v["source_keyword"].astype(str).str.startswith("kw:")]
    if v.empty:
        return pd.DataFrame(columns=["选题", "样本量", "P90播放", "播放中位数", "集中度"])
    v = v.copy()
    v["选题"] = v["source_keyword"].str.replace("kw:", "", regex=False)
    # ⚠️ 口径必须和 SQL 版一致：SQL 用 ROW_NUMBER()=FLOOR(cnt*0.9) 取顺序统计量，
    #    pandas 默认是线性插值（会在两个值之间加权），两者结果不同（45.0 vs 45.8）。
    #    这里用 interpolation="lower" 复现 SQL 的算法。
    g = v.groupby("选题")["view_cnt"].agg(
        [("样本量", "count"),
         ("P90播放", lambda s: s.quantile(0.9, interpolation="lower")),
         ("播放中位数", "median")]).reset_index()
    g["集中度"] = (g["P90播放"] / g["播放中位数"]).round(1)
    g["P90播放"] = g["P90播放"].round(0)
    g["播放中位数"] = g["播放中位数"].round(0)
    return _clean(g.sort_values("集中度", ascending=False).reset_index(drop=True))


@st.cache_data(ttl=TTL)
def danmaku_by_zone() -> pd.DataFrame:
    if mode() == "mysql":
        return _sql("""
            SELECT v.sub_zone AS 分区, COUNT(DISTINCT d.bvid) AS 视频数,
                   COUNT(*) AS 弹幕数,
                   ROUND(COUNT(*)/COUNT(DISTINCT d.bvid), 0) AS 每视频弹幕
            FROM danmaku d JOIN video v ON d.bvid = v.bvid
            GROUP BY v.sub_zone ORDER BY 弹幕数 DESC
        """).rename(columns={"sub_zone": "分区"})
    p = SNAP / "danmaku_zone.csv"
    if not p.exists():
        return pd.DataFrame(columns=["分区", "视频数", "弹幕数", "每视频弹幕"])
    d = pd.read_csv(p).rename(columns={
        "sub_zone": "分区", "video_cnt": "视频数",
        "danmaku_cnt": "弹幕数", "danmaku_per_video": "每视频弹幕"})
    return _clean(d)


@st.cache_data(ttl=TTL)
def cluster_topics() -> pd.DataFrame:
    for p in (SNAP / "cluster_topics.csv", ROOT / "data" / "processed" / "clusters.csv"):
        if p.exists():
            df = pd.read_csv(p)
            if "topic_name" in df.columns and "cluster" in df.columns:
                g = (df.groupby(["cluster", "topic_name"]).size()
                     .reset_index(name="条数").sort_values("条数", ascending=False))
                g["占比%"] = (g["条数"] / len(df) * 100).round(1)
                g = g.rename(columns={"cluster": "簇", "topic_name": "命名"})
                return g.reset_index(drop=True)
    return pd.DataFrame()

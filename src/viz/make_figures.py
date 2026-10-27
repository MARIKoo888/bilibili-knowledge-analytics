"""批量生成分析图表 —— 把 SQL 结果画成能放进报告的图

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.viz.make_figures

产出（figures/）：
    fig_duration_compare.png   时长 × 播放中位数（全量 vs 职场）—— 发现1/3
    fig_quadrant.png           四象限散点（播放 × 互动率）—— 发现6
    fig_fav_vs_like.png        分区收藏率 vs 点赞率 —— 发现4
    fig_concentration.png      5 个关键词的注意力集中度 —— Q1

作图原则（面试可讲）：
  1. 标题写结论，不写变量名（"8–15分钟最优"而不是"时长与播放关系"）
  2. 每个数字都能追溯到某个 SQL —— 图是结论的呈现，不是探索
  3. 中文必须显式设字体，否则全是方块
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import db_url  # noqa: E402

FIG = ROOT / "figures"
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.dpi"] = 130

C_MAIN = "#2E86DE"
C_ALT = "#EE5A24"
C_GREY = "#95A5A6"


def q(engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.DataFrame(conn.execute(text(sql)).fetchall())
    # MySQL 的 AVG/ROUND 返回 decimal.Decimal，numpy 无法直接做乘加（会 TypeError）。
    # 统一把 object 列里的 Decimal 转成 float。
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda x: float(x) if isinstance(x, Decimal) else x)
    return df


# ---------------------------------------------------------------- 图1
def fig_duration(engine) -> None:
    """时长 × 播放中位数：全量 vs 仅职业职场（控制变量对照）"""
    base = """
    WITH b AS (
      SELECT view_cnt,
        CASE WHEN duration_sec < 180 THEN '1_<3分' WHEN duration_sec < 480 THEN '2_3-8分'
             WHEN duration_sec < 900 THEN '3_8-15分' WHEN duration_sec < 1800 THEN '4_15-30分'
             ELSE '5_>30分' END AS bucket
      FROM video WHERE is_duration_outlier = 0 {extra}
    ), r AS (
      SELECT bucket, view_cnt,
             ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY view_cnt) rn,
             COUNT(*) OVER (PARTITION BY bucket) cnt FROM b
    )
    SELECT bucket, ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                                  THEN view_cnt END)) AS median_view, MAX(cnt) AS n
    FROM r GROUP BY bucket ORDER BY bucket
    """
    allv = q(engine, base.format(extra=""))
    zc = q(engine, base.format(extra="AND sub_zone='职业职场'"))

    x = np.arange(len(allv))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10, 5.5))
    b1 = ax.bar(x - w / 2, allv["median_view"], w, label="全部分区（未控制）", color=C_GREY)
    b2 = ax.bar(x + w / 2, zc["median_view"], w, label="仅职业职场（控制分区）", color=C_MAIN)
    ax.set_xticks(x)
    ax.set_xticklabels(allv["bucket"], fontsize=10)
    ax.set_ylabel("播放中位数")
    ax.set_title("控制分区后，短视频和长视频的高点都消失了——真正的规律只有「8–15 分钟」", fontsize=12)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    for bars in (b1, b2):
        for r in bars:
            h = r.get_height()
            if h and h == h:
                ax.annotate(f"{h/10000:.1f}万", (r.get_x()+r.get_width()/2, h),
                            ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig_duration_compare.png", bbox_inches="tight")
    plt.close()
    print("[fig] fig_duration_compare.png")


# ---------------------------------------------------------------- 图2
def fig_quadrant(engine) -> None:
    """四象限：播放 × 互动率，P75 分割"""
    df = q(engine, """
        SELECT view_cnt, (like_cnt + fav_cnt) / NULLIF(view_cnt,0) AS eng
        FROM video WHERE is_duration_outlier = 0 AND view_cnt > 1000
    """).dropna()
    v75 = np.percentile(df["view_cnt"], 75)
    e75 = np.percentile(df["eng"], 75)

    fig, ax = plt.subplots(figsize=(9, 6.5))
    hi_v = df["view_cnt"] >= v75
    hi_e = df["eng"] >= e75
    ax.scatter(df.loc[~hi_v, "view_cnt"], df.loc[~hi_v, "eng"],
               s=18, color=C_GREY, alpha=.55, label=f"低播放·低互动 ({(~hi_v & ~hi_e).sum()})")
    ax.scatter(df.loc[~hi_v & hi_e, "view_cnt"], df.loc[~hi_v & hi_e, "eng"],
               s=18, color=C_ALT, alpha=.6, label=f"低播放·高互动 ({(~hi_v & hi_e).sum()})")
    ax.scatter(df.loc[hi_v & ~hi_e, "view_cnt"], df.loc[hi_v & ~hi_e, "eng"],
               s=18, color="#8E44AD", alpha=.6, label=f"高播放·低互动 ({(hi_v & ~hi_e).sum()})")
    ax.scatter(df.loc[hi_v & hi_e, "view_cnt"], df.loc[hi_v & hi_e, "eng"],
               s=45, color=C_MAIN, edgecolor="k", linewidth=.4,
               label=f"高播放·高互动 ({(hi_v & hi_e).sum()})")

    ax.axvline(v75, color="k", ls="--", lw=1, alpha=.6)
    ax.axhline(e75, color="k", ls="--", lw=1, alpha=.6)
    ax.annotate(f"P75 播放 = {v75/10000:.0f}万", (v75, ax.get_ylim()[1]),
                xytext=(4, -12), textcoords="offset points", fontsize=9)
    ax.annotate(f"P75 互动率 = {e75*100:.1f}%", (ax.get_xlim()[1], e75),
                xytext=(-105, 5), textcoords="offset points", fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("播放量（对数轴）")
    ax.set_ylabel("互动率 = (点赞+收藏)/播放")
    ax.set_title("爆款 ≠ 高互动：高播放·高互动仅 18 条（5.2%）", fontsize=12)
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(alpha=.22)
    fig.tight_layout()
    fig.savefig(FIG / "fig_quadrant.png", bbox_inches="tight")
    plt.close()
    print("[fig] fig_quadrant.png")


# ---------------------------------------------------------------- 图3
def fig_fav_like(engine) -> None:
    """分区收藏率 vs 点赞率，突出职业职场"""
    df = q(engine, """
        SELECT sub_zone,
               ROUND(AVG(fav_cnt/NULLIF(view_cnt,0))*100,2) AS fav,
               ROUND(AVG(like_cnt/NULLIF(view_cnt,0))*100,2) AS lik,
               COUNT(*) AS n
        FROM video WHERE is_duration_outlier=0 AND view_cnt>1000
        GROUP BY sub_zone HAVING COUNT(*)>=10 ORDER BY fav DESC
    """)
    df = df.sort_values("fav")
    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    ax.barh(y - .2, df["fav"], .4, label="收藏率", color=C_MAIN)
    ax.barh(y + .2, df["lik"], .4, label="点赞率", color=C_ALT)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{z} (n={n})" for z, n in zip(df["sub_zone"], df["n"])], fontsize=9)
    ax.set_xlabel("%（占播放量）")
    ax.set_title("职业职场是知识区唯一「收藏 > 点赞」的细分", fontsize=12)
    ax.legend()
    ax.grid(axis="x", alpha=.25)
    for i, (f, l, z) in enumerate(zip(df["fav"], df["lik"], df["sub_zone"])):
        if f > l:
            ax.annotate("收藏/点赞 = %.2f" % (f / l), (max(f, l) + .15, i),
                        va="center", fontsize=9, color=C_MAIN, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "fig_fav_vs_like.png", bbox_inches="tight")
    plt.close()
    print("[fig] fig_fav_vs_like.png")


# ---------------------------------------------------------------- 图4
def fig_concentration(engine) -> None:
    """5 个关键词的注意力集中度（P90 / 中位数）"""
    df = q(engine, """
        WITH r AS (
          SELECT source_keyword, view_cnt,
                 ROW_NUMBER() OVER (PARTITION BY source_keyword ORDER BY view_cnt) rn,
                 COUNT(*) OVER (PARTITION BY source_keyword) cnt
          FROM video WHERE is_duration_outlier=0 AND source_keyword LIKE 'kw:%'
        )
        SELECT source_keyword, MAX(cnt) AS n,
               ROUND(AVG(CASE WHEN rn=FLOOR(cnt*0.9) THEN view_cnt END)) AS p90,
               ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2)) THEN view_cnt END)) AS med
        FROM r GROUP BY source_keyword
    """)
    df["conc"] = df["p90"] / df["med"]
    df = df.sort_values("conc")
    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = [C_ALT if c > 20 else C_MAIN for c in df["conc"]]
    bars = ax.barh(df["source_keyword"], df["conc"], color=colors)
    ax.set_xlabel("注意力集中度 = P90播放 ÷ 中位播放（越高越「爆款通吃」）")
    ax.set_title("职场沟通的注意力集中度是简历修改的 6 倍——普通账号不该碰", fontsize=12)
    ax.grid(axis="x", alpha=.25)
    for r, c, p, m in zip(bars, df["conc"], df["p90"], df["med"]):
        ax.annotate(f"{c:.1f}  (P90 {p/10000:.0f}万 / 中位 {m/10000:.1f}万)",
                    (r.get_width() + .5, r.get_y() + r.get_height()/2),
                    va="center", fontsize=9)
    ax.set_xlim(0, df["conc"].max() * 1.55)
    fig.tight_layout()
    fig.savefig(FIG / "fig_concentration.png", bbox_inches="tight")
    plt.close()
    print("[fig] fig_concentration.png")


def main() -> int:
    engine = create_engine(db_url(), pool_pre_ping=True)
    FIG.mkdir(parents=True, exist_ok=True)
    fig_duration(engine)
    fig_quadrant(engine)
    fig_fav_like(engine)
    fig_concentration(engine)
    print(f"\n[done] 4 张图已写入 {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

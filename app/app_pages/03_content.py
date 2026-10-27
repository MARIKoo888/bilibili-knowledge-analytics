"""页3 · 内容拆解：时长与播放的关系（含控制变量对照）"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common  # noqa: E402

st.title("内容拆解")
with st.container(border=True):
    st.markdown("**这一页回答什么问题**")
    st.markdown("视频该做多长？控制分区之后，结论还成立吗？")

# ---- 时长对照 ----
with st.container(border=True):
    st.subheader("Q2 · 时长 × 播放中位数：全部分区 vs 仅职业职场")

    mode = st.segmented_control(
        "看哪一版",
        options=["并排对比", "只看全部分区", "只看职业职场"],
        default="并排对比",
        key="dur_mode",
    )

    df_all = common.duration_bins(only_zc=False)
    df_zc = common.duration_bins(only_zc=True)

    if mode == "只看全部分区":
        st.bar_chart(df_all, x="时长桶", y="播放中位数", height=360,
                     alt="全部分区的时长分桶播放中位数")
        st.dataframe(df_all, hide_index=True, width="stretch")
    elif mode == "只看职业职场":
        st.bar_chart(df_zc, x="时长桶", y="播放中位数", height=360,
                     alt="职业职场分区的时长分桶播放中位数")
        st.dataframe(df_zc, hide_index=True, width="stretch")
    else:
        merged = (df_all[["时长桶", "播放中位数"]].rename(columns={"播放中位数": "全部分区"})
                  .merge(df_zc[["时长桶", "播放中位数"]].rename(
                      columns={"播放中位数": "仅职业职场"}), on="时长桶", how="outer")
                  .sort_values("时长桶"))
        st.bar_chart(merged, x="时长桶", y=["全部分区", "仅职业职场"], height=360,
                     alt="时长分桶的播放中位数：全部分区与仅职业职场的对比条形图")
        st.dataframe(merged, hide_index=True, width="stretch")

    st.success(
        "**结论**：不控制分区时，短视频（<3 分）和长视频（15–30 分）看起来都很能打；"
        "**控制到只算职业职场后，这两个高点分别塌陷 76% 和 67%**（61,825→14,980、"
        "77,938→25,328）——它们来自其他分区的娱乐短视频，不是时长效应。\n\n"
        "**唯一稳健的结论**：8–15 分钟播放中位数 46,597，是 3–8 分钟（20,554）的 **2.3 倍**。\n\n"
        "**行动**：职场垂类时长控制在 8–15 分钟；3 分钟以内或 15 分钟以上无优势。",
        title="发现 1 + 发现 3（辛普森悖论的实证）",
    )

    st.caption(
        "⚠️ 只控制了**分区**，未控制 **UP 主粉丝量**（粉丝数据未采集）。"
        "若大 UP 主恰好偏爱某一时长区间，本结论仍可能被体量混淆。"
    )

st.divider()

# ---- 全量 vs 职场 的对照图（静态） ----
with st.container(border=True):
    st.subheader("图示：控制变量前后")
    img = Path(__file__).resolve().parents[1] / "figures" / "fig_duration_compare.png"
    if img.exists():
        st.image(str(img), caption="左：全部分区；右：仅职业职场", width="stretch")
    else:
        st.info("图未生成，先跑 `python -m src.viz.make_figures`")

st.divider()

# ---- 四象限 ----
with st.container(border=True):
    st.subheader("Q2 · 四象限：高播放 × 高互动（P75 阈值）")
    img2 = Path(__file__).resolve().parents[1] / "figures" / "fig_quadrant.png"
    if img2.exists():
        st.image(str(img2), width="stretch",
                 caption="横轴播放量（对数），纵轴互动率；虚线为 P75 分割线")
    st.dataframe(
        pd.DataFrame({
            "象限": ["低播放·低互动", "高播放·低互动", "低播放·高互动", "高播放·高互动"],
            "条数": [188, 69, 68, 18],
            "占比": ["54.8%", "20.1%", "19.8%", "5.2%"],
        }),
        hide_index=True, width="stretch",
    )
    st.info(
        "若两指标独立，高·高应占 6.25%（约 21 条），实际只有 18 条（5.2%）——"
        "**爆款不等于高互动**。原因是互动率分母（播放量）在推荐流中涨得比分子快。",
        title="为什么高播放·高互动这么少",
    )

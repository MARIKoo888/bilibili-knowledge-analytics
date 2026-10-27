"""页2 · 分区与时段：竞争度（注意力集中度）、发布时段分布"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common  # noqa: E402

st.title("分区与时段")
with st.container(border=True):
    st.markdown("**这一页回答什么问题**")
    st.markdown(
        "哪个选题是「少数爆款通吃」、哪个「稳定有量」？"
        "发布时段和星期有没有规律？"
    )

# ---- Q1 竞争度 ----
with st.container(border=True):
    st.subheader("Q1 · 选题竞争度：注意力集中度 = P90 播放 ÷ 中位播放")
    df = common.concentration()
    st.bar_chart(df, x="选题", y="集中度", height=340,
                 alt="5 个选题的注意力集中度条形图")
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={
            "集中度": st.column_config.NumberColumn(format="%.1f"),
            "P90播放": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.success(
        "**怎么读**：集中度高 = 普通视频只有 1.9 万播放，头部能到 86 万，"
        "少数爆款吃掉大部分注意力（赢家通吃，新号难出头）；"
        "集中度低 = 头部和普通差距小，普通内容也能稳定拿量。\n\n"
        "**行动**：普通账号优先做「简历修改 / 应届生求职」（集中度 7.2）；"
        "有爆款能力才做「职场沟通」（集中度 45.0，天花板 86 万）。",
        title="业务含义",
    )
    st.caption(
        "⚠️ 原设计用「供给量 ÷ 需求量（视频数/播放中位数）」算供需比，"
        "但采集受每词 ≤60 条截断，且 B站 `numResults` 对所有关键词统一封顶 1000，"
        "**供给量不可测**，故改用样本内集中度代理（采集方式一致，可横向比较）。"
    )

st.divider()

# ---- Q2 时段 ----
with st.container(border=True):
    st.subheader("Q2 · 发布时段 × 星期（供给分布）")
    d = common.weekday_hour()
    pivot = d.pivot(index="星期", columns="时段", values="视频数").fillna(0).astype(int)
    pivot = pivot.reindex(columns=[c for c in ["上午", "下午", "晚间"] if c in pivot.columns])
    pivot.index = [f"周{i}" for i in pivot.index]

    st.markdown("**每个格子 = 那天那个时段发了多少条视频**")
    st.dataframe(
        pivot, width="stretch",
        column_config={c: st.column_config.NumberColumn(c, format="%d") for c in pivot.columns},
    )
    st.bar_chart(pivot, height=320, alt="星期×时段的视频数堆叠柱状图")
    st.warning(
        "**本页不提供「最佳发布时段」结论。**  \n"
        "原因：21 个格子样本量仅 4–36 条，同一时段内播放中位数极差达 18 倍"
        "（周二下午 n=36 仅 5,647；周一下午 n=32 达 372,663），**噪声大于信号**；"
        "且样本来自排行榜与搜索前几页，本身偏向爆款，不能代表知识区的真实发布行为。  \n"
        "→ 要回答「何时发布更优」，需改用「同 UP 主多视频对比」或随机抽样。",
        title="为什么这里没有时段建议",
    )

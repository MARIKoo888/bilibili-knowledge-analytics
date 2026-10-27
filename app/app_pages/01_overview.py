"""页1 · 总览：规模、分布、趋势"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

import common  # noqa: E402

st.title("总览")
st.caption(
    "场景：知识区·**职场垂类**的内容运营，每周要决定「下周发什么、多长、什么时候发」。"
)

# 先渲染快的 UI（标题、说明），慢查询放在后面 —— 遵循"先出界面再算数"
with st.container(border=True):
    st.markdown("**这一页回答什么问题**")
    st.markdown("知识区整体规模如何？各分区的播放水平差多少？内容供给随时间怎么变？")

# ---- KPI 行：horizontal=True 窄屏会自动换行（比 st.columns 更适合指标行）----
k = common.kpi()
with st.container(horizontal=True):
    st.metric("视频数", f"{k['视频数']:,}", border=True)
    st.metric("UP 主数", f"{k['UP主数']:,}", border=True)
    st.metric("二级分区", f"{k['分区数']}", border=True)
    st.metric("弹幕数", f"{k['弹幕数']:,}", border=True)
    st.metric("异常时长", f"{k['异常条数']}", border=True,
              delta="已打标未删", delta_color="off")

st.warning(
    "均值播放 会被爆款带飞（均值 / 中位数 ≈ 13.6 倍），"
    "所以下面统一用 **中位数**——它才代表「一条普通视频能拿多少」。",
    title="口径提醒",
)

# ---- 两栏：分区中位数 + 月度趋势 ----
col1, col2 = st.columns([1.1, 1])

with col1:
    with st.container(border=True):
        st.subheader("各分区播放中位数")
        dfz = common.median_by("sub_zone")
        dfz = dfz[~dfz["维度"].isin(["其他"])]
        st.bar_chart(dfz, x="维度", y="播放中位数", height=380,
                     alt="各二级分区的播放中位数条形图")
        with st.expander("看数据表"):
            st.dataframe(dfz, hide_index=True, width="stretch")
        st.caption(
            "⚠️ 分区之间**不可直接比较**：职业职场是定向采集（related 滚雪球 + 5 关键词），"
            "科学科普来自排行榜顺手带的，抽样强度差十几倍。"
        )

with col2:
    with st.container(border=True):
        st.subheader("月度供需变化")
        dft = common.month_trend()
        st.line_chart(dft, x="月份", y=["视频数", "播放中位数"], height=380,
                      alt="按月的新发视频数与播放中位数折线图")
        with st.expander("看数据表"):
            st.dataframe(dft, hide_index=True, width="stretch")
        st.caption(
            "⚠️ **不能**当市场趋势读：采集时点是 2026-10，时间分布主要由"
            "「搜索接口返回哪些内容」决定。146 个周仅 403 条视频，平均每周 2.8 条。"
        )

st.info(
    "完整结论见 `reports/analysis_report_v2.md`（9 条发现 / 9 条偏差 / 5 条建议）。"
)

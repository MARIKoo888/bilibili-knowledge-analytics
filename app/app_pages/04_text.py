"""页4 · 弹幕洞察：互动结构、词云、时间轴、主题分布"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

import common  # noqa: E402

FIG = ROOT / "figures"

st.title("弹幕洞察")
with st.container(border=True):
    st.markdown("**这一页回答什么问题**")
    st.markdown(
        "观众在这类内容里「要什么」？他们在哪一刻最激动？"
        "为什么**不能**用弹幕情感当质量指标？"
    )

# ---- 互动结构：收藏 > 点赞 ----
with st.container(border=True):
    st.subheader("发现 4 · 职业职场是唯一「收藏 > 点赞」的细分")
    df = common.fav_like_by_zone()
    st.bar_chart(df, x="分区", y=["收藏率", "点赞率"], height=340,
                 alt="各分区的收藏率与点赞率对比条形图")
    with st.expander("看数据表"):
        st.dataframe(df, hide_index=True, width="stretch")
    st.success(
        "职业职场收藏率 3.39%、点赞率 1.93%，比值 **1.75**；其他 6 个分区比值 0.41–0.93。\n\n"
        "**含义**：职场内容提供「工具价值」——用户的第一反应是「收藏，面试前再看」，不是点赞。\n\n"
        "**行动**：该垂类考核指标用**收藏率**，不用点赞率。",
        title="怎么读",
    )

st.divider()

# ---- 弹幕密度：沉默的消费者 ----
with st.container(border=True):
    st.subheader("发现 7 · 弹幕密度差 12 倍：职场用户不发弹幕")
    d = common.danmaku_by_zone()
    st.bar_chart(d, x="分区", y="每视频弹幕", height=340,
                 alt="各分区每视频平均弹幕数的条形图")
    with st.expander("看数据表"):
        st.dataframe(d, hide_index=True, width="stretch")
    st.success(
        "职业职场 **117 条/视频**，其他分区 **1,401 条/视频**——相差 12 倍。\n\n"
        "与「收藏>点赞」同源：用户把内容当工具，看完即走，不产生即时表达欲。\n\n"
        "**行动**：不能用弹幕热度衡量职场内容的质量（会系统性低估优质工具型内容）。",
        title="怎么读",
    )

st.divider()

# ---- 词云 ----
with st.container(border=True):
    st.subheader("发现 8 · 观众在聊什么")
    c1, c2 = st.columns(2)
    with c1:
        if (FIG / "wordcloud_zc.png").exists():
            st.image(str(FIG / "wordcloud_zc.png"), width="stretch",
                     caption="职业职场弹幕词云")
    with c2:
        if (FIG / "wordcloud_other.png").exists():
            st.image(str(FIG / "wordcloud_other.png"), width="stretch",
                     caption="对照组：其他知识区弹幕词云")
    st.markdown(
        "职场 Top 词：**面试 485 / 公司 279 / 工作 211 / 面试官 164 / 简历 128**  \n"
        "职场特有词（对照组为 0）：**面试官 / 简历 / 薪资 / 谈薪**  \n"
        "意外发现：**「缺点」出现 147 次** → 用户在反复讨论「面试问缺点怎么答」，"
        "这是一个 SQL 查不出来的选题线索。"
    )

st.divider()

# ---- 主题聚类 ----
with st.container(border=True):
    st.subheader("主题聚类（TF-IDF + SVD + KMeans, k=9）")
    ct = common.cluster_topics()
    if ct.empty:
        st.info("先跑 `python -m src.nlp.cluster` 生成聚类结果")
    else:
        st.dataframe(ct, hide_index=True, width="stretch")
        st.warning(
            "**轮廓系数仅 0.0565**，远低于 0.25 的「有结构」门槛。"
            "首次直接对 TF-IDF 聚类时还出现退化解（单簇占 94.1%）——"
            "说明弹幕太短，不足以支撑可靠的主题分类。\n\n"
            "本页**不宣称完成主题分类**，只把它当「话题倾向的粗分组」供人工解读。\n\n"
            "另：簇 6「装修施工」占 8.3%，是职业职场分区混入技能教学视频造成的噪声。",
            title="必须说明的局限",
        )

st.divider()

# ---- 时间轴 ----
with st.container(border=True):
    st.subheader("发现 10 · 观众在第几分钟最激动")
    if (FIG / "danmaku_timeline_zc.png").exists():
        st.image(str(FIG / "danmaku_timeline_zc.png"), width="stretch",
                 caption="蓝线=弹幕密度，橙虚线=笑声密度；横轴为视频相对进度")
    st.markdown(
        "**原始计数**（15,025 条弹幕）：前 5% 时长集中了 **14.0%** 的弹幕"
        "（均匀应为 5%，2.8 倍）；最后 5% 为 4.6%（接近均匀，**无衰减**）。  \n"
        "**但开头弹幕不是内容反应**：抽查原文是「来了来了／终于／第一个／首页通知书／"
        "鹅姐吃我三连／许愿拿offer／回来还愿」，属于**到达打卡与对创作者的关系互动**。  \n"
        "**结尾不衰减**说明内容留得住人 → 可把「结尾 5% 弹幕密度 / 5%」当作**完播率代理指标**。"
    )
    st.caption(
        "⚠️ 仅 4 条视频 / 4,850 条弹幕，样本极小，仅作方法演示。"
        "另：初版用「除以自身最大值」归一化后得出「开头结尾几乎相同」，"
        "改用原始计数才发现开头是结尾的 3 倍——归一化会抹平真实差异。"
    )

st.divider()

# ---- 情感基线 ----
with st.container(border=True):
    st.subheader("发现 9 · 情感分析基线失败：弹幕不是情感载体")
    c1, c2, c3 = st.columns(3)
    c1.metric("snownlp 准确率", "27.0%", border=True)
    c2.metric("多数类基线（全判中性）", "88%", border=True)
    c3.metric("差距", "-61 pt", border=True, delta="比全猜还差", delta_color="inverse")

    st.markdown(
        "100 条人工盲标样本的标注分布：**正 6% / 中 88% / 负 6%**。  \n"
        "误判类型：疑问句被当情绪 11 例、玩梗被判正面 4 例、反讽未识别"
        "（「又是制造焦虑的标题」被判正面 0.85）。"
    )
    st.error(
        "**根因不是模型不够好，是数据不适合。** 弹幕 88% 中性——用户发弹幕是伴随式反应，"
        "不表达评价。换 BERT 也救不回来。  \n"
        "→ 所以本页**不使用情感指标**评估内容，改用收藏率等行为指标。",
        title="为什么不继续优化模型",
    )

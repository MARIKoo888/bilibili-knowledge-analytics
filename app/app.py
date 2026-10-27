"""看板入口 —— 多页导航

运行：
    .\\.venv\\Scripts\\python.exe -m streamlit run app/app.py

结构（Streamlit 官方推荐的多页写法）：
    app/app.py              <- 入口：定义导航（本文件）
    app/common.py           <- 共享层：连接、缓存查询
    app/app_pages/*.py      <- 各页面（保持"直接脚本"，不要包成函数）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="B站知识区内容运营决策支持",
    page_icon=":material/insights:",
    layout="wide",
)

pages = [
    st.Page("app_pages/01_overview.py", title="总览", icon=":material/dashboard:", default=True),
    st.Page("app_pages/02_zone_time.py", title="分区与时段", icon=":material/calendar_month:"),
    st.Page("app_pages/03_content.py", title="内容拆解", icon=":material/schedule:"),
    st.Page("app_pages/04_text.py", title="弹幕洞察", icon=":material/forum:"),
]

nav = st.navigation(pages)

with st.sidebar:
    st.caption(
        "数据截面：2026-10-19 ~ 10-27\n\n"
        "视频 458 条 ｜ 弹幕 79,455 条\n\n"
        "样本偏向爆款，供给量不可测——详见每页的偏差提示与 "
        "`reports/analysis_report_v2.md`"
    )

nav.run()

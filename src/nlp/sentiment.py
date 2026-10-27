"""情感分析基线（snownlp）+ 盲标样本导出 —— 第11周任务

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.nlp.sentiment

产出：
    data/processed/danmaku_sentiment.csv   每条弹幕的 snownlp 分数与三分类
    data/processed/label_sample.csv        **盲标样本 100 条**（不含模型预测，避免锚定偏差）

为什么必须先做基线：
  面试必问"你的情感分析准确率多少"。没有基线，你不知道自己的模型是进步还是退步。
  基线通常很弱（snownlp 是购物评论语料训练的），这恰恰是"你为什么需要自己标注+训练"的论据。

⚠️ 标注规则（关键，不能事后改）：
  正 = 明确赞许/感谢/共鸣（"学到了""讲得真好""说到心坎里"）
  负 = 明确否定/抱怨/批评（"太坑了""纯废话""制造焦虑"）
  中 = 疑问、玩梗、无情绪、单纯陈述（"怎么答啊""xsl""？""我的缺点是太完美"）
  特别注意：**反讽按字面识别会出错**（"又是制造焦虑的标题"字面像中性，实际是负面批评）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from snownlp import SnowNLP  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import db_url  # noqa: E402

OUT_ALL = ROOT / "data" / "processed" / "danmaku_sentiment.csv"
OUT_SAMPLE = ROOT / "data" / "processed" / "label_sample.csv"
CLUSTERS = ROOT / "data" / "processed" / "clusters.csv"

# 三分类阈值（snownlp 输出 0~1 的"正面概率"）
POS_TH = 0.60
NEG_TH = 0.40

SAMPLE_N = 100
RANDOM_STATE = 42


def classify(score: float) -> str:
    if score >= POS_TH:
        return "正"
    if score <= NEG_TH:
        return "负"
    return "中"


def main() -> int:
    # ---------- 1. 读弹幕（只取职场：Q3 的分析范围）----------
    engine = create_engine(db_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT d.content, d.dup_count, v.sub_zone FROM danmaku d "
            "JOIN video v ON d.bvid = v.bvid WHERE v.sub_zone = '职业职场'"
        )).fetchall()
    df = pd.DataFrame(rows, columns=["content", "dup_count", "sub_zone"])
    print(f"[load] 职场弹幕 {len(df)} 条")

    # ---------- 2. 挂上主题（来自聚类结果）----------
    if CLUSTERS.exists():
        cl = pd.read_csv(CLUSTERS)
        if "topic_name" not in cl.columns:          # 旧版 clusters.csv 没带名字，用字典补
            try:
                from src.nlp.cluster import TOPIC_NAMES
                cl["topic_name"] = cl["cluster"].map(TOPIC_NAMES).fillna("未命名")
            except Exception:
                cl["topic_name"] = "簇" + cl["cluster"].astype(str)
        cl = cl[["content", "cluster", "topic_name"]].drop_duplicates("content")
        df = df.merge(cl, on="content", how="left")
        df["topic_name"] = df["topic_name"].fillna("未分类（短文本）")
        df["cluster"] = df["cluster"].fillna(-1).astype(int)
        print(f"[join] 已挂上主题；未分类 {int((df['topic_name']=='未分类（短文本）').sum())} 条")
    else:
        df["cluster"] = -1
        df["topic_name"] = "未分类"
        print("[warn] 没找到 clusters.csv，跳过主题关联（先跑 src.nlp.cluster）")

    # ---------- 3. snownlp 打分 ----------
    print("[snownlp] 打分中…（约 25 秒）")
    scores = [SnowNLP(str(t)).sentiments for t in df["content"]]
    df["snow_score"] = scores
    df["snow_label"] = [classify(s) for s in scores]

    print("\n===== snownlp 三分类分布 =====")
    print(df["snow_label"].value_counts(normalize=True).mul(100).round(1).to_string())

    # ---------- 4. 情感 × 主题 交叉表（占比%）----------
    print("\n===== 情感 × 主题 交叉表（行内占比 %）=====")
    ct = pd.crosstab(df["topic_name"], df["snow_label"], normalize="index").mul(100).round(1)
    cnt = df["topic_name"].value_counts()
    ct = ct.loc[cnt.index]                     # 按样本量排序
    ct.insert(0, "样本量", cnt)
    print(ct.to_string())

    # ---------- 5. 落盘全量 ----------
    OUT_ALL.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    print(f"\n[done] 全量结果写入 {OUT_ALL}")

    # ---------- 6. 导出盲标样本 ----------
    # 关键：只导出 content + 空 label 列，**不含模型预测**，避免锚定偏差
    rng = np.random.default_rng(RANDOM_STATE)
    idx = rng.choice(len(df), size=min(SAMPLE_N, len(df)), replace=False)
    sample = df.iloc[idx][["content"]].copy()
    sample.insert(0, "idx", range(1, len(sample) + 1))
    sample["label"] = ""                        # ← 你来填：正 / 中 / 负
    sample.to_csv(OUT_SAMPLE, index=False, encoding="utf-8-sig")
    print(f"[done] 盲标样本 {len(sample)} 条写入 {OUT_SAMPLE}")
    print("       打开它，在 label 列填 正 / 中 / 负（每条 2 秒），填完跑 src.nlp.eval_sentiment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""TF-IDF + KMeans 主题聚类 —— 第10周周五任务

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.nlp.cluster

产出：
    data/processed/clusters.csv     每条弹幕的：文本, 簇号, 距质心距离
    （控制台打印）每个簇：样本量、Top15 关键词、5 条代表性弹幕

方法说明（面试必讲）：
  1. 为什么用 TF-IDF 而不是词频？
     → 词频会让"哈哈""老师"这类通用高频词主导所有簇；
       TF-IDF 会压低"所有簇都出现"的词，突出"本簇特有"的词。
  2. 为什么 KMeans 要指定 k？
     → KMeans 不自己决定簇数。用一个"轮廓系数（silhouette）"扫一下
       k=4..10 选最优，比拍脑袋定 k 有说服力。
  3. 簇没有名字，必须人工命名。
     → 这一步不能自动化。命名是否准确，是分析师的活。
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

import jieba  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics import silhouette_score  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import db_url  # noqa: E402
from src.nlp.segment import CUSTOM_WORDS, STOPWORDS  # noqa: E402

OUT_CSV = ROOT / "data" / "processed" / "clusters.csv"

# 词云里过滤掉但聚类里也要处理的"无信息词"
EXTRA_STOP = {"哈哈哈", "哈哈哈哈", "哈哈", "这么", "这么", "还是", "还有",
              "不会", "不能", "感觉", "喜欢", "直接", "这个问题"}
STOP_ALL = STOPWORDS | EXTRA_STOP

for w in CUSTOM_WORDS:
    jieba.add_word(w, freq=10000)

RANDOM_STATE = 42

# 人工命名（见 docs/cluster_topics.md）。KMeans 每次跑的簇号可能变，
# 所以这里按「关键词特征」把名字对上；跑完请核对控制台输出再更新此表。
TOPIC_NAMES = {
    0: "薪资与待遇",
    1: "表达逻辑与内容质量",
    2: "公司文化与绩效",
    3: "综合杂谈（长尾）",
    4: "考证与行业吐槽",
    5: "「缺点」玩梗",
    6: "装修施工（噪声）",
    7: "面试实战焦虑",
    8: "内容/UP主评价",
}


def tokenize(t: str) -> list[str]:
    """分词并过滤：长度>=2、非停用词、非纯数字。"""
    out = []
    for w in jieba.cut(t):
        w = w.strip()
        if len(w) < 2 or w in STOP_ALL or w.isdigit():
            continue
        out.append(w)
    return out


def load_zc_danmaku() -> pd.DataFrame:
    engine = create_engine(db_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT d.content FROM danmaku d JOIN video v ON d.bvid = v.bvid "
            "WHERE v.sub_zone = '职业职场' AND CHAR_LENGTH(d.content) >= 4"
        )).fetchall()
    return pd.DataFrame({"content": [r[0] for r in rows if r[0]]})


def main() -> int:
    df = load_zc_danmaku()
    print(f"[load] 职场弹幕（长度>=4）{len(df)} 条")
    if len(df) < 50:
        print("[error] 样本太少")
        return 1

    # 分词后拼回字符串（TfidfVectorizer 需要一个可迭代的"词序列"）
    print("[seg ] 分词中…")
    df["tokens"] = df["content"].map(tokenize)
    df = df[df["tokens"].map(len) > 0].reset_index(drop=True)
    print(f"[seg ] 有效 {len(df)} 条")

    # ---------- TF-IDF ----------
    vec = TfidfVectorizer(
        tokenizer=lambda x: x,        # 已经是 token 列表，直接透传
        preprocessor=lambda x: x,
        token_pattern=None,
        max_features=3000,
        min_df=5,                     # 至少出现在 5 条弹幕里（去掉偶发词）
        max_df=0.2,                   # 出现在 >20% 弹幕里的词没有区分度，丢掉（比 0.5 更狠）
    )
    X = vec.fit_transform(df["tokens"])
    terms = np.array(vec.get_feature_names_out())
    print(f"[tfidf] 矩阵 {X.shape[0]} 条 × {X.shape[1]} 词")

    # ---------- SVD 降维（LSA）----------
    # 短文本的 TF-IDF 矩阵非常稀疏，直接 KMeans 容易退化成一团。
    # 用 TruncatedSVD 压到 100 维，相当于"潜在语义空间"，能把同义/近义合并。
    from sklearn.decomposition import TruncatedSVD
    n_comp = min(100, X.shape[1] - 1)
    svd = TruncatedSVD(n_components=n_comp, random_state=RANDOM_STATE)
    Xs = svd.fit_transform(X)
    from sklearn.preprocessing import normalize
    Xs = normalize(Xs)                # L2 归一化，让欧氏距离≈余弦
    print(f"[svd] 降到 {n_comp} 维，累计解释方差 {svd.explained_variance_ratio_.sum():.3f}")

    # ---------- 选 k：轮廓系数 ----------
    print("[k] 扫描 k=4..10 的轮廓系数（样本大时抽样算，避免太慢）")
    best_k, best_score = 6, -1.0
    n_sample = min(3000, Xs.shape[0])
    rng = np.random.default_rng(RANDOM_STATE)
    idx = rng.choice(Xs.shape[0], n_sample, replace=False)
    for k in range(4, 11):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = km.fit_predict(Xs)
        sc = silhouette_score(Xs[idx], labels[idx], metric="cosine")
        sizes = np.bincount(labels)
        print(f"   k={k:>2}  轮廓系数 {sc:.4f}  最大簇占比 {sizes.max()/len(labels)*100:.1f}%")
        # 退化解惩罚：某一簇占比 > 80% 视为无效（KMeans 崩溃）
        if sizes.max() / len(labels) > 0.8:
            continue
        if sc > best_score:
            best_k, best_score = k, sc
    print(f"[k] 选定 k={best_k}（轮廓系数 {best_score:.4f}）")

    # ---------- 正式聚类 ----------
    km = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=10)
    df["cluster"] = km.fit_predict(Xs)
    # 每条到所属质心的距离（越小越典型）
    dist = km.transform(Xs)
    df["dist"] = dist[np.arange(len(df)), df["cluster"]]

    # ---------- 每个簇的解释 ----------
    print("\n" + "=" * 70)
    order = df["cluster"].value_counts().index.tolist()
    for cid in order:
        sub = df[df["cluster"] == cid]
        # 该簇的 TF-IDF 均值 -> top 词
        mask = (df["cluster"] == cid).values
        mean_vec = np.asarray(X[mask].mean(axis=0)).ravel()
        top_idx = mean_vec.argsort()[::-1][:15]
        top_terms = " ".join(terms[i] for i in top_idx)

        print(f"\n--- 簇 {cid} | 样本 {len(sub)} 条（{len(sub)/len(df)*100:.1f}%）---")
        print(f"关键词: {top_terms}")
        print("代表性弹幕（离质心最近的 5 条）:")
        for _, r in sub.nsmallest(5, "dist").iterrows():
            print(f"   · {r['content'][:60]}")
    print("=" * 70)

    # ---------- 落盘 ----------
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df["topic_name"] = df["cluster"].map(TOPIC_NAMES).fillna("未命名")
    df[["content", "cluster", "topic_name", "dist"]].to_csv(
        OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[done] 写入 {OUT_CSV}（{len(df)} 行）")
    print("[next] 核对 docs/cluster_topics.md 的命名，再写进报告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

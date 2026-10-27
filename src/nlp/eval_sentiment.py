"""情感分析基线评估 —— 用你的 100 条人工标注算准确率

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.nlp.eval_sentiment

前置：
    data/processed/label_sample.csv  的 label 列已填好（正 / 中 / 负）

产出：
    准确率（accuracy）
    每个类的 precision / recall / F1（混淆矩阵）
    **误判案例清单** ← 这是面试最值钱的部分（"模型错在哪、为什么"）
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

import pandas as pd  # noqa: E402
from sklearn.metrics import classification_report, confusion_matrix  # noqa: E402

SAMPLE = ROOT / "data" / "processed" / "label_sample.csv"
ALL = ROOT / "data" / "processed" / "danmaku_sentiment.csv"

# 把各种写法统一成 正/中/负
NORMALIZE = {
    "正": "正", "正面": "正", "正向": "正", "pos": "正", "positive": "正", "1": "正",
    "中": "中", "中性": "中", "neu": "中", "neutral": "中", "0": "中",
    "负": "负", "负面": "负", "负向": "负", "neg": "负", "negative": "负", "-1": "负",
}


def main() -> int:
    if not SAMPLE.exists():
        print(f"[error] 找不到 {SAMPLE}，先跑 src.nlp.sentiment")
        return 1

    s = pd.read_csv(SAMPLE)
    s["label"] = s["label"].astype(str).str.strip().str.lower().map(
        lambda x: NORMALIZE.get(x, x))

    filled = s[s["label"].isin(["正", "中", "负"])]
    print(f"[label] 共 {len(s)} 条，已标注 {len(filled)} 条")
    if len(filled) == 0:
        print("[error] label 列还没填。请打开该文件，在 label 列填 正 / 中 / 负")
        return 1
    if len(filled) < len(s):
        print(f"[warn] 还有 {len(s)-len(filled)} 条没填，只用已填的评估")
        bad = s[~s["label"].isin(["正", "中", "负"])]["label"].unique()
        print(f"       无法识别的值示例: {list(bad)[:5]}")

    # 用内容去匹配全量结果里的 snownlp 预测（盲标样本里没有预测值，避免锚定）
    allres = pd.read_csv(ALL)
    allres = allres.drop_duplicates("content")
    merged = filled.merge(allres[["content", "snow_label", "snow_score"]],
                          on="content", how="left")
    missing = merged["snow_label"].isna().sum()
    if missing:
        print(f"[warn] {missing} 条在全量结果里没匹配上，已丢弃")
        merged = merged.dropna(subset=["snow_label"])

    y_true = merged["label"].tolist()
    y_pred = merged["snow_label"].tolist()
    acc = sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true)

    print("\n" + "=" * 60)
    print(f"基线准确率（snownlp）= {acc*100:.1f}%（{len(y_true)} 条标注样本）")
    print("=" * 60)

    labels = ["正", "中", "负"]
    print("\n===== 混淆矩阵（行=人工标注，列=模型预测）=====")
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print("            " + "".join(f"{l:>6}" for l in labels))
    for i, l in enumerate(labels):
        print(f"人工 {l}  " + "".join(f"{cm[i][j]:>6}" for j in range(len(labels))))

    print("\n===== 各类指标 =====")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    # ---------- 误判案例（面试金句素材）----------
    wrong = merged[merged["label"] != merged["snow_label"]].copy()
    wrong = wrong.sort_values("snow_score")
    print(f"\n===== 误判案例 {len(wrong)} 条（按模型分数从低到高）=====")
    for _, r in wrong.head(20).iterrows():
        print(f"  人工[{r['label']}] 模型[{r['snow_label']}:{r['snow_score']:.2f}]  {str(r['content'])[:44]}")

    # ---------- 自动归类误判类型（粗分类，供你人工复核）----------
    print("\n===== 误判类型的粗略统计 =====")
    def guess_reason(t: str) -> str:
        t = str(t)
        if any(k in t for k in ["？", "?", "怎么", "什么", "吗", "呢", "多少", "如何"]):
            return "疑问句被当情绪"
        if any(k in t for k in ["哈哈", "笑死", "xsl", "233", "hhh", "草"]):
            return "玩梗/笑声被判正面"
        if len(t) <= 4:
            return "极短文本信息不足"
        if any(k in t for k in ["焦虑", "坑", "废", "无语", "离谱", "呵呵"]):
            return "反讽未被识别"
        return "其他"
    wrong["reason"] = wrong["content"].map(guess_reason)
    print(wrong["reason"].value_counts().to_string())
    print("\n[提示] 把这份误判清单写进报告——面试问'你的模型错在哪'时直接用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

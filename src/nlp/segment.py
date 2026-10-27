"""jieba 分词 + 词频 + 词云 —— 第10周周三/周四任务

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.nlp.segment

产出：
    data/processed/danmaku_words.csv    词频表（词, 频次）
    figures/wordcloud_zc.png            职场弹幕词云
    figures/wordcloud_other.png         其他分区弹幕词云（对照组）

三个关键技术点（面试可讲）：
  1. 自定义词典：jieba 默认会把"面试官"切成"面试/官"，把"秋招"切成"秋/招"。
     所以必须加领域词（简历/秋招/内推/转正/跳槽…），否则词频表全是碎片。
  2. 停用词：把"哈哈""就是""这个""什么"这类高频无信息词去掉，
     但**不要一刀切**——"哈哈哈"本身是情绪信号，所以在清洗阶段单独统计，不在这里删。
  3. 权重选择：每条去重后的弹幕算 1 次（不按 dup_count 加权）。
     理由：若按刷屏次数加权，"哈哈"这类会直接霸榜，词频表失去信息量。
     dup_count 单独作为"刷屏强度"指标分析（见 SQL）。
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import jieba  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import db_url  # noqa: E402

OUT_CSV = ROOT / "data" / "processed" / "danmaku_words.csv"
FIG_DIR = ROOT / "figures"

# ---------- 领域自定义词典 ----------
# 不加这些词，jieba 会把它们切碎（如"秋招"→"秋"/"招"）
CUSTOM_WORDS = [
    "简历", "面试", "面试官", "秋招", "春招", "校招", "社招", "内推", "转正",
    "跳槽", "离职", "入职", "试用期", "应届生", "往届生", "双非", "大厂",
    "国企", "考公", "考编", "事业编", "体制内", "副业", "涨薪", "谈薪",
    "年终奖", "绩效", "KPI", "OKR", "五险一金", "公积金", "劳动合同",
    "劳动合同法", "劳动仲裁", "辞退", "裁员", "优化", "裸辞", "躺平",
    "内卷", "卷", "打工人", "社畜", "上班", "上班族", "打工人",
    "自我介绍", "无领导小组", "群面", "单面", "HR", "HR面", "技术面",
    "行业", "转行", "跨行", "职业规划", "第一份工作", "找工作", "求职",
    "投简历", "投递", "offer", "开摆", "996", "007", "大小周",
]

# ---------- 停用词 ----------
# 只去掉"高频但无信息"的虚词/口头语；情绪词（哈哈/笑死/泪目）保留
STOPWORDS = set("""
的 了 是 在 我 你 他 她 它 们 这 那 有 和 就 不 也 都 说 要 会 能 可以
一个 什么 怎么 这个 那个 我们 你们 他们 自己 就是 还是 但是 因为 所以
如果 已经 现在 时候 这样 那样 知道 觉得 真的 其实 应该 可能 没有 不是
一二 三 四 五 六 七 八 九 十 个 位 次 种 点 些 啊 吧 呢 吗 哦 哈
前 后 上 下 里 外 中 大 小 多 少 好 对 嗯 emm 呃 诶 哎 哎呦 噢 哇
发 给 让 把 被 从 到 跟 比 像 做 用 想 看 来 去 过 起来 出来 一下
""".split())

for w in CUSTOM_WORDS:
    jieba.add_word(w, freq=10000)


def load_danmaku(zone: str | None) -> list[str]:
    """从 MySQL 读取弹幕文本。zone=None 表示"非该分区"。"""
    engine = create_engine(db_url(), pool_pre_ping=True)
    if zone:
        sql = ("SELECT d.content FROM danmaku d JOIN video v ON d.bvid=v.bvid "
               "WHERE v.sub_zone = :z")
        params = {"z": zone}
    else:
        sql = ("SELECT d.content FROM danmaku d JOIN video v ON d.bvid=v.bvid "
               "WHERE v.sub_zone <> :z")
        params = {"z": "职业职场"}
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [r[0] for r in rows if r[0]]


def segment(texts: list[str]) -> Counter:
    """分词 + 过滤，返回词频 Counter。"""
    counter: Counter = Counter()
    for t in texts:
        for w in jieba.cut(t):
            w = w.strip()
            if len(w) < 2:                     # 单字基本无信息（"啊""的"）
                continue
            if w in STOPWORDS:
                continue
            if w.isdigit():                    # 纯数字
                continue
            counter[w] += 1
    return counter


def build_wordcloud(counter: Counter, out: Path, title: str) -> None:
    """画词云（中文必须显式指定字体路径，否则全是方块）。"""
    try:
        from wordcloud import WordCloud
    except ImportError:
        print("[warn] 没装 wordcloud，跳过画图")
        return

    import matplotlib
    matplotlib.use("Agg")                      # 无界面后端，避免弹窗
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    font = "C:/Windows/Fonts/msyh.ttc"
    if not Path(font).exists():
        font = "C:/Windows/Fonts/simhei.ttf"

    wc = WordCloud(
        font_path=font,
        width=1200, height=700,
        background_color="white",
        max_words=150,
        colormap="viridis",
    ).generate_from_frequencies(counter)

    out.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 7))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title(title, fontsize=16)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[fig] 已保存 {out}")


def main() -> int:
    # ---------- 职场 ----------
    zc_texts = load_danmaku("职业职场")
    print(f"[load] 职业职场弹幕 {len(zc_texts)} 条")
    zc_words = segment(zc_texts)
    print(f"[seg ] 职业职场词表 {len(zc_words)} 个词")
    print("[top20]", ", ".join(f"{w}:{c}" for w, c in zc_words.most_common(20)))

    # ---------- 对照组 ----------
    other_texts = load_danmaku(None)
    print(f"\n[load] 其他分区弹幕 {len(other_texts)} 条")
    other_words = segment(other_texts)
    print(f"[seg ] 其他分区词表 {len(other_words)} 个词")
    print("[top20]", ", ".join(f"{w}:{c}" for w, c in other_words.most_common(20)))

    # ---------- 落盘 ----------
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([
        {"分区": "职业职场", "词": w, "频次": c} for w, c in zc_words.most_common(500)
    ] + [
        {"分区": "其他分区", "词": w, "频次": c} for w, c in other_words.most_common(500)
    ])
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[done] 词频表写入 {OUT_CSV}（{len(df)} 行）")

    # ---------- 词云 ----------
    build_wordcloud(zc_words, FIG_DIR / "wordcloud_zc.png", "职业职场 弹幕词云")
    build_wordcloud(other_words, FIG_DIR / "wordcloud_other.png", "其他知识区 弹幕词云（对照）")

    # ---------- 两路差异 ----------
    print("\n===== 职场特有高频词（职场频次/其他频次 比值最高）=====")
    rows = []
    for w, c in zc_words.most_common(200):
        co = other_words.get(w, 0)
        if c >= 20:
            rows.append((w, c, co, c / (co + 1)))
    for w, c, co, ratio in sorted(rows, key=lambda x: -x[3])[:15]:
        print(f"  {w:<8} 职场 {c:>4} | 其他 {co:>5} | 倍数 {ratio:>6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

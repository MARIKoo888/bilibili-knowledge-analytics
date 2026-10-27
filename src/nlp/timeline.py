"""弹幕时间轴分析 —— 观众在第几分钟最激动？【本项目最有趣的图】

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.nlp.timeline

产出：
    figures/danmaku_timeline_zc.png    职场视频的弹幕密度 + 笑声密度时间轴

为什么这个分析好玩且独有：
  1. 评论没有时间轴——"第几分钟观众最激动"这类问题**只有弹幕能回答**
  2. 情绪模型不可用（实测 snownlp 27% < 全猜 88%），但"哈哈"是**可靠的笑声代理**：
     人笑的时候真的会发"哈哈"，这是行为信号，不是模型猜测
  3. 能验证一个运营常识："前 30 秒决定留人"到底是不是真的

方法：
  - 每条弹幕带 send_time_sec（出现在视频第几秒）
  - 用它除以视频总时长，得到"相对位置 0~100%"，让不同长度的视频可比
  - 分 20 个桶（每桶 5%），统计每桶的弹幕条数（已按视频时长归一化）
  - 同时对"含哈哈/笑死/233"的弹幕单独统计，得到笑声密度曲线
"""
from __future__ import annotations

import re
import sys
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

FIG = ROOT / "figures" / "danmaku_timeline_zc.png"
N_BINS = 20              # 20 个桶 = 每 5%
MIN_DANMAKU = 30         # 只要弹幕 >= 30 条的视频（否则曲线没意义）
TOP_N = 4                # 画播放最高的 4 个视频

# 笑声 / 强反应标记（比情感模型可靠的行为信号）
LAUGH = re.compile(r"哈哈|笑死|233|xsl|hhh|😂|🤣", re.IGNORECASE)
SHOCK = re.compile(r"？？？|\?\?\?|卧槽|我靠|啊这|离谱|绝了")

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
matplotlib.rcParams["axes.unicode_minus"] = False


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (候选视频列表, 弹幕明细)。"""
    engine = create_engine(db_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        vids = pd.DataFrame(conn.execute(text(
            "SELECT v.bvid, v.title, v.duration_sec, v.view_cnt, "
            "       COUNT(d.dmid) AS n_dm "
            "FROM video v JOIN danmaku d ON v.bvid = d.bvid "
            "WHERE v.sub_zone = '职业职场' AND v.duration_sec > 0 "
            "GROUP BY v.bvid, v.title, v.duration_sec, v.view_cnt "
            "HAVING n_dm >= :m ORDER BY n_dm DESC LIMIT :n"
        ), {"m": MIN_DANMAKU, "n": TOP_N}).fetchall(),
            columns=["bvid", "title", "duration_sec", "view_cnt", "n_dm"])

        bvids = tuple(vids["bvid"])
        dm = pd.DataFrame(conn.execute(text(
            "SELECT bvid, content, send_time_sec FROM danmaku "
            f"WHERE bvid IN {bvids}"
        )).fetchall(), columns=["bvid", "content", "send_time_sec"])
    return vids, dm


def bin_curve(df: pd.DataFrame, duration: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """把一条视频的弹幕按相对位置分桶，返回 (桶中心%, 全弹幕密度, 笑声密度)。"""
    rel = (df["send_time_sec"].clip(lower=0) / max(duration, 1)).clip(0, 0.999)
    idx = (rel * N_BINS).astype(int)
    total = np.bincount(idx, minlength=N_BINS).astype(float)
    laugh_mask = df["content"].astype(str).str.contains(LAUGH, regex=True)
    laugh = np.bincount(idx[laugh_mask], minlength=N_BINS).astype(float)

    # 归一化成"每 1% 时长的弹幕数"，让不同长度视频可比
    pct_per_bin = 100.0 / N_BINS
    total = total / pct_per_bin
    laugh = laugh / pct_per_bin

    centers = (np.arange(N_BINS) + 0.5) * pct_per_bin
    return centers, total, laugh


def main() -> int:
    vids, dm = load_data()
    if vids.empty:
        print(f"[error] 没有弹幕数 >= {MIN_DANMAKU} 的职场视频")
        return 1
    print(f"[load] 选中 {len(vids)} 个视频，弹幕 {len(dm)} 条")

    fig, axes = plt.subplots(len(vids), 1, figsize=(11, 3.0 * len(vids)), sharex=True)
    if len(vids) == 1:
        axes = [axes]

    all_total, all_laugh = [], []
    for ax, (_, v) in zip(axes, vids.iterrows()):
        sub = dm[dm["bvid"] == v["bvid"]]
        centers, total, laugh = bin_curve(sub, int(v["duration_sec"]))
        all_total.append(total / max(total.max(), 1))       # 归一到 0~1 便于平均
        all_laugh.append(laugh / max(laugh.max(), 1))

        ax.plot(centers, total, color="#2E86DE", lw=2, label="弹幕密度")
        ax.fill_between(centers, total, alpha=0.15, color="#2E86DE")
        ax2 = ax.twinx()
        ax2.plot(centers, laugh, color="#EE5A24", lw=1.6, ls="--", label="笑声密度")
        ax2.set_ylabel("笑声/1%时长", color="#EE5A24", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="#EE5A24", labelsize=8)

        # 标出峰值位置
        peak = centers[int(np.argmax(total))]
        ax.axvline(peak, color="#999", ls=":", lw=1)
        ax.annotate(f"峰值 {peak:.0f}%", xy=(peak, total.max()),
                    xytext=(5, 6), textcoords="offset points", fontsize=9, color="#444")

        title = str(v["title"])[:38]
        ax.set_title(f"{title}…  |  {int(v['duration_sec'])//60}分{v['view_cnt']/10000:.0f}万播放",
                     fontsize=10, loc="left")
        ax.set_ylabel("弹幕/1%时长", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25)

    axes[-1].set_xlabel("视频相对进度（%，0=开头，100=结尾）", fontsize=10)
    fig.suptitle("职场视频的观众情绪时间轴：他们在第几分钟最激动？", fontsize=14, y=1.0)
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[fig] 已保存 {FIG}")

    # ---------- 汇总：所有视频平均的曲线 ----------
    centers = (np.arange(N_BINS) + 0.5) * (100.0 / N_BINS)
    avg_total = np.mean(all_total, axis=0)
    avg_laugh = np.mean(all_laugh, axis=0)
    print("\n===== 平均弹幕密度（相对位置）=====")
    for c, t, l in zip(centers, avg_total, avg_laugh):
        bar = "█" * int(t * 40)
        print(f"  {c:>5.0f}%  {bar:<40} 弹幕{avg_total[list(centers).index(c)]:.2f} 笑{l:.2f}")

    # 前 5% vs 后 5% 的对比（验证"前30秒决定留人"）
    head = avg_total[:1].mean()
    tail = avg_total[-1:].mean()
    print(f"\n[结论素材] 前 5% 时长平均弹幕密度 {head:.2f}，最后 5% 为 {tail:.2f}，比值 {head/max(tail,1e-6):.2f}x")
    peak_pos = centers[int(np.argmax(avg_total))]
    print(f"[结论素材] 平均弹幕峰值出现在 {peak_pos:.0f}% 位置")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

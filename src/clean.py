"""清洗：3 个 raw json 合并 -> data/processed/videos.csv

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.clean

处理 4 个已知问题（见 任务清单.md 断点）：
  ① bvid 为空的行  -> 丢弃（没有主键无法入库）
  ② HTML 实体 &amp; -> 解码成 &
  ③ 时长异常值     -> 打标 is_duration_outlier=1（不删，保留可追溯）
  ④ 分区是混的     -> 保留，加 sub_zone 维度（已决策：方案 B）

专业习惯（面试可讲）：
  - 清洗必须输出"清洗前后行数对比"日志，否则你不知道自己丢了什么
  - 异常值"打标不删"：删了就无法回溯，也会让结论不可解释
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

RAW_FILES = ["sample.json", "videos_zc.json", "videos_kw.json"]
OUT = ROOT / "data" / "processed" / "videos.csv"

# 时长超过 3 小时（10800 秒）视为疑似直播回放/合集 → 打标，不删
DURATION_OUTLIER_SEC = 3 * 3600


def load_raw() -> list[dict]:
    """读所有 raw json，拼成一个列表。"""
    rows: list[dict] = []
    for name in RAW_FILES:
        p = ROOT / "data" / "raw" / name
        if not p.exists():
            print(f"[load] 跳过（不存在）: {name}")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"[load] {name}: {len(data)} 条")
        rows.extend(data)
    return rows


def clean(rows: list[dict]) -> pd.DataFrame:
    """逐条清洗 + 去重，返回 DataFrame。"""
    kept: list[dict] = []
    seen: set[str] = set()
    dropped_empty_bvid = 0
    dropped_dup = 0

    for r in rows:
        bvid = str(r.get("bvid") or "").strip()

        # ---------------- TODO 1：丢弃 bvid 为空的行 ----------------
        # 提示：空的话 dropped_empty_bvid += 1 然后 continue
        if not bvid:
            dropped_empty_bvid += 1
            continue

        # ---------------- TODO 2：按 bvid 去重 ----------------
        # 提示：已经在 seen 里的话 dropped_dup += 1 然后 continue；
        #       否则 seen.add(bvid)
        if bvid in seen:
            dropped_dup += 1
            continue
        seen.add(bvid)

        # ---------------- 下面已写好，你只需看懂 ----------------
        # ② HTML 实体解码：&amp; -> &  &quot; -> "
        title = html.unescape(str(r.get("title") or "")).strip()
        desc = html.unescape(str(r.get("description") or "")).strip()

        # ③ 时长异常打标（不删）
        dur = r.get("duration_sec")
        try:
            dur = int(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur = None
        is_outlier = 1 if (dur is not None and dur > DURATION_OUTLIER_SEC) else 0

        kept.append({
            **r,
            "bvid": bvid,
            "title": title,
            "description": desc,
            "duration_sec": dur,
            "is_duration_outlier": is_outlier,
        })

    print(f"\n[clean] 原始 {len(rows)} 条")
    print(f"[clean] 丢弃 bvid 为空: {dropped_empty_bvid}")
    print(f"[clean] 丢弃重复 bvid : {dropped_dup}")
    print(f"[clean] 保留          : {len(kept)}")

    df = pd.DataFrame(kept)

    # 数值列统一成可空整数（避免入库时 int 溢出/NaN 报错）
    int_cols = ["aid", "mid", "duration_sec", "pub_hour", "pub_weekday", "view_cnt",
                "like_cnt", "coin_cnt", "fav_cnt", "danmaku_cnt", "reply_cnt",
                "share_cnt", "is_duration_outlier"]
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    return df


def report(df: pd.DataFrame) -> None:
    """清洗后的体检报告 —— 每次跑都看一眼，别做完就走。"""
    print("\n===== 清洗后体检 =====")
    print("行数 :", len(df))
    print("列数 :", len(df.columns))
    print("\n二级分区分布:")
    print(df["sub_zone"].value_counts().head(12).to_string())
    print("\n时长异常标记:", int(df["is_duration_outlier"].sum()), "条")
    print("播放为空/0 :", int((df["view_cnt"].fillna(0) == 0).sum()), "条")
    print("时长为空   :", int(df["duration_sec"].isna().sum()), "条")
    print("\n播放分位:")
    print(df["view_cnt"].describe().to_string())


def main() -> int:
    rows = load_raw()
    if not rows:
        print("[error] 一个 raw 文件都没读到")
        return 1
    df = clean(rows)
    report(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")   # utf-8-sig 让 Excel 不乱码
    print(f"\n[done] 写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

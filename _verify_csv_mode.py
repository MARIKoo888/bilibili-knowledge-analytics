"""验证：CSV 模式（pandas）算出的数字，与 MySQL 模式（SQL）是否一致

做法：直接用 data/processed/videos.csv 复现 app/common.py 里的 pandas 逻辑，
      和之前 SQL 跑出来的已知答案对比。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

CSV = Path(__file__).resolve().parent / "data" / "processed" / "videos.csv"
df = pd.read_csv(CSV)
df["is_duration_outlier"] = df["is_duration_outlier"].fillna(0).astype(int)
v = df[df["is_duration_outlier"] == 0]
print(f"载入 {len(df)} 行，有效 {len(v)} 行\n")

ok = True


def check(name, got, want, tol=0.01):
    global ok
    if want is None:
        print(f"  {name}: {got}")
        return
    good = abs(got - want) <= max(tol, abs(want) * 0.001)
    ok = ok and good
    print(f"  {'OK ' if good else 'FAIL'} {name}: 得到 {got:,.1f}，应为 {want:,.1f}")


print("=== 1. 总体中位数（SQL 结果 41532）===")
check("播放中位数", v["view_cnt"].median(), 41532, tol=1)

print("\n=== 2. 分区中位数 Top3（SQL: 科学科普 1488721 / 人文历史 1274884）===")
g = v.groupby("sub_zone")["view_cnt"].agg(["median", "count"]).reset_index()
g = g[g["count"] >= 10].sort_values("median", ascending=False)
print(g.head(3).to_string(index=False))
check("科学科普", float(g[g.sub_zone == "科学科普"]["median"].iloc[0]), 1488721, tol=1)
check("人文历史", float(g[g.sub_zone == "人文历史"]["median"].iloc[0]), 1274884, tol=1)

print("\n=== 3. 时长分桶·仅职场（SQL: 14980/20554/46597/25328/17367）===")
zc = v[v["sub_zone"] == "职业职场"].dropna(subset=["duration_sec"]).copy()
zc["桶"] = pd.cut(zc["duration_sec"], bins=[0, 180, 480, 900, 1800, 10**9],
                  labels=["<3分", "3-8分", "8-15分", "15-30分", ">30分"], right=False)
d = zc.groupby("桶", observed=False)["view_cnt"].agg(["median", "count"]).reset_index()
print(d.to_string(index=False))
for label, want in zip(["<3分", "3-8分", "8-15分", "15-30分", ">30分"],
                       [14980, 20554, 46597, 25328, 17367]):
    row = d[d["桶"] == label]
    if len(row):
        check(f"  {label}", float(row["median"].iloc[0]), want, tol=1)

print("\n=== 4. 集中度（SQL: 职场沟通 45.0 最高 / 简历修改 7.2 最低）===")
kw = v[v["source_keyword"].astype(str).str.startswith("kw:")].copy()
kw["选题"] = kw["source_keyword"].str.replace("kw:", "", regex=False)
c = kw.groupby("选题")["view_cnt"].agg(
    [("n", "count"),
     ("p90", lambda s: s.quantile(0.9, interpolation="lower")),
     ("med", "median")]).reset_index()
c["集中度"] = (c["p90"] / c["med"]).round(1)
print(c.sort_values("集中度", ascending=False).to_string(index=False))
top = c.sort_values("集中度", ascending=False).iloc[0]
bot = c.sort_values("集中度", ascending=False).iloc[-1]
check("最高集中度", float(top["集中度"]), 45.0, tol=0.5)
check("最低集中度", float(bot["集中度"]), 7.2, tol=0.5)

print("\n=== 5. 收藏率 vs 点赞率（SQL: 职场 3.39/1.93，比值 1.75）===")
f = v[v["view_cnt"] > 1000].copy()
f["fav_rate"] = f["fav_cnt"] / f["view_cnt"] * 100
f["like_rate"] = f["like_cnt"] / f["view_cnt"] * 100
z = f[f["sub_zone"] == "职业职场"]
check("职场收藏率%", float(z["fav_rate"].mean()), 3.39, tol=0.05)
check("职场点赞率%", float(z["like_rate"].mean()), 1.93, tol=0.05)
check("收藏/点赞比值", float(z["fav_rate"].mean() / z["like_rate"].mean()), 1.75, tol=0.05)

print("\n" + ("=" * 50))
print("全部一致 ✅ CSV 模式可以放心用" if ok else "有偏差 ❌ 需要修 pandas 逻辑")
sys.exit(0 if ok else 1)

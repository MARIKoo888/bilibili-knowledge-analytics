# SQL 目录规范

## 命名规范

```
sql/01_zone_supply_demand.sql      # 编号_主题.sql
sql/02_pub_hour_weekday.sql
...
```

## 每条 SQL 必须带文件头（面试官会看这个）

```sql
-- ============================================================
-- 业务问题：Q1 知识区哪些细分选题供过于求？  职业职场类
-- 指标口径：供给量 = 该细分视频数；需求量 = 该细分播放量中位数     供需比=供给量/需求量
-- 对比基准：知识区整体中位数
-- 结论：（跑完后用一句话写结论，没有结论就是没做完）
-- 已知局限：（如：仅覆盖 10 个关键词的抽样）
-- ============================================================
SELECT ...
```

> 规矩：**没有"结论"一行的 SQL 文件，视为未完成**。这一条是从"我写了SQL"升级到"我做了分析"的关键。

## 12 条清单（对照 `docs/03_课题技术方案.md` 第三节）

| # | 文件 | 主要技能 | 状态 |
|---|---|---|---|
| 1 | 01_zone_supply_demand.sql | GROUP BY + 中位数 | ☐ |
| 2 | 02_pub_hour_weekday.sql | 交叉分组 | ☐ |
| 3 | 03_duration_bins.sql | CASE 分桶 | ☐ |
| 4 | 04_top_by_zone.sql | ROW_NUMBER 分区排名 | ☐ |
| 5 | 05_engage_rate_compare.sql | 多指标口径对比 | ☐ |
| 6 | 06_quadrant_boom.sql | 分位数定阈值 + CASE | ☐ |
| 7 | 07_up_follower_bins.sql | 分桶聚合 | ☐ |
| 8 | 08_weekly_supply_trend.sql | 日期截断 + LAG 环比 | ☐ |
| 9 | 09_keyword_competition.sql | 关键词竞争度 | ☐ |
| 10 | 10_sentiment_by_zone.sql | JOIN + 分组 | ☐ |
| 11 | 11_negative_top_videos.sql | 排序 + 阈值 | ☐ |
| 12 | 12_publish_interval.sql | LAG 差值（可选） | ☐ |

## 中位数模板（MySQL 没有 MEDIAN）

```sql
WITH r AS (
  SELECT zone, view_cnt,
         ROW_NUMBER() OVER (PARTITION BY zone ORDER BY view_cnt) AS rn,
         COUNT(*)     OVER (PARTITION BY zone)                   AS cnt
  FROM video
)
SELECT zone, AVG(view_cnt) AS median_view, MAX(cnt) AS n
FROM r
WHERE rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
GROUP BY zone
ORDER BY median_view DESC;
```

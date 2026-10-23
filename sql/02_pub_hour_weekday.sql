-- ============================================================
-- 业务问题：Q2 什么发布时段（小时×星期）能拿到更高播放？
-- 指标口径：因变量 = 播放量中位数；分桶 = 星期(1-7) × 时段(上午6-11/下午12-17/晚间18+)
--           深夜 0-5 点仅 10 条，样本不足，已排除
-- 对比基准：同星期同时段内部比较；基准值 = 全区播放中位数 41,532
-- 结论：本数据不支持"发布时段×星期"的可靠归因。
--   21 个格子样本量 4–36 条，同一时段内中位数极差达 18 倍（如周二下午 n=36 仅 5,647，
--   而周一下午 n=32 达 372,663），波动由个别爆款主导，噪声大于信号。
--   更根本的问题：样本来自排行榜/搜索前几页（本身偏向爆款），
--   不能代表知识区整体发布行为，故不能用它推断"何时发布更优"。
-- → 决策含义：时段建议需改用"同 UP 主多视频对比"或"随机抽样"才能验证。
-- 已知局限：① 格子样本 4–36 条；② 采集偏向爆款；③ 视频跨 2022–2026 年，年份混淆未控制
-- ============================================================

WITH base AS (
    SELECT pub_weekday,view_cnt,
       CASE WHEN pub_hour < 6  THEN '深夜'
            WHEN pub_hour < 12 THEN '上午'
            WHEN pub_hour < 18 THEN '下午'
            ELSE '晚间' END AS 时段
    FROM video
    WHERE is_duration_outlier = 0
        AND pub_hour >= 6
),
r AS (
  SELECT pub_weekday, 时段, view_cnt,
     ROW_NUMBER() OVER (PARTITION BY pub_weekday, 时段 ORDER BY view_cnt) AS rn,
     COUNT(*)     OVER (PARTITION BY pub_weekday, 时段)                   AS cnt
  FROM base
)

SELECT pub_weekday, 时段, MAX(cnt) AS n,
       ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                      THEN view_cnt END)) AS 中位数
FROM r
GROUP BY pub_weekday, 时段
ORDER BY 中位数 DESC;  
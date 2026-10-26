--高播放·高互动只有 18 条（5.2%），而高播放·低互动有 69 条。

--如果播放和互动率互相独立，那"高播放·高互动"应该占 25%×25% = 6.25%，约 21 条。实际 18 条，接近独立但略偏负。

--更值得注意的是：高播放·低互动（69）远多于 低播放·高互动（68）——两者接近，但结合总体看：

--播放量越大的视频，互动率往往越低。 因为互动率的分母是播放量——播放涨得比点赞快。

--这正是 docs/02_metrics.md 里写的"分母陷阱"。 你自己在指标定义时就预见到了，现在数据证实了。

--"爆款 ≠ 高互动。高播放视频的互动率普遍偏低，因为互动率的分母（播放量）随曝光增长快于分子。因此内容质量评估不能用互动率单一指标，必须结合绝对播放量分档来看。"

WITH valid AS (
    SELECT view_cnt, like_cnt, fav_cnt,
           (like_cnt + fav_cnt) / NULLIF(view_cnt, 0) AS 互动率
    FROM video
    WHERE is_duration_outlier = 0 AND view_cnt > 1000
),
-- 阈值1：播放量的 P75（按播放排序）
th_v AS (
    SELECT ROUND(AVG(CASE WHEN rn = FLOOR(cnt*0.75) THEN view_cnt END)) AS v75
    FROM (SELECT view_cnt,
                 ROW_NUMBER() OVER (ORDER BY view_cnt) AS rn,
                 COUNT(*)     OVER ()                   AS cnt
          FROM valid) a
),
-- 阈值2：互动率的 P75（按互动率排序 ← 关键区别）
th_e AS (
    SELECT ROUND(AVG(CASE WHEN rn = FLOOR(cnt*0.75) THEN 互动率 END), 4) AS e75
    FROM (SELECT 互动率,
                 ROW_NUMBER() OVER (ORDER BY 互动率) AS rn,
                 COUNT(*)     OVER ()                AS cnt
          FROM valid) b
)
SELECT
    CASE WHEN v.view_cnt >= tv.v75 THEN '高播放' ELSE '低播放' END AS 播放档,
    CASE WHEN v.互动率  >= te.e75 THEN '高互动' ELSE '低互动' END AS 互动档,
    COUNT(*) AS n
FROM valid v
CROSS JOIN th_v tv
CROSS JOIN th_e te
GROUP BY 播放档, 互动档
ORDER BY n DESC;
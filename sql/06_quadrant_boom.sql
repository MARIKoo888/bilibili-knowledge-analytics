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
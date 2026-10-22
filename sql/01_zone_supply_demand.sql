-- ============================================================
-- 业务问题：Q1 求职类哪些细分选题供过于求 / 供不应求？
-- 指标口径：
--   需求量 = 该关键词下播放量的中位数
--   竞争度 = 注意力集中度 = P90播放 / 中位数播放
--   （原口径"供给量/需求量"不可用，原因见已知局限）
-- 对比基准：5 个关键词横向比较（每词 3 页、采集方式一致，可公平比较）
-- 结论：5 个选题的需求（播放中位数）差异不大（1.36万–1.91万），
--   但注意力集中度差异显著（7.2–45.0）：职场沟通最高（45.0），
--   简历修改与应届生求职最低（7.2）。
--   → 普通账号优先做简历修改/应届生求职（稳定有量）；
--     有爆款能力则做职场沟通（天花板 86 万）。
-- 已知局限：
--   1) 供给量不可测：采集受"每词 3 页 ≤60 条"上限截断；
--      B站 search 接口 numResults 对所有关键词统一封顶 1000，
--      故放弃"视频数/播放中位数"的供需比，改用样本内集中度代理。
--   2) 样本量 40–59 条偏小（每词），结论为方向性。
--   3) 分区维度不可比：职业职场为定向采集，科学科普来自排行榜，
--      抽样强度差十几倍（见语句1/2，用于报告"数据可信度"章节）。
--   4) coin/share 字段缺失，互动率只能用 (点赞+收藏)/播放。
-- ============================================================

-- 语句1/2：分区维度对比（仅作抽样偏差的证据，不用于 Q1 结论）

SELECT sub_zone, COUNT(*) AS 供给量
FROM video
WHERE is_duration_outlier = 0
GROUP BY sub_zone
ORDER BY 供给量 DESC;

SELECT sub_zone,view_cnt,
    ROW_NUMBER() OVER(PARTITION BY sub_zone ORDER BY view_cnt) AS rn,
    COUNT(*)     OVER(PARTITION BY sub_zone)                   AS cnt
FROM video
WHERE is_duration_outlier = 0
ORDER BY sub_zone,view_cnt
LIMIT 30;

--语句3

WITH r AS (
  SELECT source_keyword, view_cnt,
         ROW_NUMBER() OVER (PARTITION BY source_keyword ORDER BY view_cnt) AS rn,
         COUNT(*)     OVER (PARTITION BY source_keyword)                   AS cnt
  FROM video 
  WHERE is_duration_outlier = 0
  AND source_keyword LIKE 'kw:%' 
)
SELECT source_keyword,
       MAX(cnt) AS n,
       ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                      THEN view_cnt END))                       AS 中位数,
       ROUND(AVG(CASE WHEN rn = FLOOR(cnt*0.9)
                      THEN view_cnt END))                       AS P90播放,
       ROUND(AVG(CASE WHEN rn = FLOOR(cnt*0.9) THEN view_cnt END)
             / NULLIF(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                               THEN view_cnt END), 0), 1)       AS 集中度

FROM r
GROUP BY source_keyword
ORDER BY 集中度 DESC;
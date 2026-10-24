-- ============================================================
-- 业务问题：Q2 视频时长与播放量的关系 —— 多长的视频播放中位数更高？
-- 指标口径：因变量 = 播放量中位数；自变量 = 时长桶（5 档，单位秒）
-- 对比基准：
--   语句1 基准 = 全区播放中位数 41,532（不控制分区）
--   语句2 基准 = 职业职场分区内（控制分区，n=173）
-- 结论：
--   ① 不控制分区时（语句1）：呈现 W 形 —— <3分钟 61,825、8–15分钟 78,408、
--      15–30分钟 77,938 都高，3–8分钟最低（22,629）。
--   ② 控制分区只看职业职场（语句2）后，两个高点塌陷：
--      <3分钟 61,825→14,980（-76%）、15–30分钟 77,938→25,328（-67%）。
--      → 说明这两个高点主要由**其他分区的娱乐/搞笑类短视频**贡献，不是时长效应。
--   ③ 唯一在两个版本中都成立（稳健）的结论：
--      8–15 分钟播放中位数最高（全区 78,408 / 职场内 46,597），
--      在职场内是 3–8 分钟（20,554）的 2.3 倍。
-- → 行动建议：职场垂类内容时长应控制在 8–15 分钟；
--   做 3 分钟以内或 15 分钟以上，在本数据中看不到优势。
--   这是"控制变量"的直接证据，也是全项目最值钱的一段方法论。
-- 已知局限：
--   ① 只控制了分区，**未控制 UP 主粉丝量**（粉丝数据未采集）；
--   ② coin/share 缺失，无法算综合互动率；
--   ③ 样本偏向爆款（排行榜+搜索前几页）；
--   ④ 职场内"4_15到30分钟"桶 n=20，样本偏小。
-- ============================================================


-- ============================================================
-- 【语句 1】不控制分区：全部 403 条视频按 5 个时长桶比中位数
-- 用途：作为"控制变量前后对比"的基线。
-- ============================================================
WITH base AS (
    SELECT
        view_cnt,                                                    -- 要用的指标：播放量
        CASE WHEN duration_sec < 180  THEN '1_小于3分钟'              -- 0~179 秒
             WHEN duration_sec < 480  THEN '2_3到8分钟'               -- 180~479 秒
             WHEN duration_sec < 900  THEN '3_8到15分钟'              -- 480~899 秒
             WHEN duration_sec < 1800 THEN '4_15到30分钟'             -- 900~1799 秒
             ELSE                          '5_大于30分钟'             -- 1800 秒以上
        END AS 时长桶                                                -- 新列名，后面靠它分组
    FROM video
    WHERE is_duration_outlier = 0                                    -- 排除 >3 小时的直播回放/课程合集
),
r AS (
    SELECT
        时长桶,
        view_cnt,
        ROW_NUMBER() OVER (PARTITION BY 时长桶 ORDER BY view_cnt) AS rn,   -- 组内按播放升序编号
        COUNT(*)     OVER (PARTITION BY 时长桶)                   AS cnt   -- 组内总条数
    FROM base
)
SELECT
    时长桶,
    MAX(cnt) AS n,                                                   -- 该桶样本量
    ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))    -- 只留正中间那 1~2 行
                   THEN view_cnt END))   AS 播放中位数              -- AVG 忽略 NULL
FROM r
GROUP BY 时长桶
ORDER BY 时长桶;


-- ============================================================
-- 【语句 2】控制分区：只看职业职场（n=173）
-- 和语句1 唯一的区别就是 WHERE 里多了一行 sub_zone 过滤。
-- 用途：验证语句1 的规律是不是"分区混杂"造成的（辛普森悖论检验）。
-- ============================================================
WITH base AS (
    SELECT
        view_cnt,
        CASE WHEN duration_sec < 180  THEN '1_小于3分钟'
             WHEN duration_sec < 480  THEN '2_3到8分钟'
             WHEN duration_sec < 900  THEN '3_8到15分钟'
             WHEN duration_sec < 1800 THEN '4_15到30分钟'
             ELSE                          '5_大于30分钟'
        END AS 时长桶
    FROM video
    WHERE is_duration_outlier = 0
      AND sub_zone = '职业职场'                                       -- ★ 控制变量：只看一个分区
),
r AS (
    SELECT
        时长桶,
        view_cnt,
        ROW_NUMBER() OVER (PARTITION BY 时长桶 ORDER BY view_cnt) AS rn,
        COUNT(*)     OVER (PARTITION BY 时长桶)                   AS cnt
    FROM base
)
SELECT
    时长桶,
    MAX(cnt) AS n,
    ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
                   THEN view_cnt END))   AS 播放中位数
FROM r
GROUP BY 时长桶
ORDER BY 时长桶;

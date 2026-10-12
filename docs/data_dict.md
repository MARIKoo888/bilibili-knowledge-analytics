# 数据字典与已知坑（第7周周一任务）

## 一、字段字典

### video 表
| 字段 | 类型 | 含义 | 单位/取值 | 口径注意 |
|---|---|---|---|---|
| bvid | varchar | 视频唯一ID | BV1xx… | 主键 |
| title | varchar | 标题 | | 含 emoji/特殊符号，分析前要清理吗？ |
| zone / sub_zone | varchar | 一级/二级分区 | | 分区命名会变，采集时间不同可能不一致 |
| tag_list | varchar | 标签 | 逗号分隔 | 需拆分成多行才能统计 |
| duration_sec | int | 时长 | 秒 | API 返回的是秒 |
| pub_time | datetime | 发布时间 | | **时区**：接口返回 unix 时间戳，转本地时间 |
| view_cnt / like_cnt / coin_cnt / fav_cnt / danmaku_cnt / reply_cnt | int | 计数 | 次 | **快照值**，必须配 crawled_at |
| source_keyword | varchar | 采集来源关键词 | | 用于分析抽样偏差 |
| crawled_at | datetime | 采集时间 | | 数据截面时间 |

### comment 表
| 字段 | 含义 | 口径注意 |
|---|---|---|
| rpid | 评论ID | 主键 |
| content | 评论内容 | 含表情、@、URL，需清洗 |
| like_cnt | 评论点赞数 | 可用于加权（高赞评论代表主流意见） |
| parent_rpid | 父评论 | 0 = 一级评论；要不要只分析一级？ |
| sentiment | 情感标签 | 分析后回填：1 正 / 0 中 / -1 负 |

## 二、已知的坑（至少写 3 条，第7周一边做一边补）

1. **"万"字单位**：页面显示"12.3万"，接口返回的可能是整数 —— 统一成整数，别混用。
2. **快照漂移**：同一条视频两次采集播放量不同 → 报告里必须声明"数据截面 = YYYY-MM-DD"。
3. （待填）
4. （待填）

## 三、数据量与分布自检（每次入库后跑）

```sql
SELECT COUNT(*) AS videos, COUNT(DISTINCT mid) AS ups,
       MIN(pub_time) AS first_pub, MAX(pub_time) AS last_pub
FROM video;

-- 分区分布：有没有某个分区样本过少（<50 条）导致结论不稳
SELECT zone, sub_zone, COUNT(*) FROM video GROUP BY 1,2 ORDER BY 3 DESC;

-- 缺失值体检
SELECT SUM(title IS NULL OR title='') AS no_title,
       SUM(duration_sec IS NULL)      AS no_duration,
       SUM(view_cnt IS NULL)          AS no_view,
       SUM(pub_time IS NULL)          AS no_pub
FROM video;
```

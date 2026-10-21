-- ============================================================
-- 建表脚本：bili 库（M1 里程碑）
-- 业务问题：支撑 Q1 供需分析 / Q2 爆款要素归因 / Q3 弹幕评论洞察
-- 设计说明：
--   1. 三张表：up_author（UP主快照）/ video（视频快照）/ danmaku（弹幕，第10周用）
--   2. video 表冗余 pub_hour / pub_weekday：高频分组维度，避免每次 HOUR() 计算
--   3. 叫"快照表"是因为 播放/点赞 是累计值，会随时间涨 —— 所以必须存 crawled_at
--   4. 没有用户表：拿不到用户级曝光数据，所以不做协同过滤（诚实是加分项）
-- ============================================================

USE bili;

-- UP主快照表 -------------------------------------------------
CREATE TABLE IF NOT EXISTS up_author (
  mid         BIGINT       PRIMARY KEY COMMENT 'UP主ID',
  name        VARCHAR(128)          COMMENT '昵称',
  follower    INT                   COMMENT '粉丝数(快照,本项目暂缺)',
  video_count INT                   COMMENT '投稿数(快照,本项目暂缺)',
  sign        VARCHAR(255)          COMMENT '签名(本项目暂缺)',
  crawled_at  DATETIME              COMMENT '采集时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='UP主快照表';

-- 视频表 ----------------------------------------------------
CREATE TABLE IF NOT EXISTS video (
  bvid           VARCHAR(20)  PRIMARY KEY COMMENT 'BV号',
  aid            BIGINT                COMMENT 'av号',
  title          VARCHAR(300)          COMMENT '标题(已去HTML标签/实体)',
  description    TEXT                  COMMENT '简介',
  mid            BIGINT                COMMENT 'UP主ID',
  zone           VARCHAR(64)           COMMENT '一级分区',
  sub_zone       VARCHAR(64)           COMMENT '二级分区',
  tag_list       VARCHAR(500)          COMMENT '标签,逗号分隔',
  duration_sec   INT                   COMMENT '时长(秒)',
  pub_time       DATETIME              COMMENT '发布时间',
  pub_hour       TINYINT               COMMENT '发布小时(冗余便于分析)',
  pub_weekday    TINYINT               COMMENT '1=周一',
  view_cnt       INT                   COMMENT '播放(采集快照)',
  like_cnt       INT,
  coin_cnt       INT                   COMMENT '投币(搜索接口缺失,见报告已知局限)',
  fav_cnt        INT                   COMMENT '收藏',
  danmaku_cnt    INT                   COMMENT '弹幕数',
  reply_cnt      INT                   COMMENT '评论数',
  share_cnt      INT                   COMMENT '分享(搜索接口缺失)',
  is_duration_outlier TINYINT DEFAULT 0 COMMENT '时长异常标记:1=疑似直播回放/合集(不删,只打标)',
  source_keyword VARCHAR(64)           COMMENT '通过哪个关键词/接口采到',
  crawled_at     DATETIME              COMMENT '采集时间',
  INDEX idx_zone (zone, sub_zone),
  INDEX idx_pub  (pub_time),
  INDEX idx_mid  (mid),
  INDEX idx_view (view_cnt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='视频表(快照)';

-- 弹幕表（第10周用，先建好）----------------------------------
CREATE TABLE IF NOT EXISTS danmaku (
  dmid           BIGINT       PRIMARY KEY COMMENT '弹幕ID',
  cid            BIGINT                COMMENT '视频cid(=弹幕池id)',
  bvid           VARCHAR(20)           COMMENT 'BV号',
  content        VARCHAR(200)          COMMENT '弹幕内容',
  send_time_sec  INT                   COMMENT '出现在视频第几秒',
  mode           TINYINT               COMMENT '弹幕类型',
  font_size      TINYINT,
  color          INT,
  ctime          DATETIME              COMMENT '发送时间',
  dup_count      INT DEFAULT 1         COMMENT '同文本出现次数=刷屏强度',
  sentiment      TINYINT               COMMENT '情感:1正 0中 -1负(分析后回填)',
  topic_cluster  INT                   COMMENT '聚类主题编号(分析后回填)',
  INDEX idx_bvid (bvid),
  INDEX idx_cid  (cid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='弹幕表(按文本去重并保留次数)';

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一配置入口：读 config.yaml + .env。

所有模块都从这里拿配置，别在代码里硬编码关键词/密码/上限。
（面试可讲的专业习惯：配置与代码分离、密钥不进仓库）
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

# Windows 控制台默认 GBK，中文会乱码 —— 强制 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    """读 .env 到环境变量。装了 python-dotenv 就用它，没装也能退化运行。"""
    env = ROOT / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
        return
    except ImportError:
        pass
    if env.exists():                                # 简易兜底解析
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


@lru_cache(maxsize=1)
def load_config() -> dict:
    """读取并展开 config.yaml 中的 ${ENV_VAR} 占位符。"""
    import yaml

    _load_env()
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    def expand(v):
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.getenv(v[2:-1], "")
        if isinstance(v, dict):
            return {k: expand(x) for k, x in v.items()}
        if isinstance(v, list):
            return [expand(x) for x in v]
        return v

    return expand(cfg)


def db_url() -> str:
    """SQLAlchemy 连接串。backend=sqlite 时给兜底路径（见 docs/mysql_setup.md 路线 D）。"""
    d = load_config()["database"]
    if d.get("backend") == "sqlite":
        p = ROOT / d.get("sqlite_path", "data/bili.db")
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{p.as_posix()}"
    return (f"mysql+pymysql://{d['user']}:{d['password']}@{d['host']}:{d['port']}"
            f"/{d['name']}?charset={d.get('charset', 'utf8mb4')}")


def path(*parts: str) -> Path:
    """项目内的绝对路径，例如 path('data', 'raw', 'sample.json')。"""
    p = ROOT.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


if __name__ == "__main__":                      # python -m src.config 自检
    c = load_config()
    crawl, db = c["crawl"], c["database"]
    backend = db.get("backend", "mysql")
    print("关键词分组：", {k: len(v) for k, v in crawl["keyword_groups"].items()})
    print("二级分区  ：", "、".join(z["name"] for z in crawl["sub_zone_tids"]))
    print("采集上限  ：", crawl["max_videos"], "视频 /", crawl["max_comments"], "评论",
          "/", crawl["max_danmaku"], "弹幕")
    target = (db.get("sqlite_path", "") if backend == "sqlite"
              else f"{db.get('host') or '(未配置)'}:{db.get('port') or '-'}/{db.get('name') or '-'}")
    print("数据库    ：", backend, "→", target)
    url = db_url()
    if db.get("password"):                              # 别把密码打到终端/日志里
        url = url.replace(db["password"], "***")
    print("DB URL    ：", url)
    if backend == "mysql" and not db.get("host"):
        print("\n提示：数据库配置为空 → copy .env.example .env 并填账号密码（见 docs/mysql_setup.md）。")

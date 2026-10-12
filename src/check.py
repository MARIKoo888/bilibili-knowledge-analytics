#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检 —— 第6周周三任务的第一步：先确认机器能跑，再写代码。

用法：
    python src/check.py          （或 python -m src.check）

它检查 5 件事：Python 版本 / 依赖包 / 目录可写 / .env 与 MySQL 连接 / 中文字体。
全绿之后再动手写采集代码；红的先按提示修，别带着问题往下走（后面会更难定位）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文会乱码 —— 强制 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]

PKGS = [
    ("requests", "网络请求 / 采集"),
    ("bs4", "BeautifulSoup 页面解析"),
    ("pandas", "数据处理"),
    ("numpy", "数值计算"),
    ("sqlalchemy", "数据库 ORM"),
    ("pymysql", "MySQL 驱动"),
    ("yaml", "读 config.yaml"),
    ("dotenv", "读 .env"),
    ("jieba", "中文分词"),
    ("wordcloud", "词云"),
    ("sklearn", "机器学习"),
    ("matplotlib", "绘图"),
    ("seaborn", "统计绘图"),
    ("snownlp", "情感分析基线"),
    ("streamlit", "交互看板"),
    ("openpyxl", "Excel 读写"),
]

DIRS = ["data/raw", "data/processed", "figures", "logs", "reports",
        "notebooks", "app", "sql", "docs", "src/spider", "src/analyze",
        "src/nlp", "src/recsys", "src/llm"]

rows: list[tuple[str, str, str]] = []          # (状态, 检查项, 说明)


def add(ok: bool, item: str, detail: str = "", warn: bool = False) -> None:
    rows.append(("WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"), item, detail))


def check_python() -> None:
    v = sys.version_info
    add(v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro}", "需要 >= 3.10")
    enc = (sys.stdout.encoding or "").lower()
    add("utf" in enc, f"控制台编码 {sys.stdout.encoding}", "建议 UTF-8，否则中文输出/词云易乱码", warn=True)


def check_pkgs() -> None:
    missing = []
    for mod, desc in PKGS:
        spec = importlib.util.find_spec(mod)
        ok = spec is not None
        add(ok, f"依赖 {mod}", desc)
        if not ok:
            missing.append(mod)
    if missing:
        print("\n缺少依赖，先执行：\n  pip install -r requirements.txt")
        print("（只缺个别的可用：pip install " + " ".join(
            {"bs4": "beautifulsoup4", "sklearn": "scikit-learn", "yaml": "PyYAML",
             "dotenv": "python-dotenv"}.get(m, m) for m in missing) + "）")


def check_dirs() -> None:
    for d in DIRS:
        p = ROOT / d
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            add(True, f"目录 {d}", "可写")
        except Exception as e:                                  # noqa: BLE001
            add(False, f"目录 {d}", f"{type(e).__name__}: {e}")


def _db_backend() -> str:
    """读 config.yaml 的 database.backend（不依赖 .env，纯文件读取）。"""
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
        return (cfg.get("database") or {}).get("backend", "mysql")
    except Exception:                                            # noqa: BLE001
        return "mysql"


def check_env_and_db() -> None:
    if _db_backend() == "sqlite":
        import sqlite3
        db = ROOT / "data" / "bili.db"
        try:
            db.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(db)
            ver = con.execute("select sqlite_version()").fetchone()[0]
            con.close()
            add(True, "SQLite 连接", f"版本 {ver} → {db.name}")
            add(False, "数据库后端", "当前是 sqlite 兜底模式 → 装好 MySQL 后把 config.yaml 改回 backend: mysql"
                                     "（简历和 JD 都要 MySQL）", warn=True)
        except Exception as e:                                   # noqa: BLE001
            add(False, "SQLite 连接", f"{type(e).__name__}: {e}")
        return

    env = ROOT / ".env"
    if not env.exists():
        add(False, ".env 配置文件", "没有 .env：copy .env.example .env 后填数据库密码（见 docs/mysql_setup.md）",
            warn=True)
        return
    add(True, ".env 配置文件", "存在")
    try:
        from dotenv import dotenv_values
    except ImportError:
        return
    cfg = {k: v for k, v in dotenv_values(env).items() if v}
    need = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    lost = [k for k in need if not cfg.get(k)]
    if lost:
        add(False, ".env 字段完整性", "缺少：" + ", ".join(lost), warn=True)
        return
    add(True, ".env 字段完整性", "5 个字段齐全")
    try:
        import pymysql
        conn = pymysql.connect(host=cfg["DB_HOST"], port=int(cfg["DB_PORT"]),
                               user=cfg["DB_USER"], password=cfg["DB_PASSWORD"],
                               charset="utf8mb4", connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
            cur.execute("SHOW DATABASES LIKE %s", (cfg["DB_NAME"],))
            has_db = cur.fetchone() is not None
        conn.close()
        add(True, "MySQL 连接", f"版本 {ver}")
        add(has_db, f"数据库 {cfg['DB_NAME']}",
            "已存在" if has_db else "不存在 → CREATE DATABASE bili DEFAULT CHARSET utf8mb4;")
    except Exception as e:                                       # noqa: BLE001
        add(False, "MySQL 连接", f"{type(e).__name__}: {e}")


def check_font() -> None:
    try:
        from matplotlib import font_manager
    except ImportError:
        return
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC"):
        if cand in names:
            add(True, "中文字体", f"找到 {cand} → 画图前设 rcParams['font.sans-serif']")
            return
    add(False, "中文字体", "没找到中文字体，图表中文会变方块", warn=True)


def main() -> int:
    print("=" * 62)
    print(f"环境自检  root={ROOT}")
    print("=" * 62)
    check_python()
    check_env_and_db()
    check_font()
    check_dirs()
    check_pkgs()

    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]"}
    width = max(len(r[1]) for r in rows) if rows else 10
    fails = [r for r in rows if r[0] == "FAIL"]
    warns = [r for r in rows if r[0] == "WARN"]
    passes = [r for r in rows if r[0] == "PASS"]
    for st, item, detail in fails + warns:
        print(f"{icon[st]} {item.ljust(width)}  {detail}")
    if not fails and not warns:
        print("全部通过 ✅")
    print("-" * 62)
    print(f"通过 {len(passes)} / 警告 {len(warns)} / 失败 {len(fails)}")
    if fails:
        print("\n下一步：按上面的 FAIL 逐条修（依赖 → `pip install -r requirements.txt`；"
              "数据库 → 建库并填 .env），修完重跑本脚本。")
    else:
        print("\n下一步（第6周周三）：跑通一次 B站公开接口调用并落盘 data/raw/sample.json。"
              "卡住超过 90 分钟 → 看 reference/wbi_sign_reference.py。")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""跑 .sql 文件的小工具（读文件 -> 执行 -> 打印结果）

用法：
    $env:PYTHONUTF8=1
    .\\.venv\\Scripts\\python.exe -m src.run_sql sql/01_zone_supply_demand.sql

为什么要有它：
  - 不用每次手打一长串 mysql 命令
  - 结果自动对齐成表格，一眼能看懂
  - 报错会告诉你"第几条语句挂了"，比裸 mysql 友好
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import db_url  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 100)


def split_sql(sql: str) -> list[str]:
    """按分号切语句，去掉纯注释块和空语句。"""
    # 先去掉整行注释，避免注释里的分号干扰
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    body = "\n".join(lines)

    stmts = []
    for raw in body.split(";"):
        s = raw.strip()
        if s:
            stmts.append(s)
    return stmts


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m src.run_sql <sql文件路径>")
        return 2

    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"[error] 文件不存在: {path}")
        return 2

    stmts = split_sql(path.read_text(encoding="utf-8"))
    print(f"[run] {path.name} 共 {len(stmts)} 条语句\n")

    engine = create_engine(db_url(), pool_pre_ping=True)
    ok = 0
    for i, s in enumerate(stmts, 1):
        head = " ".join(s.split())[:80]
        print(f"--- 语句 {i} ---")
        print(f"    {head}{'...' if len(s) > 80 else ''}")
        try:
            with engine.connect() as conn:
                res = conn.execute(text(s))
                if res.returns_rows:
                    df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
                    print(df.to_string(index=False))
                    print(f"    （{len(df)} 行）")
                else:
                    print("    OK（无返回行）")
            ok += 1
        except Exception as e:
            print(f"    [FAIL] {type(e).__name__}: {str(e)[:300]}")
            print(f"    >>> 第 {i} 条语句失败，后面停止执行")
            return 1
        print()

    print(f"[done] {ok}/{len(stmts)} 条语句执行成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

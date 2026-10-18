#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ORM 模型(app/orm.py)中的表/列/约束注释同步到数据库。

幂等,可重复执行;不动数据,只发 COMMENT ON 语句。
新建库无需执行(create_all 建表时自动带注释);对已存在的库补注释或改注释时执行。

用法:
  cd backend && .venv/bin/python scripts/apply_comments.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app import orm  # noqa: E402,F401  注册全部表定义
from app.db import Base, engine  # noqa: E402


def lit(value: str) -> str:
    """SQL 字符串字面量转义。"""
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    statements: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.comment:
            statements.append(f"COMMENT ON TABLE {table.name} IS {lit(table.comment)}")
        for col in table.columns:
            if col.comment:
                statements.append(f"COMMENT ON COLUMN {table.name}.{col.name} IS {lit(col.comment)}")
        for cons in table.constraints:
            if cons.name and getattr(cons, "comment", None):
                statements.append(
                    f"COMMENT ON CONSTRAINT {cons.name} ON {table.name} IS {lit(cons.comment)}"
                )

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
    print(f"已同步 {len(statements)} 条注释到数据库")


if __name__ == "__main__":
    main()

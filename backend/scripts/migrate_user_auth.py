#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 users 表补充用户名/密码列(存量库迁移,幂等)。

新库无需执行(create_all 按 orm.py 直接建全)。
用法: cd backend && .venv/bin/python scripts/migrate_user_auth.py
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402

DDL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
    "COMMENT ON TABLE users IS '用户表(用户名+密码注册;openid 为第三方登录预留)'",
    "COMMENT ON COLUMN users.username IS '用户名(3-32位字母/数字/下划线)'",
    "COMMENT ON COLUMN users.password_hash IS '密码哈希(PBKDF2-SHA256 含盐)'",
]


def main() -> None:
    with engine.begin() as conn:
        for sql in DDL:
            conn.execute(text(sql))
    print("users 表迁移完成(新增 username/password_hash 列与唯一索引)")


if __name__ == "__main__":
    main()

"""SQLAlchemy 引擎与会话(同步模式,psycopg2)。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def db_ready() -> bool:
    """快速探测数据库连通性(用于优雅降级)。"""
    try:
        with engine.connect():
            return True
    except Exception:
        return False

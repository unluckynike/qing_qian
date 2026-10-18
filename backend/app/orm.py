"""ORM 表定义:users / drawings / readings / messages。

签文库(100 签)不进库:JSON 文件为唯一数据源,drawings.sign_no 直接引用 1-100。
表/列注释随 create_all 建表时自动写入;对已存在的库执行 scripts/apply_comments.py 同步。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "用户表(登录体系二期启用;当前匿名模式不写入)"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键")
    openid: Mapped[str | None] = mapped_column(
        String(64), unique=True, comment="第三方登录标识(openid,预留)"
    )
    nickname: Mapped[str | None] = mapped_column(String(64), comment="昵称")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )


class Drawing(Base):
    """一次抽签。"""

    __tablename__ = "drawings"
    __table_args__ = (
        CheckConstraint("sign_no BETWEEN 1 AND 100", name="ck_drawings_sign_no", comment="签号取值 1-100"),
        {"comment": "抽签记录(每次摇签一条)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), comment="关联用户;匿名抽签时为 NULL"
    )
    sign_no: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="签号 1-100,对应签文库 JSON 的 no 字段"
    )
    category: Mapped[str | None] = mapped_column(
        String(16), comment="所问分类(事业/姻缘/财运/健康/其他)"
    )
    question: Mapped[str | None] = mapped_column(Text, comment="所问之事(≤100 字)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="抽签时间"
    )


class Reading(Base):
    """一次 AI 详批(首答)。"""

    __tablename__ = "readings"
    __table_args__ = {"comment": "AI 解签记录(每签首答一条)"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键")
    drawing_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联抽签记录(drawings.id)",
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False, comment="使用的模型标识(如 glm-4-flash)")
    prompt_version: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="提示词版本(解签口径追溯,见 prompt.py)"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="完整解签文本")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="生成时间"
    )


class Message(Base):
    """解签后的追问对话。"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_messages_role", comment="角色仅限 user/assistant"),
        {"comment": "解签追问对话(一次追问写入 user 与 assistant 各一条)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键")
    reading_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("readings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联解签记录(readings.id)",
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="角色:user=求签人 / assistant=解签师傅"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="时间"
    )


class Setting(Base):
    """系统配置(键值对,后台管理页维护;AI 配置优先于 .env)。"""

    __tablename__ = "settings"
    __table_args__ = {"comment": "系统配置(键值对;后台管理页维护,优先于 .env)"}

    key: Mapped[str] = mapped_column(String(64), primary_key=True, comment="配置键(如 llm_api_key)")
    value: Mapped[str | None] = mapped_column(Text, comment="配置值(字符串;温度/上限按数字解析)")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="最后修改时间"
    )

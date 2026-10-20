"""用户注册 / 登录 / 当前用户信息。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import SessionLocal, db_ready
from ..orm import User
from ..services.user_auth import (
    create_user_token,
    current_user_optional,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=24)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


def _need_db() -> None:
    if not db_ready():
        raise HTTPException(status_code=503, detail="数据库不可用,请稍后再试")


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname or u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.post("/register")
def register(body: RegisterBody) -> dict:
    _need_db()
    with SessionLocal() as db:
        exists = db.query(User).filter(User.username == body.username).first()
        if exists:
            raise HTTPException(status_code=409, detail="用户名已被注册")
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            nickname=(body.nickname or "").strip() or body.username,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token, exp = create_user_token(user.id)
        logger.info("新用户注册: %s (id=%s)", user.username, user.id)
        return {"token": token, "expires_at": exp, "user": _user_out(user)}


@router.post("/login")
def login(body: LoginBody) -> dict:
    _need_db()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == body.username).first()
        if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token, exp = create_user_token(user.id)
        return {"token": token, "expires_at": exp, "user": _user_out(user)}


@router.get("/me")
def me(user: User | None = Depends(current_user_optional)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return {"user": _user_out(user)}

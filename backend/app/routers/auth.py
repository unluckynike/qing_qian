"""用户注册 / 登录 / 当前用户信息。

统一登录入口 POST /auth/login:自动识别账号类型 ——
先校验管理员(.env 单账号),失败再查普通用户表;返回 role 区分身份。
登录与注册事件(含失败尝试)写入 login_logs,供后台"登录日志"页查看。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings
from ..db import SessionLocal, db_ready
from ..orm import LoginLog, User
from ..services.admin_auth import check_credentials, create_admin_token
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


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else None)


def _write_log(
    request: Request, username: str, role: str, action: str, success: bool, reason: str | None
) -> None:
    """best-effort 写入登录日志,失败不影响主流程。"""
    try:
        if not db_ready():
            return
        with SessionLocal() as db:
            db.add(
                LoginLog(
                    username=username[:32],
                    role=role,
                    action=action,
                    success=success,
                    reason=reason,
                    ip=_client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:256] or None,
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("写登录日志失败: %s", exc)


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname or u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.post("/register")
def register(body: RegisterBody, request: Request) -> dict:
    _need_db()
    username = body.username
    if settings.admin_password.strip() and username.lower() == settings.admin_username.lower():
        raise HTTPException(status_code=409, detail="该用户名为系统保留")
    with SessionLocal() as db:
        exists = db.query(User).filter(User.username == username).first()
        if exists:
            raise HTTPException(status_code=409, detail="用户名已被注册")
        user = User(
            username=username,
            password_hash=hash_password(body.password),
            nickname=(body.nickname or "").strip() or username,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token, exp = create_user_token(user.id)
        logger.info("新用户注册: %s (id=%s)", user.username, user.id)
        result = {"role": "user", "token": token, "expires_at": exp, "user": _user_out(user)}
    _write_log(request, username, "user", "register", True, None)
    return result


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict:
    _need_db()

    # 1) 管理员优先(.env 单账号,与用户表完全独立)
    if check_credentials(body.username, body.password):
        token, exp = create_admin_token()
        _write_log(request, body.username, "admin", "login", True, None)
        return {"role": "admin", "token": token, "expires_at": exp}

    # 2) 普通用户
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == body.username).first()
        if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
            _write_log(request, body.username, "user", "login", False, "用户名或密码错误")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        if not user.is_active:
            _write_log(request, body.username, "user", "login", False, "账号已禁用")
            raise HTTPException(status_code=403, detail="账号已被禁用,请联系管理员")
        token, exp = create_user_token(user.id)
        _write_log(request, body.username, "user", "login", True, None)
        return {"role": "user", "token": token, "expires_at": exp, "user": _user_out(user)}


@router.get("/me")
def me(user: User | None = Depends(current_user_optional)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return {"user": _user_out(user)}

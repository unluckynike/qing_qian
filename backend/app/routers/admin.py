"""后台管理:登录、概览、签文记录、用户管理、AI 配置。

鉴权:单管理员账号(.env 的 ADMIN_USERNAME/ADMIN_PASSWORD),
登录换取 HMAC 签名令牌(有效期 ADMIN_TOKEN_HOURS),Bearer 方式调用其余接口。
"""
import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..config import settings
from ..db import SessionLocal, db_ready
from ..orm import Drawing, Message, Reading, User
from ..services import llm
from ..services.ai_config import get_ai_config, mask_key, set_ai_config
from ..services.signstore import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- 鉴权 ----------
def _admin_ready() -> bool:
    return bool(settings.admin_password.strip())


def _secret() -> bytes:
    # 密码变更即自动使旧令牌失效
    return f"{settings.admin_username}:{settings.admin_password}".encode()


def _create_token() -> tuple[str, int]:
    exp = int(time.time()) + settings.admin_token_hours * 3600
    payload = (
        base64.urlsafe_b64encode(json.dumps({"u": settings.admin_username, "exp": exp}).encode())
        .decode()
        .rstrip("=")
    )
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", exp


def _verify_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
        expect = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(data.get("exp", 0)) > time.time()
    except Exception:  # noqa: BLE001 任何解析异常都视为无效令牌
        return False


def require_admin(authorization: str | None = Header(default=None)) -> str:
    if not _admin_ready():
        raise HTTPException(status_code=503, detail="后台未启用:请在 backend/.env 配置 ADMIN_PASSWORD")
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or not _verify_token(token):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return token


def _need_db() -> None:
    if not db_ready():
        raise HTTPException(status_code=503, detail="数据库不可用")


# ---------- 请求模型 ----------
class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class SettingsBody(BaseModel):
    llm_api_base: str | None = Field(default=None, max_length=256)
    llm_api_key: str | None = Field(default=None, max_length=256)
    llm_model: str | None = Field(default=None, max_length=64)
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_max_tokens: int | None = Field(default=None, ge=16, le=8192)


# ---------- 登录 ----------
@router.post("/login")
def login(body: LoginBody) -> dict:
    if not _admin_ready():
        raise HTTPException(status_code=503, detail="后台未启用:请在 backend/.env 配置 ADMIN_PASSWORD")
    ok_user = hmac.compare_digest(body.username, settings.admin_username)
    ok_pass = hmac.compare_digest(body.password, settings.admin_password)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, exp = _create_token()
    return {"token": token, "expires_at": exp, "username": settings.admin_username}


# ---------- 概览 ----------
@router.get("/overview", dependencies=[Depends(require_admin)])
def overview() -> dict:
    _need_db()
    with SessionLocal() as db:
        drawings = db.scalar(select(func.count()).select_from(Drawing)) or 0
        readings = db.scalar(select(func.count()).select_from(Reading)) or 0
        messages = db.scalar(select(func.count()).select_from(Message)) or 0
        users = db.scalar(select(func.count()).select_from(User)) or 0
        today = db.scalar(
            select(func.count()).select_from(Drawing).where(func.date(Drawing.created_at) == func.current_date())
        ) or 0
    cfg = get_ai_config()
    return {
        "drawings": drawings,
        "readings": readings,
        "messages": messages,
        "users": users,
        "drawings_today": today,
        "ai": {
            "configured": bool(cfg["llm_api_key"].strip()),
            "model": cfg["llm_model"],
            "api_base": cfg["llm_api_base"],
        },
    }


# ---------- 签文记录 ----------
@router.get("/drawings", dependencies=[Depends(require_admin)])
def list_drawings(limit: int = 20, offset: int = 0) -> dict:
    _need_db()
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(Drawing)) or 0
        rows = db.scalars(select(Drawing).order_by(Drawing.id.desc()).limit(limit).offset(offset)).all()
        items = []
        for d in rows:
            reading = db.scalars(
                select(Reading).where(Reading.drawing_id == d.id).order_by(Reading.id.desc()).limit(1)
            ).first()
            msg_count = (
                db.scalar(
                    select(func.count())
                    .select_from(Message)
                    .join(Reading, Reading.id == Message.reading_id)
                    .where(Reading.drawing_id == d.id)
                )
                or 0
            )
            sign = store.get(d.sign_no) or {}
            items.append(
                {
                    "drawing_id": d.id,
                    "sign_no": d.sign_no,
                    "title": sign.get("title", ""),
                    "category": d.category,
                    "question": d.question,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "reading_id": reading.id if reading else None,
                    "reading_model": reading.model if reading else None,
                    "excerpt": (reading.content[:100] if reading else None),
                    "messages": msg_count,
                }
            )
    return {"total": total, "items": items}


@router.delete("/drawings/{drawing_id}", dependencies=[Depends(require_admin)])
def delete_drawing(drawing_id: int) -> dict:
    _need_db()
    with SessionLocal() as db:
        row = db.get(Drawing, drawing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        db.delete(row)  # readings/messages 级联删除
        db.commit()
    return {"ok": True}


# ---------- 用户管理 ----------
@router.get("/users", dependencies=[Depends(require_admin)])
def list_users() -> dict:
    _need_db()
    with SessionLocal() as db:
        rows = db.scalars(select(User).order_by(User.id.desc()).limit(200)).all()
        items = []
        for u in rows:
            cnt = db.scalar(select(func.count()).select_from(Drawing).where(Drawing.user_id == u.id)) or 0
            items.append(
                {
                    "id": u.id,
                    "openid": u.openid,
                    "nickname": u.nickname,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "drawings": cnt,
                }
            )
    return {"items": items}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: int) -> dict:
    _need_db()
    with SessionLocal() as db:
        row = db.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        db.delete(row)  # drawings.user_id 外键为 SET NULL,历史记录保留
        db.commit()
    return {"ok": True}


# ---------- AI 配置 ----------
@router.get("/settings", dependencies=[Depends(require_admin)])
def read_settings() -> dict:
    cfg = get_ai_config()
    key = cfg["llm_api_key"].strip()
    return {
        "llm_api_base": cfg["llm_api_base"],
        "llm_model": cfg["llm_model"],
        "llm_temperature": cfg["llm_temperature"],
        "llm_max_tokens": cfg["llm_max_tokens"],
        "llm_api_key_set": bool(key),
        "llm_api_key_masked": mask_key(key),
    }


@router.put("/settings", dependencies=[Depends(require_admin)])
def update_settings(body: SettingsBody) -> dict:
    values = body.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status_code=400, detail="未提供任何配置项")
    try:
        set_ai_config(values)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("后台更新 AI 配置: %s", sorted(values.keys()))
    return read_settings()


@router.post("/settings/test", dependencies=[Depends(require_admin)])
def test_settings() -> dict:
    try:
        return llm.test_connection()
    except llm.LLMNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 上游模型服务报错原样透出(不含密钥)
        raise HTTPException(status_code=400, detail=f"连接测试失败:{exc}") from exc

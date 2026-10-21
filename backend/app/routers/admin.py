"""后台管理:概览、签文记录、用户管理、AI 配置。

鉴权见 services/admin_auth(单管理员账号 + HMAC 签名令牌,与普通用户体系独立)。
登录走统一入口 POST /api/auth/login(自动识别账号类型)。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..db import SessionLocal, db_ready
from ..orm import Drawing, LoginLog, Message, Reading, User
from ..services import llm
from ..services.admin_auth import check_credentials, create_admin_token, require_admin
from ..services.ai_config import get_ai_config, mask_key, set_ai_config
from ..services.signstore import store
from ..services.user_auth import hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


def _need_db() -> None:
    if not db_ready():
        raise HTTPException(status_code=503, detail="数据库不可用")


# ---------- 请求模型 ----------
class SettingsBody(BaseModel):
    llm_api_base: str | None = Field(default=None, max_length=256)
    llm_api_key: str | None = Field(default=None, max_length=256)
    llm_model: str | None = Field(default=None, max_length=64)
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_max_tokens: int | None = Field(default=None, ge=16, le=8192)
    llm_thinking: str | None = Field(default=None, max_length=16, description='""=默认,"disabled"=关闭思考')


class ResetPasswordBody(BaseModel):
    password: str = Field(min_length=6, max_length=64, description="新密码(≥6 位)")


class UserStatusBody(BaseModel):
    is_active: bool


# ---------- 登录(兼容保留;新统一入口为 /api/auth/login) ----------
@router.post("/login")
def login(body: LoginBody) -> dict:
    if not check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, exp = create_admin_token()
    return {"role": "admin", "token": token, "expires_at": exp}


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
def list_users(q: str | None = None) -> dict:
    """用户列表(可按用户名/昵称模糊搜索),含抽签数与最近抽签时间。"""
    _need_db()
    with SessionLocal() as db:
        stmt = select(User)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(User.username.ilike(like), User.nickname.ilike(like)))
        rows = db.scalars(stmt.order_by(User.id.desc()).limit(200)).all()
        items = []
        for u in rows:
            cnt = db.scalar(select(func.count()).select_from(Drawing).where(Drawing.user_id == u.id)) or 0
            last = db.scalar(select(func.max(Drawing.created_at)).where(Drawing.user_id == u.id))
            items.append(
                {
                    "id": u.id,
                    "username": u.username,
                    "nickname": u.nickname,
                    "is_active": u.is_active,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "drawings": cnt,
                    "last_drawing_at": last.isoformat() if last else None,
                }
            )
    return {"items": items}


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_admin)])
def reset_user_password(user_id: int, body: ResetPasswordBody) -> dict:
    _need_db()
    with SessionLocal() as db:
        row = db.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        row.password_hash = hash_password(body.password)
        db.commit()
    logger.info("管理员重置用户密码: user_id=%s", user_id)
    return {"ok": True}


@router.patch("/users/{user_id}/status", dependencies=[Depends(require_admin)])
def set_user_status(user_id: int, body: UserStatusBody) -> dict:
    _need_db()
    with SessionLocal() as db:
        row = db.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        row.is_active = body.is_active
        db.commit()
    logger.info("管理员%s用户: user_id=%s", "启用" if body.is_active else "禁用", user_id)
    return {"ok": True, "is_active": body.is_active}


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


# ---------- 登录日志 ----------
@router.get("/login-logs", dependencies=[Depends(require_admin)])
def list_login_logs(limit: int = 50, offset: int = 0, only_failed: bool = False) -> dict:
    """登录/注册事件日志(倒序分页;only_failed 只看失败尝试)。"""
    _need_db()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with SessionLocal() as db:
        stmt = select(LoginLog)
        if only_failed:
            stmt = stmt.where(LoginLog.success.is_(False))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(LoginLog.id.desc()).limit(limit).offset(offset)).all()
        items = [
            {
                "id": r.id,
                "username": r.username,
                "role": r.role,
                "action": r.action,
                "success": r.success,
                "reason": r.reason,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    return {"total": total, "items": items}


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
        "llm_thinking": cfg.get("llm_thinking", ""),
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

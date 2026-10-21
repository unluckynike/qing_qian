"""用户注册/登录与会话令牌(仅标准库实现,无额外依赖)。

- 密码:PBKDF2-SHA256 加盐哈希(12 万次迭代)
- 会话:HMAC-SHA256 签名令牌(含过期时间),Bearer 方式携带
- 与后台管理员令牌相互独立(不同密钥与载荷类型)
"""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from ..config import settings
from ..db import SessionLocal, db_ready
from ..orm import User

ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:  # noqa: BLE001 任何格式异常均视为校验失败
        return False


def _secret() -> bytes:
    return settings.user_secret.encode()


def create_user_token(user_id: int) -> tuple[str, int]:
    exp = int(time.time()) + settings.user_token_days * 86400
    payload = (
        base64.urlsafe_b64encode(json.dumps({"uid": user_id, "exp": exp, "typ": "user"}).encode())
        .decode()
        .rstrip("=")
    )
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", exp


def _parse_token(token: str) -> int | None:
    try:
        payload, sig = token.split(".", 1)
        expect = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data.get("typ") != "user" or float(data.get("exp", 0)) <= time.time():
            return None
        return int(data["uid"])
    except Exception:  # noqa: BLE001
        return None


def current_user_optional(authorization: str | None = Header(default=None)) -> User | None:
    """可选登录:带有效用户令牌则返回用户,否则 None(不抛错)。被禁用的账号视为未登录。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    if not db_ready():
        return None
    uid = _parse_token(authorization[7:].strip())
    if uid is None:
        return None
    with SessionLocal() as db:
        user = db.get(User, uid)
        if user is not None and not user.is_active:
            return None
        return user


def require_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user

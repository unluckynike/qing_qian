"""后台管理员鉴权(单账号 .env 配置;密钥与载荷独立于普通用户体系)。"""
import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException

from ..config import settings


def admin_ready() -> bool:
    return bool(settings.admin_password.strip())


def _secret() -> bytes:
    # 密码变更即自动使旧令牌失效
    return f"{settings.admin_username}:{settings.admin_password}".encode()


def create_admin_token() -> tuple[str, int]:
    exp = int(time.time()) + settings.admin_token_hours * 3600
    payload = (
        base64.urlsafe_b64encode(json.dumps({"u": settings.admin_username, "exp": exp}).encode())
        .decode()
        .rstrip("=")
    )
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", exp


def verify_admin_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
        expect = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(data.get("exp", 0)) > time.time()
    except Exception:  # noqa: BLE001 任何解析异常都视为无效令牌
        return False


def check_credentials(username: str, password: str) -> bool:
    """账号密码校验(统一登录入口使用)。"""
    if not admin_ready():
        return False
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password, settings.admin_password
    )


def require_admin(authorization: str | None = Header(default=None)) -> str:
    if not admin_ready():
        raise HTTPException(status_code=503, detail="后台未启用:请在 backend/.env 配置 ADMIN_PASSWORD")
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return token

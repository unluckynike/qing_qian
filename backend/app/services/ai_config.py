"""AI 配置动态读取:数据库 settings 表优先,.env 兜底。

后台管理页修改后立即生效(每次调用时读取),无需重启后端。
"""
import logging

from ..config import settings
from ..db import SessionLocal, db_ready
from ..orm import Setting

logger = logging.getLogger(__name__)

AI_FIELDS = ("llm_api_base", "llm_api_key", "llm_model", "llm_temperature", "llm_max_tokens", "llm_thinking")


def get_ai_config() -> dict:
    """有效 AI 配置:DB 覆盖值 > .env 值,并做类型归一。"""
    cfg: dict = {
        "llm_api_base": settings.llm_api_base,
        "llm_api_key": settings.llm_api_key,
        "llm_model": settings.llm_model,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "llm_thinking": settings.llm_thinking,
    }
    if db_ready():
        try:
            with SessionLocal() as db:
                for row in db.query(Setting).filter(Setting.key.in_(AI_FIELDS)).all():
                    if row.value is not None:
                        cfg[row.key] = row.value
        except Exception as exc:  # noqa: BLE001 数据库不可用时静默回退 .env
            logger.warning("读取 settings 表失败,使用 .env 配置: %s", exc)

    try:
        cfg["llm_temperature"] = float(cfg["llm_temperature"])
    except (TypeError, ValueError):
        cfg["llm_temperature"] = 0.8
    try:
        cfg["llm_max_tokens"] = int(cfg["llm_max_tokens"])
    except (TypeError, ValueError):
        cfg["llm_max_tokens"] = 1200
    return cfg


def set_ai_config(values: dict) -> dict:
    """upsert 提供的字段;值传空字符串表示清空该配置(如清空 Key 即关闭 AI 解签)。"""
    if not db_ready():
        raise RuntimeError("数据库不可用,无法保存配置")
    with SessionLocal() as db:
        changed = []
        for key, value in values.items():
            if key not in AI_FIELDS or value is None:
                continue
            row = db.get(Setting, key)
            if row is None:
                db.add(Setting(key=key, value=str(value)))
            else:
                row.value = str(value)
            changed.append(key)
        db.commit()
    logger.info("AI 配置已更新: %s", changed)
    return get_ai_config()


def mask_key(key: str) -> str:
    """密钥脱敏展示:仅保留末 4 位。"""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]

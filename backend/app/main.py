"""青签 · FastAPI 入口。

启动: cd backend && ../ 或 uvicorn app.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import orm  # noqa: F401  确保 ORM 表定义被注册
from .config import settings
from .db import Base, engine
from .routers import admin, divination, signs
from .services import llm
from .services.signstore import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(engine)
        logger.info("数据库就绪(已确保建表)")
    except Exception as exc:  # noqa: BLE001 数据库不可用时不阻塞启动,静态功能不受影响
        logger.warning("数据库不可用,将以无持久化模式运行: %s", exc)
    logger.info("签文库加载完成: %d 签", store.total)
    logger.info("AI 解签: %s", "已配置" if llm.is_configured() else "未配置(仅静态解签)")
    yield


app = FastAPI(title="青签 · 解签 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signs.router, prefix="/api")
app.include_router(divination.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "signs": store.total,
        "llm_configured": llm.is_configured(),
        "db_url": settings.database_url.split("@")[-1],  # 不含凭据
    }


# 生产模式:前端构建产物由后端直接托管(开发时用 vite dev server)
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")

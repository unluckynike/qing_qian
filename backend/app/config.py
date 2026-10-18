"""运行配置:优先读环境变量,其次 backend/.env。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_PATH = BACKEND_DIR / "data" / "lvzu_signs.json"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://qingqian:qingqian_dev@localhost:5432/qingqian"
    llm_api_base: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_api_key: str = ""
    llm_model: str = "glm-4-flash"
    llm_temperature: float = 0.8
    llm_max_tokens: int = 1200
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

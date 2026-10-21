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
    llm_thinking: str = ""  # 推理型模型思考模式:""=跟随模型默认,"disabled"=关闭思考

    # 使用助手知识库(RAG):embedding 模型留空则用关键词检索;配置后重建知识库自动升级向量检索
    embedding_model: str = ""
    kb_top_k: int = 4
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 后台管理(单管理员账号;ADMIN_PASSWORD 为空则后台接口返回 503)
    admin_username: str = "admin"
    admin_password: str = ""
    admin_token_hours: int = 12

    # 普通用户会话(注册/登录;USER_SECRET 用于签名用户令牌,公开部署前务必修改)
    user_secret: str = "qingqian-user-secret-change-me"
    user_token_days: int = 7

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

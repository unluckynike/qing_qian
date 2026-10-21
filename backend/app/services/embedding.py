"""Embedding 向量化服务(pgvector RAG 用;复用 LLM 的 API Key 与 Base URL)。

未配置 embedding 模型、或该模型未在服务商开通时,抛 EmbeddingUnavailable,
知识库检索自动回退关键词模式(见 services/knowledge.py)。
"""
from .ai_config import get_ai_config
from .llm import _client


class EmbeddingUnavailable(RuntimeError):
    pass


def is_configured() -> bool:
    cfg = get_ai_config()
    return bool(str(cfg.get("embedding_model") or "").strip()) and bool(cfg["llm_api_key"].strip())


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化;任何失败统一抛 EmbeddingUnavailable(调用方负责降级)。"""
    cfg = get_ai_config()
    model = str(cfg.get("embedding_model") or "").strip()
    if not model:
        raise EmbeddingUnavailable("未配置 embedding 模型")
    if not cfg["llm_api_key"].strip():
        raise EmbeddingUnavailable("未配置 API Key")
    try:
        resp = _client(cfg).embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]
    except Exception as exc:  # noqa: BLE001 上游错误统一降级
        raise EmbeddingUnavailable(f"embedding 调用失败:{exc}") from exc


def probe() -> dict:
    """连通性探测:返回可用状态与向量维度。"""
    vecs = embed_texts(["连通性测试"])
    return {"ok": True, "dim": len(vecs[0])}

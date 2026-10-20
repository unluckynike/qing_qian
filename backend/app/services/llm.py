"""OpenAI 兼容流式客户端(默认智谱 GLM/火山方舟;配置来自 ai_config 动态读取)。

支持推理型模型:配置 llm_thinking=disabled 时,请求体带 thinking.type=disabled,
跳过思考过程直接输出正文(方舟 deepseek 系列等支持)。
"""
import time
from collections.abc import Iterator

from openai import OpenAI

from .ai_config import get_ai_config


class LLMNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(get_ai_config()["llm_api_key"].strip())


def _client(cfg: dict) -> OpenAI:
    return OpenAI(api_key=cfg["llm_api_key"], base_url=cfg["llm_api_base"], timeout=90.0)


def _extra_body(cfg: dict) -> dict | None:
    """按配置生成附加请求体(目前仅思考模式开关)。"""
    if str(cfg.get("llm_thinking", "")).strip().lower() == "disabled":
        return {"thinking": {"type": "disabled"}}
    return None


def stream_chat(messages: list[dict[str, str]]) -> Iterator[str]:
    """逐段产出模型回复文本(仅 content,推理内容不展示)。未配置 Key 时抛 LLMNotConfigured。"""
    cfg = get_ai_config()
    if not cfg["llm_api_key"].strip():
        raise LLMNotConfigured("未配置 LLM_API_KEY")

    kwargs: dict = {}
    extra = _extra_body(cfg)
    if extra:
        kwargs["extra_body"] = extra

    stream = _client(cfg).chat.completions.create(
        model=cfg["llm_model"],
        messages=messages,  # type: ignore[arg-type]
        temperature=cfg["llm_temperature"],
        max_tokens=cfg["llm_max_tokens"],
        stream=True,
        **kwargs,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        text = getattr(chunk.choices[0].delta, "content", None)
        if text:
            yield text


def test_connection() -> dict:
    """连通性测试:发一条最小请求验证配置。失败抛异常(由路由转成 4xx)。"""
    cfg = get_ai_config()
    if not cfg["llm_api_key"].strip():
        raise LLMNotConfigured("未配置 API Key")

    kwargs: dict = {}
    extra = _extra_body(cfg)
    if extra:
        kwargs["extra_body"] = extra

    started = time.time()
    resp = _client(cfg).chat.completions.create(
        model=cfg["llm_model"],
        messages=[{"role": "user", "content": "回复“OK”两个字母即可"}],
        temperature=0,
        max_tokens=32 if extra else 8,
        **kwargs,
    )
    latency = int((time.time() - started) * 1000)
    reply = (resp.choices[0].message.content or "").strip() if resp.choices else ""
    return {"ok": True, "model": cfg["llm_model"], "latency_ms": latency, "reply": reply[:40]}

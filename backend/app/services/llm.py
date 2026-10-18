"""OpenAI 兼容流式客户端(默认智谱 GLM)。"""
from collections.abc import Iterator

from openai import OpenAI

from ..config import settings


class LLMNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.llm_api_key.strip())


def stream_chat(messages: list[dict[str, str]]) -> Iterator[str]:
    """逐段产出模型回复文本。未配置 Key 时抛 LLMNotConfigured。"""
    if not is_configured():
        raise LLMNotConfigured("未配置 LLM_API_KEY")

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base,
        timeout=90.0,
    )
    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text

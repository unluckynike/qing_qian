"""API 请求/响应模型(Pydantic)。"""
from typing import Literal

from pydantic import BaseModel, Field

QUESTION_MAX = 100


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class DrawRequest(BaseModel):
    category: str | None = Field(default=None, max_length=16)
    question: str | None = Field(default=None, max_length=QUESTION_MAX)


class InterpretRequest(BaseModel):
    sign_no: int = Field(ge=1, le=100)
    question: str | None = Field(default=None, max_length=QUESTION_MAX)
    category: str | None = Field(default=None, max_length=16)
    drawing_id: int | None = Field(default=None, ge=1)
    reading_id: int | None = Field(default=None, ge=1, description="追问时携带首答的 reading_id")
    history: list[ChatMessage] = Field(default_factory=list, max_length=6)

"""求签与 AI 解签:抽签(随机)、SSE 流式解签、历史记录。"""
import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal, db_ready
from ..models import DrawRequest, InterpretRequest
from ..orm import Drawing, Message, Reading
from ..services import llm
from ..services.prompt import PROMPT_VERSION, build_messages
from ..services.signstore import store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["divination"])

# 提示词注入特征词:命中即拒绝
STOP_WORDS = [
    "忽略", "指令", "命令", "无视", "ignore", "instruction", "command",
    "重新开始", "扮演", "开发者模式", "system prompt", "越狱",
]

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _reject_injection(*texts: str | None) -> None:
    for text in texts:
        if not text:
            continue
        low = text.lower()
        hit = next((w for w in STOP_WORDS if w in low), None)
        if hit:
            raise HTTPException(status_code=400, detail=f"所问之事包含不允许的词:{hit}")


@router.post("/draw")
def draw(body: DrawRequest) -> dict:
    """安全随机抽签;可持久化时写入 drawings 记录。"""
    _reject_injection(body.question)
    no = store.random_no()
    sign = store.get(no)

    drawing_id = None
    if db_ready():
        try:
            with SessionLocal() as db:
                row = Drawing(sign_no=no, category=body.category, question=body.question)
                db.add(row)
                db.commit()
                drawing_id = row.id
        except Exception as exc:  # noqa: BLE001 持久化失败不阻塞抽签
            logger.warning("drawing 落库失败: %s", exc)

    return {"drawing_id": drawing_id, "sign": sign}


def _persist(
    body: InterpretRequest, model: str, content: str
) -> dict[str, int]:
    """流式结束后落库:首答写 readings,追问写 messages。返回自身 id 便于前端续聊。"""
    with SessionLocal() as db:
        if body.reading_id:  # 追问
            reading = db.get(Reading, body.reading_id)
            if reading is None:
                raise LookupError(f"reading {body.reading_id} 不存在")
            if body.question:
                db.add(Message(reading_id=reading.id, role="user", content=body.question))
            msg = Message(reading_id=reading.id, role="assistant", content=content)
            db.add(msg)
            db.commit()
            return {"reading_id": reading.id, "message_id": msg.id}

        drawing_id = body.drawing_id
        if not drawing_id:
            row = Drawing(sign_no=body.sign_no, category=body.category, question=body.question)
            db.add(row)
            db.flush()
            drawing_id = row.id
        reading = Reading(
            drawing_id=drawing_id, model=model, prompt_version=PROMPT_VERSION, content=content
        )
        db.add(reading)
        db.commit()
        return {"reading_id": reading.id, "drawing_id": drawing_id}


@router.post("/interpret")
def interpret(body: InterpretRequest) -> StreamingResponse:
    _reject_injection(body.question, *[m.content for m in body.history])

    sign = store.get(body.sign_no)
    if sign is None:
        raise HTTPException(status_code=404, detail=f"第 {body.sign_no} 签不存在")
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI 解签未配置:请在 backend/.env 中填写 LLM_API_KEY(详见 .env.example)",
        )

    messages = build_messages(sign, body.question, body.category, [m.model_dump() for m in body.history])

    def event_stream() -> Iterator[str]:
        chunks: list[str] = []
        try:
            for delta in llm.stream_chat(messages):
                chunks.append(delta)
                yield _sse({"delta": delta})
        except Exception as exc:  # noqa: BLE001 流中错误以事件形式告知前端
            logger.exception("LLM 流式调用失败")
            yield _sse({"error": f"解签服务暂时不可用:{exc}"})
            return

        content = "".join(chunks)
        done: dict[str, Any] = {"done": True, "model": settings.llm_model}
        if db_ready():
            try:
                done.update(_persist(body, settings.llm_model, content))
            except Exception as exc:  # noqa: BLE001 落库失败不影响已生成的解读
                logger.warning("解签落库失败: %s", exc)
        yield _sse(done)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/history")
def history(limit: int = 20) -> dict:
    """最近的抽签与解签记录(本地单人使用场景,暂不区分用户)。"""
    limit = max(1, min(limit, 100))
    if not db_ready():
        raise HTTPException(status_code=503, detail="数据库不可用")
    with SessionLocal() as db:
        drawings = db.scalars(
            select(Drawing).order_by(Drawing.id.desc()).limit(limit)
        ).all()
        items = []
        for d in drawings:
            reading = db.scalars(
                select(Reading).where(Reading.drawing_id == d.id).order_by(Reading.id.desc()).limit(1)
            ).first()
            sign = store.get(d.sign_no) or {}
            items.append(
                {
                    "drawing_id": d.id,
                    "sign_no": d.sign_no,
                    "title": sign.get("title", ""),
                    "category": d.category,
                    "question": d.question,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "reading_id": reading.id if reading else None,
                    "excerpt": (reading.content[:120] if reading else None),
                }
            )
    return {"items": items}

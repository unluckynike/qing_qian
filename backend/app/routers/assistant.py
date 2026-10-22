"""使用助手:基于 docs/ 知识库的站内问答(SSE 流式)。

与解签助手完全分离:独立端点 / 独立系统提示词 / 只答产品使用与吕祖灵签文化背景问题。
检索走 services/knowledge(向量或关键词双引擎自动切换)。
每次问答记入 assistant_logs,支持赞踩反馈(评估质量、驱动文档迭代)。
"""
import json
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..db import SessionLocal, db_ready
from ..models import ChatMessage
from ..orm import AssistantLog, User
from ..services import knowledge, llm
from ..services.user_auth import current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["assistant"])

STOP_WORDS = ["忽略", "指令", "命令", "无视", "ignore", "instruction", "command", "重新开始", "扮演"]
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

SYSTEM_TEMPLATE = """你是「青小签」——青签网站的**使用助手**。你负责回答用户关于本站功能与使用方法,以及吕祖与吕祖灵签文化背景、传统求签礼俗的问题。

铁律:
1. 只依据下方「知识库资料」回答;资料里没有的信息,不要猜测、不要编造功能;
2. 你的职责范围:本站功能与使用方法、账户与数据问题,以及吕祖与吕祖灵签的文化背景、传统求签礼俗;超出的问题(如直接让你解签、算命、问其他产品)礼貌说明职责范围,想解签请引导用户去"求签"页摇签,再用"请师傅解签";
3. 若提问涉及规划中的功能,按资料说明为"规划中",不要承诺上线时间;
4. 语气亲切、简洁,回答一般不超过 200 字,必要时用 1-3 条短点;
5. 直接回答,不要出现"根据知识库/资料显示"等字样;
6. **输出纯文本**,不要使用 Markdown 语法(如 **加粗**、# 标题);需要列表时用「1.」「2.」开头即可。

知识库资料:
{context}
"""


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    history: list[ChatMessage] = Field(default_factory=list, max_length=4)


class FeedbackBody(BaseModel):
    log_id: int = Field(ge=1)
    feedback: int = Field(description="1=赞 / -1=踩")


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(body: AskBody, user: User | None = Depends(current_user_optional)) -> StreamingResponse:
    question = body.question.strip()
    low = question.lower()
    hit = next((w for w in STOP_WORDS if w in low), None)
    if hit:
        raise HTTPException(status_code=400, detail=f"问题包含不允许的词:{hit}")
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail="AI 服务未配置,使用助手暂不可用")
    uid = user.id if user else None

    result = knowledge.search(question)
    if result["mode"] == "empty":
        raise HTTPException(
            status_code=503,
            detail="知识库尚未构建:管理员可在后台「AI 配置」页点击「重建知识库」",
        )

    items = result["items"][:4]
    context = "\n\n---\n\n".join(
        f"【{it['doc_path']} · {it['section']}】\n{it['content']}" for it in items
    )
    messages = (
        [{"role": "system", "content": SYSTEM_TEMPLATE.format(context=context)}]
        + [m.model_dump() for m in body.history]
        + [{"role": "user", "content": question}]
    )
    sources, seen = [], set()
    for it in items:
        key = (it["doc_path"], it["section"])
        if key not in seen:
            seen.add(key)
            sources.append({"doc": it["doc_path"], "section": it["section"]})

    def event_stream() -> Iterator[str]:
        parts: list[str] = []
        try:
            for delta in llm.stream_chat(messages):
                parts.append(delta)
                yield _sse({"delta": delta})
        except Exception as exc:  # noqa: BLE001 流中错误告知前端
            logger.exception("使用助手回答失败")
            yield _sse({"error": f"助手暂时不可用:{exc}"})
            return

        log_id = None
        if db_ready():
            try:
                with SessionLocal() as db:
                    row = AssistantLog(
                        user_id=uid,
                        question=question,
                        answer="".join(parts),
                        mode=result["mode"],
                        sources=json.dumps(sources, ensure_ascii=False),
                    )
                    db.add(row)
                    db.commit()
                    log_id = row.id
            except Exception as exc:  # noqa: BLE001 落库失败不影响已生成的回答
                logger.warning("助手问答落库失败: %s", exc)
        yield _sse({"done": True, "mode": result["mode"], "sources": sources, "log_id": log_id})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/feedback")
def feedback(body: FeedbackBody) -> dict:
    """对某条助手回答点赞/点踩(可改;匿名记录也允许评价)。"""
    if body.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback 只能是 1(赞)或 -1(踩)")
    if not db_ready():
        raise HTTPException(status_code=503, detail="数据库不可用")
    with SessionLocal() as db:
        row = db.get(AssistantLog, body.log_id)
        if row is None:
            raise HTTPException(status_code=404, detail="问答记录不存在")
        row.feedback = body.feedback
        row.feedback_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True, "feedback": body.feedback}

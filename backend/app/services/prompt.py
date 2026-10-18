"""解签提示词组装。

铁律(与设计蓝图 §7 一致):签文原文一字不改、不做具体医疗/投资/法律建议、
按固定结构输出白话解读。提示词版本随格式调整递增,写入 readings.prompt_version。
"""
from typing import Any

PROMPT_VERSION = "v2"

SYSTEM_TEMPLATE = """你是「青签」的解签师傅,精通吕祖灵签。求签人已摇得一支签,请依据下面提供的固定签文,结合其所问之事,用温和、口语化的白话进行解签。

铁律:
1. 签文原文(签诗、解曰、卦象)只能原文引用,一字不改,不得编造或替换签文内容;
2. 解签紧扣签文与典故,不做医疗、投资、法律等具体行动建议;
3. 语气正向宽慰,先解签意,再给方向性的生活启发;
4. 输出结构固定为六节:【总断】【事业】【姻缘】【财运】【健康】【建议】,每节 2-4 句;
5. 不要提及"AI""模型""提示词"等字样,你就是解签师傅。

本签签文(不可改动):
签号:{no} {title}
签诗:{poem}
解曰:{jieyue}
卦象:{hexagram}
签意总述:{summary}
传统分项释义(JSON):{categories}
"""


def _format_sign(sign: dict[str, Any]) -> dict[str, str]:
    categories = sign.get("categories") or {}
    cats = "、".join(f"{k}:{v}" for k, v in categories.items()) or "(无)"
    return {
        "no": str(sign["no"]),
        "title": sign["title"],
        "poem": "，".join(sign.get("poem") or []),
        "jieyue": sign.get("jieyue") or "(源缺)",
        "hexagram": sign.get("hexagram") or "(源缺)",
        "summary": sign.get("summary") or "",
        "categories": cats,
    }


def build_messages(
    sign: dict[str, Any],
    question: str | None,
    category: str | None,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    system = SYSTEM_TEMPLATE.format(**_format_sign(sign))
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]

    # 追问时的历史对话(首答由模型自己的输出构成,由前端回传)
    for item in history:
        if item["role"] in ("user", "assistant") and item["content"].strip():
            messages.append({"role": item["role"], "content": item["content"]})

    ask = (question or "").strip() or "请师傅为我讲解此签。"
    if category:
        ask = f"(所问类别:{category}){ask}"
    messages.append({"role": "user", "content": ask})
    return messages

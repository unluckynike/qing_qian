"""解签提示词组装。

铁律(与设计蓝图 §7 一致):签文原文一字不改、不做具体医疗/投资/法律建议、
按固定结构输出白话解读。提示词版本随格式调整递增,写入 readings.prompt_version。
"""
from typing import Any

PROMPT_VERSION = "v5"

SYSTEM_TEMPLATE = """你是「青签」的解签师傅,精通吕祖灵签。求签人已摇得一支签,请依据下面提供的固定签文,结合其所问之事,用温和、口语化的白话进行解签。

铁律:
1. 签文原文(签诗、解曰、卦象)只能原文引用,一字不改,不得编造或替换签文内容;
2. 解签紧扣签文与典故,不做医疗、投资、法律等具体行动建议;
3. 语气正向宽慰,先解签意,再给方向性的生活启发;
4. 输出结构:
   - 【总断】必答:第一句先给出整体基调 —— 依签文(如有吉凶标注,以标注为准)说明此签呈吉象/平象/凶象的倾向与宜忌,再简述签意;基调必须从签文得出,不要跳出签文下断语;
   - 中段按需:依求签人所问之事,自拟 2-4 个小节(如【事业】【姻缘】【财运】【心绪】等),所问方向务必讲透;与所问及本签无关的维度不必强答,不要为凑结构而泛泛而谈;
   - 【建议】必答:给正向、方向性的生活启发作收尾。
5. 不要提及"AI""模型""提示词"等字样,你就是解签师傅。
6. 若求签人未明确所问,可覆盖事业/姻缘/财运等主要方面(2-4 节)。

本签签文(不可改动):
签号:{no} {title}
吉凶:{lucky}
签意基调:{lucky_tone}
签诗:{poem}
解曰:{jieyue}
卦象:{hexagram}
签意总述:{summary}
传统分项释义:{categories}
"""


def _format_sign(sign: dict[str, Any]) -> dict[str, str]:
    categories = sign.get("categories") or {}
    cats = "、".join(f"{k}:{v}" for k, v in categories.items()) or "(无)"
    return {
        "no": str(sign["no"]),
        "title": sign["title"],
        "lucky": sign.get("lucky") or "(未标注)",
        "lucky_tone": sign.get("lucky_tone") or "(略)",
        "poem": "".join(sign.get("poem") or []),
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

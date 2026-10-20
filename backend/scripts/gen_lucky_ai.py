#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 100 支签发地"总体基调"(吉凶档 + 一句基调),供签牌徽章与提示词注入。

数据来源策略(诚实标注,见 meta.lucky_source):
  1. 白话文本明确给出等级的签(如"中下之签""大吉之象")→ 直接采用原文等级;
  2. 其余签 → 调用当前 AI 配置(统一口径、temperature=0)归入传统六档;
     明确标注为"AI 归纳",非典籍原文标注。

用法:
  cd backend && .venv/bin/python scripts/gen_lucky_ai.py          # 生成候选(缓存可续跑)
  cd backend && .venv/bin/python scripts/gen_lucky_ai.py --merge  # 写回 data/lvzu_signs.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services.ai_config import get_ai_config  # noqa: E402
from app.services.llm import _client  # noqa: E402

SIGNS_PATH = BACKEND / "data" / "lvzu_signs.json"
CACHE = BACKEND / "scripts" / "_cache" / "lucky_ai.json"

LEVELS = ["上上", "上吉", "中吉", "中平", "中下", "下下"]

# 白话文本中"无条件明确"给出等级的签(已逐条核对原文语境;条件句/否定句不采纳):
#   12/"主大吉也,大吉大利" 27/"先凶后吉之象" 32/"算是中吉之签" 34/"为中下之签"
FORCED = {
    12: "上吉",
    27: "中平",
    32: "中吉",
    34: "中下",
}

SYSTEM = """你是民俗文化研究者,任务是把吕祖灵签的每一支签按传统解签习惯归入六个基调档位之一,并写一句基调速读。

档位口径(严格按此归类,注意档位分布应符合传统习惯:绝大多数签落在中吉/中平/中下):
- 上上: 大吉大利、成事顺遂、庆贺之象(极少数,约 3-5%)
- 上吉: 吉象明显、努力有成,稍有提醒但大势向好(约 10-15%)
- 中吉: 吉中带阻、需条件或时机,总体偏吉;"先难后易""先凶后吉""久困将伸""贵人相助"亦归此档
- 中平: 吉凶相半、平淡顺遂、宜守待时但无明确凶险;务实守成之象(与中吉合占约一半)
- 中下: 明显阻滞、多事难成、需长期忍耐,偏消极,但非凶险警示
- 下下: 凶险警示、诸事不宜强为、防损失(少数,约 5-10%)

只依据给定签文内容判断,不要额外联想。输出严格 JSON:
{"lucky": "六档之一", "tone": "不超过40个字的一句话基调,口语化,面向求签者"}
"""


def sign_prompt(s: dict) -> str:
    cats = "、".join(f"{k}:{v}" for k, v in (s.get("categories") or {}).items())
    return (
        f"签号:{s['no']} {s['title']}\n"
        f"签诗:{''.join(s.get('poem') or [])}\n"
        f"解曰:{s.get('jieyue') or '(源缺)'}\n"
        f"卦象:{s.get('hexagram') or '(源缺)'}\n"
        f"签意总述:{(s.get('summary') or '')[:220]}\n"
        f"分项释义:{cats[:400]}"
    )


def gen_one(client, model: str, s: dict) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": sign_prompt(s)},
        ],
        temperature=0,
        max_tokens=200,
        extra_body={"thinking": {"type": "disabled"}},
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.strip("`").replace("json\n", "", 1)
    # 兜底:模型偶尔会在 JSON 前后带说明文字,提取最外层花括号
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    lucky = str(data.get("lucky", "")).strip()
    if lucky not in LEVELS:
        raise ValueError(f"非法档位: {lucky}")
    return {"lucky": lucky, "tone": str(data.get("tone", "")).strip()[:60], "by": "ai"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="写回 lvzu_signs.json")
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    payload = json.loads(SIGNS_PATH.read_text(encoding="utf-8"))
    signs = payload["signs"]

    cache: dict[str, dict] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    if not args.merge:
        cfg = get_ai_config()
        if not cfg["llm_api_key"].strip():
            print("未配置 LLM_API_KEY,无法生成")
            return
        client = _client(cfg)
        model = cfg["llm_model"]
        fails = []
        for s in signs:
            n = str(s["no"])
            if n in cache and cache[n].get("lucky"):
                continue
            if s["no"] in FORCED:
                cache[n] = {"lucky": FORCED[s["no"]], "tone": "", "by": "text",
                            "note": "白话原文明确等级"}
                print(f"[{s['no']:3d}] 原文定级: {FORCED[s['no']]}")
            else:
                for attempt in range(2):
                    try:
                        cache[n] = gen_one(client, model, s)
                        print(f"[{s['no']:3d}] AI: {cache[n]['lucky']} — {cache[n]['tone']}")
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 1:
                            print(f"[{s['no']:3d}] 失败: {exc}")
                            fails.append(s["no"])
                        time.sleep(1)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(args.delay)

        # 统计与一致性
        from collections import Counter
        dist = Counter(v["lucky"] for v in cache.values() if v.get("lucky"))
        print(f"\n档位分布: {dict(sorted(dist.items(), key=lambda x: LEVELS.index(x[0])))}")
        mism = [n for n, v in cache.items() if int(n) in FORCED and v.get("by") == "ai"
                and v["lucky"] != FORCED[int(n)]]
        print(f"AI 与原文不一致(已按原文为准): {mism or '无'}")
        print(f"失败: {fails or '无'}")
        return

    # ---- merge ----
    if not cache:
        print("无候选数据,先运行生成")
        return
    merged, missing = 0, []
    for s in signs:
        item = cache.get(str(s["no"]))
        if item and item.get("lucky"):
            s["lucky"] = item["lucky"]
            if item.get("tone"):
                s["lucky_tone"] = item["tone"]
            merged += 1
        else:
            missing.append(s["no"])
    payload["meta"]["lucky_source"] = (
        "4 签取自白话原文明确等级(12/27/32/34);其余由 AI 按统一口径归纳(非典籍原文标注)"
    )
    payload["meta"]["lucky_model"] = get_ai_config()["llm_model"]
    payload["meta"]["lucky_generated_at"] = time.strftime("%Y-%m-%d")
    SIGNS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已合并 {merged}/100 支签基调;缺失: {missing or '无'}")


if __name__ == "__main__":
    main()

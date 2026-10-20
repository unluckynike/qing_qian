#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取吕祖灵签等级标注(kvov.com 综合解读"作为X签")并与本地文本线索交叉验证。

用途:为签文库补 "lucky" 字段的候选数据。本脚本只产出候选映射与验证报告,
不直接改 lvzu_signs.json;确认后再由 merge 步骤写入。

用法:
  cd backend && .venv/bin/python scripts/scrape_lucky.py           # 全量抓取(走缓存)
  cd backend && .venv/bin/python scripts/scrape_lucky.py --probe 3 # 只抓前3签
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

BASE_ID = 5323333666655574352  # 第1签 id,后续逐 +1
PAGE = "http://m-zy.kvov.com/gy.php?id={id}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) qing_qian-dataset/0.1"

HERE = Path(__file__).resolve().parent
CACHE = HERE / "_cache" / "lucky"
OUT = HERE / "_cache" / "lucky_map.json"
SIGNS = HERE.parent / "data" / "lvzu_signs.json"

GRADE_RE = re.compile(
    r"(?:作为|为|是|属于)\s*((?:上上|上吉|上平|中吉|中平|中下|下下|上|中|下)\s*[签吉]|大吉|大凶)"
)
TOKENS = ["上上吉签", "上上签", "上吉签", "中吉签", "中平签", "中下签", "下下签", "上签", "中签", "下签", "上上", "大吉"]


def fetch(url: str, cache_path: Path) -> str:
    if cache_path.exists() and cache_path.stat().st_size > 3000:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    for _ in range(3):
        r = subprocess.run(["curl", "-sL", "--max-time", "25", "-A", UA, url], capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 3000:
            text = r.stdout.decode("utf-8", errors="replace")
            if "吕祖灵签" in text:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(r.stdout)
                return text
        time.sleep(3)
    raise RuntimeError(f"抓取失败: {url}")


def text_of(html: str) -> str:
    t = re.sub(r"<(script|style)[\s\S]*?</\1>", "", html)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=int, default=0, help="只抓前 N 签(调试)")
    ap.add_argument("--delay", type=float, default=1.2)
    args = ap.parse_args()

    nums = range(1, (args.probe or 100) + 1)
    result: dict[str, dict] = {}
    for n in nums:
        url = PAGE.format(id=BASE_ID + n - 1)
        try:
            html = fetch(url, CACHE / f"lucky_{n:03d}.html")
        except Exception as exc:  # noqa: BLE001
            print(f"[{n:3d}] 抓取失败: {exc}")
            continue
        text = text_of(html)
        m = GRADE_RE.search(text)
        if m:
            grade = m.group(1)
            ctx = text[max(0, m.start() - 30): m.end() + 20]
            result[str(n)] = {"lucky": grade, "evidence": ctx, "source": url}
            print(f"[{n:3d}] 命中: {grade}  ({ctx[:60]}…)")
        else:
            # 兜底:找首个等级 token 的上下文
            ctx = ""
            for tok in TOKENS:
                i = text.find(tok)
                if i > 0:
                    ctx = text[max(0, i - 30): i + 20]
                    break
            result[str(n)] = {"lucky": None, "evidence": ctx, "source": url}
            print(f"[{n:3d}] 未命中" + (f" (附近: {ctx[:50]}…)" if ctx else ""))
        if n < max(nums):
            time.sleep(args.delay)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    hit = sum(1 for v in result.values() if v["lucky"])
    print(f"\n覆盖: {hit}/{len(result)} → {OUT}")

    # 与本地文本线索交叉验证
    data = json.loads(SIGNS.read_text(encoding="utf-8"))
    text_pat = re.compile(r"上上签|上签|上吉|中吉|中平|中签|中下|下签|下下|大吉|大凶|先凶后吉")
    print("\n=== 本地文本线索 vs kvov ===")
    for s in data["signs"]:
        blob = (s.get("summary") or "") + (s.get("vernacular", {}).get("jieyue") or "")
        local = set(text_pat.findall(blob))
        if local:
            kv = result.get(str(s["no"]), {}).get("lucky")
            print(f"  第{s['no']:3d}签 文本线索={sorted(local)} | kvov={kv}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 zhouyi.cc 吕祖灵签 100 签数据 -> backend/data/lvzu_signs.json

流程:
  1. 抓索引页,收集 100 个详情页链接(不假设 ID 连续)
  2. 逐页解析:标题/古人/概述/签文/解曰/卦象/签图/白话诗曰/白话解曰/12 分项释义
  3. 礼貌抓取:默认请求间隔 1.2s,失败重试 2 次;原始页面缓存到 scripts/_cache/
  4. 产出 JSON 并打印校验报告(签号连续性、缺字段、分项覆盖率)

用法:
  python3 scrape_zhouyi.py            # 全量抓取(优先命中缓存)
  python3 scrape_zhouyi.py --limit 3  # 只抓前 3 签(调试解析器)
  python3 scrape_zhouyi.py --no-cache # 忽略缓存重新抓取

注:用 curl 获取页面 —— 兼容本机系统 Python 缺少根证书、urllib 走 HTTPS 报错的环境。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

BASE = "https://www.zhouyi.cc"
INDEX_URL = BASE + "/lingqian/lvzu/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 qing_qian-dataset/0.1"

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE.parent / "data" / "lvzu_signs.json"
CACHE_DIR = HERE / "_cache"

# 12 个传统分项(各签可能缺项)
CATEGORY_KEYS = ["谋望", "钱财", "婚姻", "自身", "家宅", "开业",
                 "迁居", "出行", "疾病", "六甲", "行人", "诉讼"]

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

TITLE_RE = re.compile(r"^第([一二三四五六七八九十百零〇两\d]+)签\s*古人(.+)$")
TITLE_FALLBACK_RE = re.compile(r"^第([一二三四五六七八九十百零〇两\d]+)签\s*(\S.*)$")
HEADING_SKIP_RE = re.compile(r"^吕祖灵签.*(概述和签图|吉凶解签|在线抽签)")
CATEGORY_RE = re.compile(r"^([\u4e00-\u9fa5A-Za-z]{2,4})[：:](.+)$")


def fetch(url: str, cache_path: Path | None, use_cache: bool) -> str:
    """curl 拉页面;成功则写缓存。"""
    if use_cache and cache_path and cache_path.exists() and cache_path.stat().st_size > 5000:
        return cache_path.read_text(encoding="utf-8")
    last_err = None
    for _ in range(3):
        r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, url],
                           capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 5000:
            text = r.stdout.decode("utf-8", errors="replace")
            if "吕祖灵签" in text:
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(r.stdout)
                return text
        last_err = f"rc={r.returncode}, bytes={len(r.stdout)}"
        time.sleep(3)
    raise RuntimeError(f"抓取失败 {url} ({last_err})")


def html_to_lines(html: str) -> list[str]:
    """HTML 转纯文本行:br/块级标签断行,去标签、转实体、清空行。"""
    h = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", html, flags=re.I)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</(div|p|li|tr|h\d|strong)>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                    ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        h = h.replace(ent, ch)
    lines = [ln.strip() for ln in h.split("\n")]
    return [ln for ln in lines if ln and ln != "-->"]


def cn_to_int(s: str) -> int:
    """中文数字转 int,支持 一/十/一百/九十九 等。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    total = 0
    if "百" in s:
        head, _, s = s.partition("百")
        total += (CN_DIGITS.get(head[-1], 1) if head else 1) * 100
    if s:
        if "十" in s:
            head, _, tail = s.partition("十")
            total += (CN_DIGITS.get(head[-1], 1) if head else 1) * 10
            if tail:
                total += CN_DIGITS.get(tail[-1], 0)
        else:
            total += CN_DIGITS.get(s[-1], 0)
    return total


def dedupe_sentences(text: str) -> str:
    """去掉源站白话段落里连续重复的句子(如 'X。X。' 或整句重复两遍)。"""
    parts = re.split(r"(?<=[。！？!?])", text)
    out: list[str] = []
    for p in parts:
        if p and (not out or p.strip() != out[-1].strip()):
            out.append(p)
    return "".join(out)


def split_verse(lines: list[str]) -> list[str]:
    """仅用于校验统计:按句读拆出短句数量(展示时不做强制拆分)。"""
    out: list[str] = []
    for ln in lines:
        for part in re.split(r"[，,；;]", ln):
            part = part.strip().strip("。.！!？?")
            if part:
                out.append(part)
    return out


def find_line(lines: list[str], pred, start: int = 0) -> int:
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return -1


SECTION_STARTS = ("【签文】", "【解曰】", "【卦象】", "【概述】", "【诗曰】", "【诗曰：】", "【释义】")


def next_boundary(lines: list[str], start: int) -> int:
    """start 之后最近的下一个区段起点(含白话区标题与页脚),无则返回文末。"""
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln in SECTION_STARTS or "白话文详解" in ln or "吕祖灵签在线抽签" in ln:
            return i
    return len(lines)


def block(lines: list[str], start: int, stop: int, skip_heading: bool = True) -> list[str]:
    """取 (start, stop) 区间内非标题行。"""
    out = []
    for ln in lines[start + 1: stop if stop != -1 else len(lines)]:
        if skip_heading and HEADING_SKIP_RE.match(ln):
            continue
        out.append(ln)
    return out


def parse_sign(html: str, url: str) -> dict:
    lines = html_to_lines(html)
    missing: list[str] = []

    # 标题行:第一签 古人王母祝寿
    i_title = find_line(lines, lambda ln: bool(TITLE_RE.match(ln)))
    title, ancient, no = "", "", None
    if i_title == -1:
        i_title = find_line(lines, lambda ln: bool(TITLE_FALLBACK_RE.match(ln))
                            and not HEADING_SKIP_RE.match(ln))
        if i_title != -1:
            m = TITLE_FALLBACK_RE.match(lines[i_title])
            no, title, ancient = cn_to_int(m.group(1)), lines[i_title], ""
            missing.append("ancient")
    else:
        m = TITLE_RE.match(lines[i_title])
        no, title, ancient = cn_to_int(m.group(1)), lines[i_title], m.group(2)
    if i_title == -1:
        raise ValueError("找不到标题行(第X签 古人XX)")
    title = re.sub(r"\s+", " ", title.replace("签古人", "签 古人")).strip()

    # 区段提取:以"下一个区段标记"为边界,可容忍源站三种模板差异——
    #   签1-4 多一段【概述】;签82 无独立【卦象】(卦象并入【解曰】正文);
    #   签90 无白话详解整段;签97 的【卦象】标记下源站本身为空。
    i_qw = find_line(lines, lambda ln: ln == "【签文】", i_title)
    i_jy = find_line(lines, lambda ln: ln == "【解曰】", i_qw) if i_qw != -1 else -1
    i_gx = find_line(lines, lambda ln: ln == "【卦象】", i_jy) if i_jy != -1 else -1
    i_gs = find_line(lines, lambda ln: ln == "【概述】", i_jy) if i_jy != -1 else -1
    i_sy = find_line(lines, lambda ln: re.match(r"^【诗曰[:：]?】$", ln), i_jy) if i_jy != -1 else -1
    i_jy2 = find_line(lines, lambda ln: ln == "【解曰】", i_sy) if i_sy != -1 else -1
    i_base = i_jy2 if i_jy2 != -1 else i_jy
    i_syi = find_line(lines, lambda ln: ln == "【释义】", i_base) if i_base != -1 else -1

    summary = dedupe_sentences("".join(block(lines, i_title, i_qw)))
    poem = block(lines, i_qw, next_boundary(lines, i_qw)) if i_qw != -1 else []
    jieyue = "".join(block(lines, i_jy, next_boundary(lines, i_jy))) if i_jy != -1 else ""
    hexagram = "".join(block(lines, i_gx, next_boundary(lines, i_gx))) if i_gx != -1 else ""
    if not hexagram and "卦象：" in jieyue:  # 签82:源站把卦象写进了解曰正文
        hexagram = jieyue.split("卦象：", 1)[1].strip()
    overview = ""
    if i_gs != -1:
        overview = dedupe_sentences("".join(block(lines, i_gs, next_boundary(lines, i_gs))))

    # 白话详解(签90 等源站无此段时为空)
    v_poem = block(lines, i_sy, next_boundary(lines, i_sy)) if i_sy != -1 else []
    v_jieyue = ""
    if i_jy2 != -1:
        v_jieyue = dedupe_sentences("".join(block(lines, i_jy2, next_boundary(lines, i_jy2))))

    # 12 分项释义(遇到第一条不匹配即结束)
    categories: dict[str, str] = {}
    if i_syi != -1:
        for ln in lines[i_syi + 1:]:
            m = CATEGORY_RE.match(ln)
            if m:
                categories[m.group(1)] = m.group(2).strip()
            elif categories:
                break

    # 签图
    img = re.search(r'<img[^>]+src="([^"]*uploads[^"]+)"', html)
    image_url = img.group(1).replace("http://", "https://", 1) if img else None

    for name, val in (("poem", poem), ("jieyue", jieyue), ("hexagram", hexagram),
                      ("summary", summary), ("categories", categories)):
        if not val:
            missing.append(name)

    return {
        "no": no,
        "title": title,
        "ancient": ancient,
        "summary": summary,
        "poem": poem,
        "jieyue": jieyue,
        "hexagram": hexagram,
        "overview": overview,
        "image_url": image_url,
        "vernacular": {"poem": v_poem, "jieyue": v_jieyue},
        "categories": categories,
        "source_url": url,
        "_missing": missing,  # 校验用,最终产出前移除
    }


def parse_index(html: str) -> list[tuple[int, str]]:
    """索引页 -> [(签号, 详情页URL)],按签号排序去重。"""
    links = re.findall(
        r'href="(/lingqian/lvzu/\d+\.html)"[^>]*>([^<]*第(\d+)签[^<]*)<', html)
    seen: dict[int, str] = {}
    for href, _text, num in links:
        seen[int(num)] = BASE + href
    return sorted(seen.items())


def validate(signs: list[dict]) -> str:
    report = []
    nums = [s["no"] for s in signs]
    report.append(f"总签数: {len(signs)}(期望 100)")
    report.append(f"签号范围: {min(nums)}–{max(nums)}")
    missing_nums = sorted(set(range(1, 101)) - set(nums))
    report.append(f"缺失签号: {missing_nums or '无'}")
    dup = sorted({n for n in nums if nums.count(n) > 1})
    report.append(f"重复签号: {dup or '无'}")

    for field in ("poem", "jieyue", "hexagram", "summary", "overview", "ancient", "image_url"):
        bad = [s["no"] for s in signs if not s.get(field)]
        report.append(f"缺 {field}: {bad or '无'}")

    no_vern = [s["no"] for s in signs if not s["vernacular"]["jieyue"]]
    report.append(f"缺白话解曰: {no_vern or '无'}")
    report.append("分项释义覆盖率(共 %d 签):" % len(signs))
    for key in CATEGORY_KEYS:
        cnt = sum(1 for s in signs if key in s["categories"])
        report.append(f"  {key}: {cnt}/{len(signs)}")
    unknown = sorted({k for s in signs for k in s["categories"] if k not in CATEGORY_KEYS})
    report.append(f"非标准分项: {unknown or '无'}")
    no_overview = [s["no"] for s in signs if not s["overview"]]
    report.append(f"无概述(源站签5-100模板即无此段): {len(no_overview)} 签")
    clause_dist = Counter(len(split_verse(s["poem"])) for s in signs)
    report.append(f"签诗句读数分布: {dict(sorted(clause_dist.items()))}")
    odd_clause = [s["no"] for s in signs if not 3 <= len(split_verse(s["poem"])) <= 8]
    report.append(f"句读数超出3-8(需人工检查): {odd_clause or '无'}")
    return "\n".join(report)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 签(调试)")
    ap.add_argument("--delay", type=float, default=1.2, help="请求间隔秒数")
    ap.add_argument("--no-cache", action="store_true", help="忽略缓存重新抓取")
    ap.add_argument("--out", default=str(OUT_PATH), help="输出 JSON 路径")
    args = ap.parse_args()
    use_cache = not args.no_cache

    print("抓取索引页:", INDEX_URL)
    index_html = fetch(INDEX_URL, CACHE_DIR / "index.html", use_cache)
    entries = parse_index(index_html)
    print(f"索引页解析到 {len(entries)} 个详情链接")
    if args.limit:
        entries = entries[:args.limit]

    signs, failed = [], []
    for i, (num, url) in enumerate(entries, 1):
        print(f"[{i}/{len(entries)}] 第{num}签 {url}")
        cache_file = CACHE_DIR / f"sign_{num:03d}.html"
        from_cache = use_cache and cache_file.exists() and cache_file.stat().st_size > 5000
        try:
            html = fetch(url, cache_file, use_cache)
            signs.append(parse_sign(html, url))
        except Exception as e:  # noqa: BLE001 逐签容错,失败不中断
            print(f"  !! 解析/抓取失败: {e}")
            failed.append((num, str(e)))
        if i < len(entries) and not from_cache:
            time.sleep(args.delay)

    print("\n===== 校验报告 =====")
    if signs:
        print(validate(signs))
    if failed:
        print(f"失败 {len(failed)} 签: {failed}")

    payload = {
        "meta": {
            "system": "吕祖灵签",
            "temple": "青签",
            "total": len(signs),
            "source": INDEX_URL,
            "scraped_at": date.today().isoformat(),
            "license_note": "签诗/解曰/卦象等古典原文属公版;白话总述与分项释义整理自公开网页,仅内部参考,公开部署请替换",
            "cleaning_note": "白话字段已移除源站连续重复句;签诗保留源站分行;古文其余字段未改动",
        },
        "signs": [{k: v for k, v in s.items() if k != "_missing"} for s in signs],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写出: {out}({out.stat().st_size // 1024} KB)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

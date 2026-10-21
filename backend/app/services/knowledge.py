"""使用助手知识库:docs/ 文档切片、构建与检索。

检索双引擎(自动选择):
- **向量模式**:doc_chunks 中已有向量且配置了 embedding 模型 → pgvector 余弦距离 Top-K;
- **关键词模式**:否则用 CJK 二元组 + BM25 风格评分(对小型 FAQ 语料效果足够),
  embedding 模型就绪后在后台"重建知识库"即可自动升级为向量检索。

语料范围:docs/user-guide.md、docs/faq.md、docs/admin-guide.md
(索引说明 docs/README.md 属维护文档,不参与检索)。
"""
import math
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy import text as sql_text

from ..config import BACKEND_DIR, settings
from ..db import SessionLocal
from ..orm import DocChunk
from .embedding import EmbeddingUnavailable, embed_texts, is_configured as embedding_configured

DOCS_DIR = BACKEND_DIR.parent / "docs"
KB_FILES = ("user-guide.md", "faq.md", "admin-guide.md")
EMBED_BATCH = 8


def split_sections(doc_title: str, md: str) -> list[dict]:
    """按 ## 小节切片;开头(第一个 ## 之前)的引言块以文档标题命名。"""
    sections: list[dict] = []
    title = doc_title
    lines: list[str] = []

    def flush() -> None:
        body = "\n".join(lines).strip()
        if len(body) >= 30:  # 过短的碎片不入库
            sections.append({"section": title, "content": body})

    for line in md.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            continue  # 文档大标题只用作引言块标题
        if line.startswith("## "):
            flush()
            title = line[3:].strip()
            lines = [line]
        else:
            lines.append(line)
    flush()
    return sections


def _read_and_split() -> list[dict]:
    chunks: list[dict] = []
    for name in KB_FILES:
        path = DOCS_DIR / name
        if not path.exists():
            continue
        md = path.read_text(encoding="utf-8")
        doc_title = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), name)
        for item in split_sections(doc_title, md):
            chunks.append({"doc_path": f"docs/{name}", **item})
    return chunks


# ---------- 关键词检索(BM25 风格 + CJK 二元组) ----------
def _tokens(s: str) -> list[str]:
    lowered = s.lower()
    words = re.findall(r"[a-z0-9_]{2,}", lowered)
    cjk = [c for c in s if "\u4e00" <= c <= "\u9fff"]
    bigrams = ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    return words + cjk + bigrams


def _keyword_search(question: str, rows: list[dict], top_k: int) -> list[dict]:
    q_tokens = set(_tokens(question))
    n = len(rows)
    docs = [Counter(_tokens(r["content"])) for r in rows]
    titles = [set(_tokens(r["section"])) for r in rows]
    df: Counter = Counter()
    for tokens in docs:
        for t in set(tokens):
            df[t] += 1
    avg_len = max(1.0, sum(sum(t.values()) for t in docs) / max(1, n))
    k1, b = 1.5, 0.75

    scored: list[tuple[float, dict]] = []
    for i, tf in enumerate(docs):
        length = sum(tf.values()) or 1
        score = 0.0
        for t in q_tokens:
            if t not in tf:
                continue
            idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1)
            score += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * length / avg_len))
        score += 1.6 * len(q_tokens & titles[i])  # 小节标题命中加权
        if score > 0:
            scored.append((score, {**rows[i], "score": round(score, 3)}))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]


# ---------- 向量检索(pgvector) ----------
def _vector_search(question: str, top_k: int) -> list[dict]:
    vec = embed_texts([question])[0]
    vec_literal = "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
    sql = sql_text(
        "SELECT doc_path, section, content, 1 - (embedding <=> CAST(:qv AS vector)) AS score "
        "FROM doc_chunks WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> CAST(:qv AS vector) LIMIT :k"
    )
    with SessionLocal() as db:
        rows = db.execute(sql, {"qv": vec_literal, "k": top_k}).fetchall()
    return [
        {"doc_path": r.doc_path, "section": r.section, "content": r.content, "score": round(float(r.score), 3)}
        for r in rows
    ]


def search(question: str, top_k: int | None = None) -> dict:
    """对外统一入口:返回 {"mode": vector|keyword|empty, "items": [...]}"""
    top_k = top_k or settings.kb_top_k
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(DocChunk)) or 0
        embedded = db.scalar(
            select(func.count()).select_from(DocChunk).where(DocChunk.embedding.is_not(None))
        ) or 0
        if total == 0:
            return {"mode": "empty", "items": []}
        if embedded > 0 and embedding_configured():
            try:
                return {"mode": "vector", "items": _vector_search(question, top_k)}
            except EmbeddingUnavailable:
                pass  # 向量服务暂不可用 → 关键词兜底
        rows = [
            {"doc_path": c.doc_path, "section": c.section, "content": c.content}
            for c in db.scalars(select(DocChunk)).all()
        ]
    return {"mode": "keyword", "items": _keyword_search(question, rows, top_k)}


# ---------- 构建 / 状态 ----------
def rebuild() -> dict:
    """重读 docs/ → 切片重建;配置了 embedding 模型时向量化,失败则降级关键词。"""
    chunks = _read_and_split()
    if not chunks:
        raise FileNotFoundError("docs/ 下未找到知识库文件(user-guide/faq/admin-guide)")

    mode, embed_error = "keyword", None
    embeddings: list[list[float] | None] = [None] * len(chunks)
    if embedding_configured():
        try:
            texts = [c["content"] for c in chunks]
            vecs: list[list[float]] = []
            for i in range(0, len(texts), EMBED_BATCH):
                vecs.extend(embed_texts(texts[i:i + EMBED_BATCH]))
            embeddings = list(vecs)
            mode = "vector"
        except EmbeddingUnavailable as exc:
            embed_error = str(exc)

    with SessionLocal() as db:
        db.execute(delete(DocChunk))
        for chunk, vec in zip(chunks, embeddings):
            db.add(DocChunk(doc_path=chunk["doc_path"], section=chunk["section"], content=chunk["content"], embedding=vec))
        db.commit()
    return {"mode": mode, "chunks": len(chunks), "embedding_error": embed_error}


def status() -> dict:
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(DocChunk)) or 0
        embedded = db.scalar(
            select(func.count()).select_from(DocChunk).where(DocChunk.embedding.is_not(None))
        ) or 0
        last = db.scalar(select(func.max(DocChunk.updated_at)))
    return {
        "chunks": total,
        "embedded": embedded,
        "last_built_at": last.isoformat() if last else None,
        "files": list(KB_FILES),
        "embedding_configured": embedding_configured(),
    }

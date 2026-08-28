from __future__ import annotations

import re

from ..config import settings
from .rag import VectorStore

# Grounded answering for live calls: the agent answers ONLY from ingested
# documents (brochures, fee sheets, FAQs). If nothing relevant is retrieved, it
# says it will check rather than inventing an answer — the core anti-hallucination
# guarantee that makes the bot trustworthy on a sales call.

_SENT = re.compile(r"(?<=[.!?])\s+")
MIN_SCORE = 0.05

_STOP = {"the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and",
         "what", "how", "when", "where", "which", "do", "does", "my", "your",
         "i", "you", "it", "this", "that", "with", "can", "will", "much", "many"}


def _norm(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "sxzo":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _content_overlap(query: str, text: str) -> int:
    q = {_norm(w) for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP}
    t = {_norm(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}
    return len(q & t)


def chunk_text(text: str, *, max_chars: int = 240) -> list[str]:
    """Split a document into retrieval-sized passages on sentence boundaries."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sents = _SENT.split(text)
    chunks, buf = [], ""
    for s in sents:
        if len(buf) + len(s) + 1 > max_chars and buf:
            chunks.append(buf.strip())
            buf = ""
        buf += (" " if buf else "") + s
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def ingest(db, *, title: str, text: str, source: str = "upload",
           org_id: str | None = None) -> dict:
    """Persist a document as chunks so retrieval survives restarts and is
    shared across workers/tenants."""
    from ..models import KnowledgeChunk, KnowledgeDoc
    org_id = org_id or settings.default_org_id
    pieces = chunk_text(text)
    doc = KnowledgeDoc(org_id=org_id, title=title, source=source, chunks=len(pieces))
    db.add(doc)
    db.flush()
    for i, piece in enumerate(pieces):
        db.add(KnowledgeChunk(doc_id=doc.id, org_id=org_id, title=title,
                              text=piece, ord=i))
    db.flush()
    return {"doc_id": doc.id, "title": title, "chunks": len(pieces)}


def _load_store(db, org_id: str) -> tuple[VectorStore, int]:
    """Build an in-memory index from this org's chunks (cheap; can be cached)."""
    from sqlalchemy import select

    from ..models import KnowledgeChunk
    store = VectorStore()
    rows = db.scalars(select(KnowledgeChunk).where(
        KnowledgeChunk.org_id == org_id)).all()
    for r in rows:
        store.add(r.text, {"doc_id": r.doc_id, "title": r.title, "chunk_id": r.id})
    return store, len(rows)


def search(db, query: str, *, org_id: str | None = None, top_k: int | None = None) -> list[dict]:
    org_id = org_id or settings.default_org_id
    from sqlalchemy import select

    from ..models import KnowledgeChunk
    from .embeddings import cosine, embed
    rows = db.scalars(select(KnowledgeChunk).where(
        KnowledgeChunk.org_id == org_id)).all()
    if not rows:
        return []
    # Hybrid: semantic embedding similarity + keyword overlap for robustness.
    qvec = embed([query])[0]
    cvecs = embed([r.text for r in rows])
    scored = []
    for r, cv in zip(rows, cvecs, strict=False):
        sim = cosine(qvec, cv)
        overlap = _content_overlap(query, r.text)
        scored.append((r, sim + 0.05 * overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    k = top_k or settings.rag_top_k
    return [{"text": r.text, "score": round(s, 4),
             "meta": {"doc_id": r.doc_id, "title": r.title, "chunk_id": r.id}}
            for r, s in scored[:k]]


def answer(db, query: str, *, org_id: str | None = None) -> dict:
    """Return a grounded answer object: retrieved passages + a citation list, or
    a safe 'let me check' when nothing relevant is found (no hallucination)."""
    hits = search(db, query, org_id=org_id)
    strong = [h for h in hits
              if _content_overlap(query, h["text"]) >= 2
              or (h["score"] >= MIN_SCORE and _content_overlap(query, h["text"]) >= 1)]
    if not strong:
        return {"grounded": False,
                "answer": ("That's a good question — let me confirm the exact "
                           "detail and get right back to you."),
                "citations": [], "context": ""}
    context = "\n".join(f"- {h['text']}" for h in strong)
    citations = [{"title": h["meta"].get("title", ""), "doc_id": h["meta"].get("doc_id", ""),
                  "score": h["score"]} for h in strong]
    return {"grounded": True,
            "answer": strong[0]["text"],
            "citations": citations, "context": context}


def ground_block(db, query: str, *, org_id: str | None = None) -> str:
    """APPROVED-FACTS block injected into the responder prompt so replies stay
    within what the documents actually say."""
    hits = [h for h in search(db, query, org_id=org_id)
            if h["score"] >= MIN_SCORE and _content_overlap(query, h["text"]) >= 1]
    if not hits:
        return ""
    return "APPROVED FACTS (answer only from these):\n" + \
           "\n".join(f"- {h['text']}" for h in hits)

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from ..config import settings

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Doc:
    text: str
    meta: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"doc_{uuid.uuid4().hex[:10]}")
    vec: Counter = field(default_factory=Counter)


class VectorStore:
    """Tiny local retrieval store (bag-of-words + cosine). Deterministic and
    dependency-free so RAG works offline; swap in pgvector/FAISS behind `search`."""

    def __init__(self) -> None:
        self.docs: dict[str, Doc] = {}
        self._df: Counter = Counter()

    def add(self, text: str, meta: dict | None = None) -> str:
        doc = Doc(text=text, meta=meta or {})
        doc.vec = Counter(_tokens(text))
        for term in set(doc.vec):
            self._df[term] += 1
        self.docs[doc.id] = doc
        return doc.id

    def _tfidf(self, counts: Counter) -> dict[str, float]:
        n = max(1, len(self.docs))
        return {t: (c) * math.log((n + 1) / (1 + self._df.get(t, 0)) + 1)
                for t, c in counts.items()}

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or settings.rag_top_k
        q = self._tfidf(Counter(_tokens(query)))
        scored = []
        for doc in self.docs.values():
            d = self._tfidf(doc.vec)
            score = self._cosine(q, d)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": d.id, "score": round(s, 4), "text": d.text, "meta": d.meta}
                for s, d in scored[:top_k]]

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        num = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return num / (na * nb) if na and nb else 0.0


def ground(query: str, store: VectorStore) -> str:
    """Return an APPROVED-FACTS style context block for the responder."""
    hits = store.search(query)
    if not hits:
        return ""
    return "RETRIEVED:\n" + "\n".join(f"- {h['text']}" for h in hits)


store = VectorStore()

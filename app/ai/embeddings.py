from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request

from ..config import settings

_DIM = 256


def _stem(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "sxzo":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


_STOP = {"the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and",
         "what", "how", "when", "where", "which", "do", "does", "my", "your",
         "i", "you", "it", "this", "that", "with", "can", "will", "much", "many",
         "am", "be", "was", "were", "has", "have", "we", "they", "our"}


def _local_embed(text: str) -> list[float]:
    """Deterministic hashing embedding (bag-of-words feature hashing) over content
    words only. No deps, stable across runs; beats pure keyword match and keeps
    the RAG pipeline testable without an API key."""
    vec = [0.0] * _DIM
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if raw in _STOP:
            continue
        tok = _stem(raw)
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % _DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts: list[str]) -> list[list[float]]:
    provider = settings.embeddings_provider
    if provider in ("openai", "voyage") and settings.embeddings_api_key:
        try:
            return _remote_embed(texts, provider)
        except Exception:
            pass
    return [_local_embed(t) for t in texts]


def _remote_embed(texts: list[str], provider: str) -> list[list[float]]:
    if provider == "openai":
        url = "https://api.openai.com/v1/embeddings"
        body = json.dumps({"model": settings.embeddings_model, "input": texts}).encode()
        headers = {"Authorization": f"Bearer {settings.embeddings_api_key}",
                   "Content-Type": "application/json"}
    else:  # voyage
        url = "https://api.voyageai.com/v1/embeddings"
        body = json.dumps({"model": settings.embeddings_model or "voyage-2",
                           "input": texts}).encode()
        headers = {"Authorization": f"Bearer {settings.embeddings_api_key}",
                   "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    return [row["embedding"] for row in data["data"]]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return num / (na * nb) if na and nb else 0.0

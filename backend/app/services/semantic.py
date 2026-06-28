"""Semantic layer powered by librarian's embedders.

We reuse librarian's pluggable embedder substrate (OpenAI when a key is present,
the offline hashing embedder otherwise) and keep a small persistent vector index
of inventory items. This drives two things:

* **Deduplication / grouping** at intake — "Arroz 1kg" and "Rice 1 kg bag"
  collapse to the same canonical item.
* **Semantic search** for the agent and the UI.
"""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path

from ..config import settings

_lock = threading.Lock()


def _build_embedder():
    if settings.ai_enabled:
        try:
            from librarian.embeddings.openai_embedder import OpenAIEmbedder

            return OpenAIEmbedder(
                model=settings.openai_embed_model, api_key=settings.openai_api_key
            )
        except Exception:
            pass
    from librarian.embeddings.hashing import HashingEmbedder

    return HashingEmbedder(dim=512)


class SemanticIndex:
    def __init__(self) -> None:
        self._embedder = _build_embedder()
        self._path: Path = settings.data_path / "item_index.json"
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, str] = {}  # item_id -> display text
        self._load()

    # --- persistence ----------------------------------------------------
    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                self._vectors = raw.get("vectors", {})
                self._meta = raw.get("meta", {})
            except Exception:
                self._vectors, self._meta = {}, {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"vectors": self._vectors, "meta": self._meta}))
        tmp.replace(self._path)

    # --- ops ------------------------------------------------------------
    def embed(self, text: str) -> list[float]:
        return self._embedder.embed_one(text or " ")

    def upsert(self, item_id: str, text: str) -> None:
        with _lock:
            self._vectors[item_id] = self.embed(text)
            self._meta[item_id] = text
            self._save()

    def remove(self, item_id: str) -> None:
        with _lock:
            self._vectors.pop(item_id, None)
            self._meta.pop(item_id, None)
            self._save()

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        if not self._vectors:
            return []
        qv = self.embed(query)
        scored = [(iid, _cosine(qv, vec)) for iid, vec in self._vectors.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def nearest(
        self, text: str, exclude: str | None = None, allowed: set[str] | None = None
    ) -> tuple[str | None, float]:
        best_id, best_score = None, -1.0
        if not self._vectors:
            return None, 0.0
        qv = self.embed(text)
        for iid, vec in self._vectors.items():
            if iid == exclude:
                continue
            if allowed is not None and iid not in allowed:
                continue
            s = _cosine(qv, vec)
            if s > best_score:
                best_id, best_score = iid, s
        return best_id, max(best_score, 0.0)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


_index: SemanticIndex | None = None


def get_index() -> SemanticIndex:
    global _index
    if _index is None:
        _index = SemanticIndex()
    return _index

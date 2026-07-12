# Copyright 2026 akai-joy
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# limitations under the License.
"""Semantic canon retrieval for the Continuity/Provenance agents.

Keyword LIKE-search stops finding the right neighbours once a world grows past
a few hundred entries ("the drake in the foundry" never matches "Slagmaw").
This module embeds canon entries (Gemini embeddings) into a vector index held
by the CanonStore and serves cosine top-k for a query.

Degrades deliberately: any embedding failure (offline, keyless, quota) falls
back to the store's keyword search, and WORLD_ENGINE_EMBEDDINGS=off disables
the whole layer (unit tests set this so no network is touched).

Backfill an existing world:  uv run python -m app.core.retrieval [--world ID]
"""

import hashlib
import logging
import math
import os
import sys

from app.core.config import load_policy_config
from app.core.store import CanonStore
from app.core.types import CanonEmbedding, CanonEntry

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_DIMENSIONS = 768
DEFAULT_TOP_K = 8

# Batch limit for one embed call (API allows more; stay conservative).
_BATCH = 100


def _retrieval_config() -> dict:
    return load_policy_config().get("retrieval", {}) or {}


def is_enabled() -> bool:
    if os.getenv("WORLD_ENGINE_EMBEDDINGS", "").lower() == "off":
        return False
    return bool(_retrieval_config().get("enabled", True))


def _model_name() -> str:
    return _retrieval_config().get("embedding_model", DEFAULT_EMBEDDING_MODEL)


def _dimensions() -> int:
    return int(_retrieval_config().get("embedding_dimensions", DEFAULT_DIMENSIONS))


def _top_k() -> int:
    return int(_retrieval_config().get("top_k", DEFAULT_TOP_K))


def content_hash(entry: CanonEntry) -> str:
    return hashlib.sha256(f"{entry.title}\n{entry.body}".encode()).hexdigest()


def embed_texts(texts: list[str], *, task_type: str) -> list[list[float]]:
    """Embed a list of texts; raises on any failure (callers fall back)."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        batch = texts[i : i + _BATCH]
        response = client.models.embed_content(
            model=_model_name(),
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=_dimensions(),
            ),
        )
        vectors.extend([list(e.values) for e in response.embeddings])
    return vectors


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return -1.0
    return dot / (norm_a * norm_b)


def index_canon_entry(store: CanonStore, entry: CanonEntry) -> bool:
    """Upsert the embedding for one entry; skips when text is unchanged.

    Returns True if a new vector was written. Raises on embedding failure —
    call sites treat indexing as best-effort.
    """
    if not is_enabled():
        return False
    digest = content_hash(entry)
    existing = store.get_canon_embedding(entry.id)
    if existing and existing.content_hash == digest and existing.model == _model_name():
        return False
    [vector] = embed_texts(
        [f"{entry.title}\n{entry.body}"], task_type="RETRIEVAL_DOCUMENT"
    )
    store.save_canon_embedding(
        CanonEmbedding(
            canon_id=entry.id,
            world_id=entry.world_id,
            model=_model_name(),
            content_hash=digest,
            vector=vector,
        )
    )
    return True


def ensure_index(store: CanonStore, world_id: str | None = None) -> tuple[int, int]:
    """Backfill embeddings for all canon entries (scoped). Returns (indexed, skipped)."""
    if not is_enabled():
        return (0, 0)
    entries = store.list_canon_entries(world_id)
    existing = {e.canon_id: e for e in store.list_canon_embeddings(world_id)}
    model = _model_name()

    pending: list[CanonEntry] = []
    for entry in entries:
        row = existing.get(entry.id)
        if row and row.content_hash == content_hash(entry) and row.model == model:
            continue
        pending.append(entry)

    if not pending:
        return (0, len(entries))

    vectors = embed_texts(
        [f"{e.title}\n{e.body}" for e in pending], task_type="RETRIEVAL_DOCUMENT"
    )
    for entry, vector in zip(pending, vectors, strict=True):
        store.save_canon_embedding(
            CanonEmbedding(
                canon_id=entry.id,
                world_id=entry.world_id,
                model=model,
                content_hash=content_hash(entry),
                vector=vector,
            )
        )
    return (len(pending), len(entries) - len(pending))


def semantic_search(
    store: CanonStore,
    query: str,
    world_id: str | None = None,
    top_k: int | None = None,
) -> list[CanonEntry]:
    """Cosine top-k canon entries for a query; keyword fallback on any failure."""
    if not is_enabled():
        return store.search_canon_entries(query, world_id)

    try:
        entries = store.list_canon_entries(world_id)
        if not entries:
            return []
        by_id = {e.id: e for e in entries}

        rows = store.list_canon_embeddings(world_id)
        indexed_ids = {r.canon_id for r in rows}
        # First search on a mostly-unindexed world: backfill once (one batched
        # embed call), then every later search is index-only.
        if len(indexed_ids & set(by_id)) < len(by_id):
            ensure_index(store, world_id)
            rows = store.list_canon_embeddings(world_id)

        model = _model_name()
        rows = [r for r in rows if r.canon_id in by_id and r.model == model]
        if not rows:
            return store.search_canon_entries(query, world_id)

        [query_vec] = embed_texts([query], task_type="RETRIEVAL_QUERY")
        scored = sorted(
            ((r, _cosine(query_vec, r.vector)) for r in rows),
            key=lambda pair: pair[1],
            reverse=True,
        )
        k = top_k if top_k is not None else _top_k()
        return [by_id[r.canon_id] for r, _score in scored[:k]]
    except Exception as e:
        logger.warning("Semantic retrieval unavailable (%s); using keyword search.", e)
        return store.search_canon_entries(query, world_id)


if __name__ == "__main__":
    from app.core.store import get_store

    logging.basicConfig(level=logging.INFO)
    target_world = None
    if "--world" in sys.argv:
        target_world = sys.argv[sys.argv.index("--world") + 1]
    indexed, skipped = ensure_index(get_store(), target_world)
    print(f"Indexed {indexed} canon entries ({skipped} already current).")

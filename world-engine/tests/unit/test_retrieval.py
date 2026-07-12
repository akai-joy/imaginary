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
"""Semantic canon retrieval: vector persistence, cosine ranking, world scoping,
and the deliberate keyword fallback when embeddings are unavailable."""

import os
import tempfile

import pytest

from app.core import retrieval
from app.core.store import SQLiteCanonStore
from app.core.types import CanonEmbedding, CanonEntry, ContributionType


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield SQLiteCanonStore(db_path=path)
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def enabled(monkeypatch):
    """Re-enable the retrieval layer (conftest turns it off suite-wide)."""
    monkeypatch.setenv("WORLD_ENGINE_EMBEDDINGS", "on")


def _entry(id_: str, title: str, body: str, world_id: str = "world_genesis"):
    return CanonEntry(
        id=id_,
        world_id=world_id,
        type=ContributionType.LORE,
        title=title,
        body=body,
        contributor_id="tester",
    )


def test_embedding_roundtrip_through_sqlite_blob(store):
    vec = [0.25, -1.5, 3.0, 0.0625]
    store.save_canon_embedding(
        CanonEmbedding(
            canon_id="canon_a",
            world_id="world_genesis",
            model="test-model",
            content_hash="h1",
            vector=vec,
        )
    )
    row = store.get_canon_embedding("canon_a")
    assert row is not None
    assert row.vector == pytest.approx(vec)
    assert row.model == "test-model"

    scoped = store.list_canon_embeddings("world_genesis")
    assert [r.canon_id for r in scoped] == ["canon_a"]
    assert store.list_canon_embeddings("world_other") == []


def test_semantic_search_ranks_by_cosine_and_scopes_by_world(
    store, enabled, monkeypatch
):
    entries = [
        _entry("canon_a", "The Ember Accord", "A pact sworn in the foundry."),
        _entry("canon_b", "Lantern Row", "A street of amber streetlamps."),
        _entry("canon_c", "Pirate Cove", "Elsewhere.", world_id="world_pirates"),
    ]
    for e in entries:
        store.save_canon_entry(e)

    vectors = {
        "canon_a": [1.0, 0.0],
        "canon_b": [0.0, 1.0],
        "canon_c": [1.0, 0.0],
    }
    model = retrieval._model_name()
    for cid, vec in vectors.items():
        e = next(x for x in entries if x.id == cid)
        store.save_canon_embedding(
            CanonEmbedding(
                canon_id=cid,
                world_id=e.world_id,
                model=model,
                content_hash=retrieval.content_hash(e),
                vector=vec,
            )
        )

    # Query vector points at canon_b's direction
    monkeypatch.setattr(
        retrieval, "embed_texts", lambda texts, task_type: [[0.1, 1.0]] * len(texts)
    )

    results = retrieval.semantic_search(store, "amber lamps", world_id="world_genesis")
    assert [e.id for e in results] == ["canon_b", "canon_a"]

    # top_k truncates
    top1 = retrieval.semantic_search(
        store, "amber lamps", world_id="world_genesis", top_k=1
    )
    assert [e.id for e in top1] == ["canon_b"]

    # world scope: pirates world never sees genesis canon
    pirates = retrieval.semantic_search(store, "anything", world_id="world_pirates")
    assert [e.id for e in pirates] == ["canon_c"]


def test_semantic_search_falls_back_to_keyword_on_embed_failure(
    store, enabled, monkeypatch
):
    store.save_canon_entry(
        _entry("canon_dragon", "The Slagmaw Drake", "A dragon nesting in cooling iron.")
    )

    def boom(texts, task_type):
        raise RuntimeError("no network")

    monkeypatch.setattr(retrieval, "embed_texts", boom)

    results = retrieval.semantic_search(store, "dragon", world_id="world_genesis")
    assert [e.id for e in results] == ["canon_dragon"]


def test_disabled_layer_uses_keyword_and_never_embeds(store, monkeypatch):
    monkeypatch.setenv("WORLD_ENGINE_EMBEDDINGS", "off")
    store.save_canon_entry(
        _entry("canon_dragon", "The Slagmaw Drake", "A dragon nesting in cooling iron.")
    )

    def fail(*args, **kwargs):
        raise AssertionError("embed_texts must not be called when disabled")

    monkeypatch.setattr(retrieval, "embed_texts", fail)

    results = retrieval.semantic_search(store, "dragon")
    assert [e.id for e in results] == ["canon_dragon"]
    assert retrieval.index_canon_entry(store, _entry("x", "t", "b")) is False


def test_index_canon_entry_skips_unchanged_content(store, enabled, monkeypatch):
    calls = []

    def fake_embed(texts, task_type):
        calls.append(list(texts))
        return [[1.0, 2.0]] * len(texts)

    monkeypatch.setattr(retrieval, "embed_texts", fake_embed)

    entry = _entry("canon_a", "Title", "Body")
    assert retrieval.index_canon_entry(store, entry) is True
    assert retrieval.index_canon_entry(store, entry) is False  # unchanged → skipped
    assert len(calls) == 1

    entry.body = "Body, revised."
    assert retrieval.index_canon_entry(store, entry) is True
    assert len(calls) == 2


def test_ensure_index_backfills_only_missing(store, enabled, monkeypatch):
    for i in range(3):
        store.save_canon_entry(_entry(f"canon_{i}", f"T{i}", f"B{i}"))

    def fake_embed(texts, task_type):
        return [[float(len(t)), 1.0] for t in texts]

    monkeypatch.setattr(retrieval, "embed_texts", fake_embed)

    indexed, skipped = retrieval.ensure_index(store, "world_genesis")
    assert (indexed, skipped) == (3, 0)
    indexed, skipped = retrieval.ensure_index(store, "world_genesis")
    assert (indexed, skipped) == (0, 3)

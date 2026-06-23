# Copyright 2026 Google LLC
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
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the Cartographer node + its controller integration."""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.agents import cartographer as cart_mod
from app.core import controller as controller_mod
from app.core.store import SQLiteCanonStore
from app.core.types import CanonEntry, Contribution, ContributionType, MapMeta


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield SQLiteCanonStore(db_path=path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def _place(store, entry_id, region, x, y):
    store.save_canon_entry(
        CanonEntry(
            id=entry_id,
            type=ContributionType.LOCATION,
            title=entry_id,
            body="a place",
            contributor_id="u1",
            map_meta=MapMeta(x=x, y=y, region=region),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )


def _mock_llm(monkeypatch, json_text):
    mock_client = MagicMock()
    resp = MagicMock()
    resp.text = json_text
    mock_client.models.generate_content.return_value = resp
    monkeypatch.setattr("google.genai.Client", lambda: mock_client)
    return mock_client


def _ctx_with_accepted(entry_id):
    ctx = MagicMock()
    ctx.state = {"narrator_proposal": {"new_entry": {"id": entry_id}}}
    return ctx


# --- node: pass-through cases (no LLM call) --------------------------------

def test_non_spatial_type_passes_through(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    client = _mock_llm(monkeypatch, "{}")
    contrib = Contribution(id="c1", author_id="u1", type="lore", title="t", body="b")

    events = list(cart_mod.cartographer_node(_ctx_with_accepted("canon_c1"), contrib))

    assert events[-1].output is contrib
    client.models.generate_content.assert_not_called()


def test_blocked_contribution_passes_through(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    client = _mock_llm(monkeypatch, "{}")
    contrib = Contribution(id="c1", author_id="u1", type="location", title="t", body="b")

    ctx = MagicMock()
    ctx.state = {}  # narrator did not accept -> no new_entry
    list(cart_mod.cartographer_node(ctx, contrib))

    assert "cartographer_proposal" not in ctx.state
    client.models.generate_content.assert_not_called()


def test_entity_with_no_places_is_not_placed(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    client = _mock_llm(monkeypatch, "{}")
    contrib = Contribution(id="c1", author_id="u1", type="character", title="Hero", body="b")

    ctx = _ctx_with_accepted("canon_c1")
    list(cart_mod.cartographer_node(ctx, contrib))

    assert "cartographer_proposal" not in ctx.state
    client.models.generate_content.assert_not_called()


# --- node: placement proposals --------------------------------------------

def test_location_placement_proposed(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    _place(store, "canon_eldoria", "Heartlands", 50, 50)
    _mock_llm(
        monkeypatch,
        '{"region": "The Frostmark", "x": 20, "y": 80, '
        '"near": ["canon_eldoria"], "located_in": ""}',
    )
    contrib = Contribution(id="c1", author_id="u1", type="location", title="Frostpeak", body="cold")

    ctx = _ctx_with_accepted("canon_c1")
    list(cart_mod.cartographer_node(ctx, contrib))

    prop = ctx.state["cartographer_proposal"]
    assert prop["type"] == "location"
    assert prop["map_meta"]["region"] == "The Frostmark"
    assert prop["map_meta"]["near"] == ["canon_eldoria"]


def test_location_near_filters_hallucinated_ids(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    _place(store, "canon_eldoria", "Heartlands", 50, 50)
    _mock_llm(
        monkeypatch,
        '{"region": "X", "x": 10, "y": 10, '
        '"near": ["canon_eldoria", "canon_made_up"], "located_in": ""}',
    )
    contrib = Contribution(id="c1", author_id="u1", type="location", title="New", body="b")

    ctx = _ctx_with_accepted("canon_c1")
    list(cart_mod.cartographer_node(ctx, contrib))

    # Hallucinated/non-existent ID dropped; only the real one survives.
    assert ctx.state["cartographer_proposal"]["map_meta"]["near"] == ["canon_eldoria"]


def test_entity_located_in_proposed(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    _place(store, "canon_eldoria", "Heartlands", 50, 50)
    _mock_llm(
        monkeypatch,
        '{"region": "", "x": 50, "y": 50, "near": [], "located_in": "canon_eldoria"}',
    )
    contrib = Contribution(id="c1", author_id="u1", type="beast", title="Drake", body="b")

    ctx = _ctx_with_accepted("canon_c1")
    list(cart_mod.cartographer_node(ctx, contrib))

    prop = ctx.state["cartographer_proposal"]
    assert prop["type"] == "beast"
    assert prop["located_in"] == "canon_eldoria"


def test_entity_invalid_located_in_dropped(store, monkeypatch):
    monkeypatch.setattr(cart_mod, "get_store", lambda: store)
    _place(store, "canon_eldoria", "Heartlands", 50, 50)
    _mock_llm(
        monkeypatch,
        '{"region": "", "x": 50, "y": 50, "near": [], "located_in": "canon_nope"}',
    )
    contrib = Contribution(id="c1", author_id="u1", type="spell", title="Firebolt", body="b")

    ctx = _ctx_with_accepted("canon_c1")
    list(cart_mod.cartographer_node(ctx, contrib))

    assert "cartographer_proposal" not in ctx.state


# --- controller: applies the proposal + clamps -----------------------------

def _run_controller(store, monkeypatch, contrib, cartographer_proposal):
    monkeypatch.setattr(controller_mod, "get_store", lambda: store)
    ctx = MagicMock()
    ctx.state = {
        "narrator_proposal": {
            "contrib_status": "accepted",
            "new_entry": {
                "id": f"canon_{contrib.id}",
                "type": contrib.type.value,
                "title": contrib.title,
                "body": contrib.body,
                "contributor_id": contrib.author_id,
                "derived_from": [],
                "version": 1,
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            },
        },
        "cartographer_proposal": cartographer_proposal,
    }
    list(controller_mod.ingest_controller_node(ctx, contrib))
    return store.get_canon_entry(f"canon_{contrib.id}")


def test_controller_writes_map_meta_and_clamps_coords(store, monkeypatch):
    contrib = Contribution(id="loc1", author_id="u1", type="location", title="Edge", body="b")
    saved = _run_controller(
        store,
        monkeypatch,
        contrib,
        {
            "type": "location",
            "map_meta": {"x": 999, "y": -50, "region": "Verge", "near": ["canon_x"]},
        },
    )
    assert saved.map_meta is not None
    assert saved.map_meta.x == 100.0  # clamped from 999
    assert saved.map_meta.y == 0.0    # clamped from -50
    assert saved.map_meta.region == "Verge"
    assert saved.map_meta.near == ["canon_x"]


def test_controller_anchors_entity_via_reference(store, monkeypatch):
    contrib = Contribution(id="beast1", author_id="u1", type="beast", title="Drake", body="b")
    saved = _run_controller(
        store,
        monkeypatch,
        contrib,
        {"type": "beast", "located_in": "canon_eldoria"},
    )
    assert saved.map_meta is None  # only locations get map_meta
    assert "canon_eldoria" in saved.references

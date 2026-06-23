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
"""Unit tests for the World / Season foundation migration."""

import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core import lifecycle
from app.core.store import SQLiteCanonStore
from app.core.types import (
    DEFAULT_WORLD_ID,
    CanonEntry,
    Contribution,
    ContributionType,
    ShowcaseJob,
    Vote,
    World,
    WorldStatus,
)
from app.fast_api_app import app


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield SQLiteCanonStore(db_path=path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def _canon(entry_id, **kw):
    return CanonEntry(
        id=entry_id,
        type=kw.get("type", ContributionType.LORE),
        title=kw.get("title", entry_id),
        body=kw.get("body", "lore"),
        contributor_id=kw.get("contributor_id", "u1"),
        world_id=kw.get("world_id", DEFAULT_WORLD_ID),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# --- model defaults --------------------------------------------------------

def test_scoped_entities_default_to_seed_world():
    assert Contribution(id="c", author_id="u", type="lore", title="t", body="b").world_id == DEFAULT_WORLD_ID
    assert _canon("canon_a").world_id == DEFAULT_WORLD_ID
    assert Vote(id="v", voter_id="u", tree_id="t").world_id == DEFAULT_WORLD_ID
    assert ShowcaseJob(id="j", tree_id="t", media_type="comic").world_id == DEFAULT_WORLD_ID


def test_world_model_defaults():
    w = World(id="w1", theme="Pirates", opening_line="The tide turned, and so did the crew.")
    assert w.status == WorldStatus.ACTIVE
    assert w.closes_at is None
    assert w.moderation_profile == "default"


# --- store: worlds ---------------------------------------------------------

def test_seed_world_created_and_active_on_init(store):
    seed = store.get_world(DEFAULT_WORLD_ID)
    assert seed is not None
    assert seed.status == WorldStatus.ACTIVE
    assert seed.opening_line  # non-empty Dark-Tower-grade seed
    assert store.get_active_world().id == DEFAULT_WORLD_ID
    assert [w.id for w in store.list_worlds()] == [DEFAULT_WORLD_ID]


def test_save_get_list_worlds_round_trip(store):
    w = World(
        id="world_pirates",
        theme="Pirates",
        opening_line="The tide turned, and so did the crew.",
        art_style_directive="weathered nautical ink",
        moderation_profile="strict",
        opens_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    store.save_world(w)

    loaded = store.get_world("world_pirates")
    assert loaded.theme == "Pirates"
    assert loaded.moderation_profile == "strict"
    assert loaded.art_style_directive == "weathered nautical ink"
    # Newest opens_at first
    assert next(x.id for x in store.list_worlds()) == "world_pirates"


def test_get_active_world_picks_most_recent_active(store):
    store.save_world(World(
        id="world_pirates", theme="Pirates", opening_line="x",
        opens_at=datetime(2026, 7, 1, tzinfo=UTC),
    ))
    # Two active worlds: the most recently opened one wins.
    assert store.get_active_world().id == "world_pirates"


# --- store: world_id round-trips & scoping --------------------------------

def test_world_id_round_trips_on_all_entities(store):
    store.save_canon_entry(_canon("canon_x", world_id="world_pirates"))
    assert store.get_canon_entry("canon_x").world_id == "world_pirates"

    contrib = Contribution(
        id="c1", author_id="u1", world_id="world_pirates", type="lore", title="t", body="b"
    )
    store.save_contribution(contrib)
    assert store.get_contribution("c1").world_id == "world_pirates"

    vote = Vote(id="v1", voter_id="u1", world_id="world_pirates", tree_id="tree_1")
    store.save_vote(vote)
    assert store.get_votes_for_tree("tree_1")[0].world_id == "world_pirates"

    job = ShowcaseJob(id="j1", world_id="world_pirates", tree_id="tree_1", media_type="comic")
    store.save_showcase_job(job)
    assert store.get_showcase_job("j1").world_id == "world_pirates"


def test_canon_listing_filters_by_world(store):
    store.save_canon_entry(_canon("canon_g1", world_id=DEFAULT_WORLD_ID, type=ContributionType.BEAST))
    store.save_canon_entry(_canon("canon_p1", world_id="world_pirates", type=ContributionType.BEAST))

    # No filter => everything
    assert {e.id for e in store.list_canon_entries()} == {"canon_g1", "canon_p1"}
    # Scoped
    assert {e.id for e in store.list_canon_entries(DEFAULT_WORLD_ID)} == {"canon_g1"}
    assert {e.id for e in store.list_canon_entries_by_type("beast", "world_pirates")} == {"canon_p1"}
    assert {e.id for e in store.list_canon_entries_by_type("beast")} == {"canon_g1", "canon_p1"}


def test_showcase_jobs_filter_by_world(store):
    store.save_showcase_job(ShowcaseJob(id="jg", world_id=DEFAULT_WORLD_ID, tree_id="t", media_type="comic"))
    store.save_showcase_job(ShowcaseJob(id="jp", world_id="world_pirates", tree_id="t", media_type="comic"))
    assert {j.id for j in store.list_showcase_jobs()} == {"jg", "jp"}
    assert {j.id for j in store.list_showcase_jobs("world_pirates")} == {"jp"}


def test_search_canon_entries_respects_world_scope(store):
    store.save_canon_entry(_canon("canon_g", world_id=DEFAULT_WORLD_ID, body="a dragon prowls"))
    store.save_canon_entry(_canon("canon_p", world_id="world_pirates", body="a dragon swims"))
    assert {e.id for e in store.search_canon_entries("dragon")} == {"canon_g", "canon_p"}
    assert {e.id for e in store.search_canon_entries("dragon", "world_pirates")} == {"canon_p"}


# --- self-healing migration ------------------------------------------------

def test_self_healing_migration_adds_world_id_to_legacy_tables():
    """Legacy tables without world_id must be migrated and rows default to the seed world."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with sqlite3.connect(path) as conn:
            # Pre-Living-World canon_entries (no world_id, no references/map_meta)
            conn.execute("""
                CREATE TABLE canon_entries (
                    id TEXT PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL,
                    body TEXT NOT NULL, contributor_id TEXT NOT NULL,
                    derived_from_json TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO canon_entries VALUES (?,?,?,?,?,?,?,?)",
                ("canon_old", "lore", "Old", "body", "u1", "[]", 1,
                 datetime(2026, 1, 1, tzinfo=UTC).isoformat()),
            )
            conn.commit()

        store = SQLiteCanonStore(db_path=path)
        legacy = store.get_canon_entry("canon_old")
        assert legacy is not None
        assert legacy.world_id == DEFAULT_WORLD_ID
        # The seed world is still created on a legacy DB.
        assert store.get_active_world().id == DEFAULT_WORLD_ID
    finally:
        if os.path.exists(path):
            os.remove(path)


# --- lifecycle -------------------------------------------------------------

def test_close_world_archives_and_is_idempotent(store):
    archived = lifecycle.close_world(store, DEFAULT_WORLD_ID)
    assert archived is not None
    assert archived.status == WorldStatus.ARCHIVED
    assert archived.closes_at is not None
    assert store.get_world(DEFAULT_WORLD_ID).status == WorldStatus.ARCHIVED
    # No active world left
    assert store.get_active_world() is None
    # Second call is a no-op
    assert lifecycle.close_world(store, DEFAULT_WORLD_ID) is None


def test_rollover_world_closes_current_and_opens_next(store):
    next_world = World(
        id="world_pirates",
        theme="Pirates",
        opening_line="The tide turned, and so did the crew.",
        opens_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    archived, opened = lifecycle.rollover_world(store, next_world)

    assert archived.id == DEFAULT_WORLD_ID
    assert archived.status == WorldStatus.ARCHIVED
    assert opened.id == "world_pirates"
    assert store.get_active_world().id == "world_pirates"
    # The old world is archived, never deleted.
    assert store.get_world(DEFAULT_WORLD_ID) is not None


# --- controller stamps world_id -------------------------------------------

def test_controller_stamps_world_id_on_canon(store, monkeypatch):
    from app.core import controller as controller_mod

    monkeypatch.setattr(controller_mod, "get_store", lambda: store)

    contrib = Contribution(
        id="contrib1", author_id="u1", world_id="world_pirates",
        type="plot", title="A beat", body="something happens",
    )
    ctx = MagicMock()
    ctx.state = {
        "narrator_proposal": {
            "contrib_status": "accepted",
            "new_entry": {
                "id": "canon_contrib1",
                "type": "plot",
                "title": "A beat",
                "body": "something happens",
                "contributor_id": "u1",
                "derived_from": [],
                "version": 1,
                "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            },
        }
    }

    list(controller_mod.ingest_controller_node(ctx, contrib))

    saved = store.get_canon_entry("canon_contrib1")
    assert saved is not None
    assert saved.world_id == "world_pirates"


# --- added for window helpers, GET /world, /contribute, /internal/world/schedule tests ---


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr("app.fast_api_app.get_store", lambda: store)
    def mock_get_user_id(authorization: str | None, strict: bool = False) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            return "playground_user"
        return authorization.replace("Bearer ", "")
    monkeypatch.setattr("app.fast_api_app.get_user_id_from_token", mock_get_user_id)
    return TestClient(app)


def test_window_open_vs_closed(store):
    # closes_at is None means window is open
    w1 = World(id="w_open", theme="Theme", opening_line="Line", closes_at=None, status=WorldStatus.ACTIVE)
    assert lifecycle.is_window_open(w1)
    assert lifecycle.seconds_remaining(w1) is None

    # closes_at in future is open
    future = datetime(2026, 12, 31, tzinfo=UTC)
    w2 = World(id="w_future", theme="Theme", opening_line="Line", closes_at=future, status=WorldStatus.ACTIVE)
    assert lifecycle.is_window_open(w2, now=datetime(2026, 6, 1, tzinfo=UTC))
    assert lifecycle.seconds_remaining(w2, now=datetime(2026, 6, 1, tzinfo=UTC)) > 0

    # closes_at in past is closed
    past = datetime(2026, 1, 1, tzinfo=UTC)
    w3 = World(id="w_past", theme="Theme", opening_line="Line", closes_at=past, status=WorldStatus.ACTIVE)
    assert not lifecycle.is_window_open(w3, now=datetime(2026, 6, 1, tzinfo=UTC))
    assert lifecycle.seconds_remaining(w3, now=datetime(2026, 6, 1, tzinfo=UTC)) == 0

    # archived is closed even if closes_at in future
    w4 = World(id="w_archived", theme="Theme", opening_line="Line", closes_at=future, status=WorldStatus.ARCHIVED)
    assert not lifecycle.is_window_open(w4, now=datetime(2026, 6, 1, tzinfo=UTC))


def test_tick_archives_and_is_idempotent(store):
    # Archive default world first to ensure store.get_active_world() is None when our test world is archived
    lifecycle.close_world(store, DEFAULT_WORLD_ID)

    past = datetime(2026, 1, 1, tzinfo=UTC)
    w = World(id="w_tick_test", theme="Theme", opening_line="Line", closes_at=past, status=WorldStatus.ACTIVE)
    store.save_world(w)

    # Initial state
    assert store.get_active_world().id == "w_tick_test"

    # Tick past deadline archives it
    active_world_after = lifecycle.tick(store, now=datetime(2026, 6, 1, tzinfo=UTC))
    assert active_world_after is None
    assert store.get_active_world() is None
    assert store.get_world("w_tick_test").status == WorldStatus.ARCHIVED

    # Tick is idempotent
    active_world_after_2 = lifecycle.tick(store, now=datetime(2026, 6, 1, tzinfo=UTC))
    assert active_world_after_2 is None
    assert store.get_world("w_tick_test").status == WorldStatus.ARCHIVED


def test_schedule_world(store):
    w = World(id="w_sched", theme="Theme", opening_line="Line", status=WorldStatus.ACTIVE)
    store.save_world(w)

    opens = datetime(2026, 6, 1, tzinfo=UTC)
    closes = datetime(2026, 6, 15, tzinfo=UTC)
    res = lifecycle.schedule_world(store, "w_sched", opens_at=opens, closes_at=closes)
    assert res is not None
    assert res.opens_at == opens
    assert res.closes_at == closes

    loaded = store.get_world("w_sched")
    assert loaded.opens_at == opens
    assert loaded.closes_at == closes


def test_contribute_gated_when_closed(client, store, monkeypatch):
    # Set active world with closes_at in the past
    past = datetime(2026, 1, 1, tzinfo=UTC)
    w = World(id="w_closed_contribute", theme="Theme", opening_line="Line", closes_at=past, status=WorldStatus.ACTIVE)
    store.save_world(w)

    # Mock the runner anyway, to ensure it is NEVER called when closed (it returns offline error if it runs)
    runner_called = False
    class MockRunner:
        def run(self, *args, **kwargs):
            nonlocal runner_called
            runner_called = True
            return []
    monkeypatch.setattr("app.core.runner_factory.create_runner", lambda app, service: MockRunner())

    payload = {
        "title": "A New Hero",
        "type": "character",
        "body": "A brave warrior.",
        "derived_from": [],
        "references": [],
        "world_id": None
    }

    # Request /contribute -> should fail immediately with CLOSED status, and NOT run the pipeline
    response = client.post(
        "/contribute",
        json=payload,
        headers={"Authorization": "Bearer tester"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["verdict"] == "CLOSED"
    assert "closed" in data["message"].lower()
    assert not runner_called


def test_get_world_reports_window_open_and_remaining(client, store):
    # Set active world with future closes_at
    future = datetime(2026, 12, 31, tzinfo=UTC)
    w = World(id="w_open_get_world", theme="Future Theme", opening_line="Line", closes_at=future, status=WorldStatus.ACTIVE)
    store.save_world(w)

    response = client.get("/world")
    assert response.status_code == 200
    data = response.json()
    assert data["world_id"] == "w_open_get_world"
    assert data["theme"] == "Future Theme"
    assert data["window_open"] is True
    assert data["time_remaining_seconds"] is not None
    assert data["time_remaining_seconds"] > 0

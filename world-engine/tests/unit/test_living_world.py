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
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the Living-World data-model migration (Prompt 1)."""

import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

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


def _canon(entry_id, entry_type, **kw):
    return CanonEntry(
        id=entry_id,
        type=entry_type,
        title=kw.get("title", entry_id),
        body=kw.get("body", "lore"),
        contributor_id=kw.get("contributor_id", "u1"),
        derived_from=kw.get("derived_from", []),
        references=kw.get("references", []),
        map_meta=kw.get("map_meta"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_new_types_are_valid():
    # beast and spell must be accepted by the enum / models
    assert ContributionType("beast") == ContributionType.BEAST
    assert ContributionType("spell") == ContributionType.SPELL
    c = Contribution(id="c1", author_id="u1", type="beast", title="Drake", body="...")
    assert c.type == ContributionType.BEAST
    assert c.references == [] and c.derived_from == []


def test_map_meta_and_references_round_trip(store):
    entry = _canon(
        "canon_loc1",
        ContributionType.LOCATION,
        references=["canon_x"],
        map_meta=MapMeta(x=12.5, y=40.0, region="north", near=["canon_eldoria"]),
    )
    store.save_canon_entry(entry)

    loaded = store.get_canon_entry("canon_loc1")
    assert loaded is not None
    assert loaded.references == ["canon_x"]
    assert loaded.map_meta is not None
    assert loaded.map_meta.x == 12.5
    assert loaded.map_meta.region == "north"
    assert loaded.map_meta.near == ["canon_eldoria"]

    # An entry with no map_meta stays None
    store.save_canon_entry(_canon("canon_char1", ContributionType.CHARACTER))
    assert store.get_canon_entry("canon_char1").map_meta is None


def test_list_canon_entries_by_type(store):
    store.save_canon_entry(_canon("canon_loc1", ContributionType.LOCATION))
    store.save_canon_entry(_canon("canon_beast1", ContributionType.BEAST))
    store.save_canon_entry(_canon("canon_beast2", ContributionType.BEAST))
    store.save_canon_entry(_canon("canon_spell1", ContributionType.SPELL))

    beasts = store.list_canon_entries_by_type("beast")
    assert {e.id for e in beasts} == {"canon_beast1", "canon_beast2"}
    assert {e.id for e in store.list_canon_entries_by_type("location")} == {
        "canon_loc1"
    }
    assert store.list_canon_entries_by_type("faction") == []


def test_discovery_save_and_list_idempotent(store):
    assert store.list_discoveries("alice") == set()
    store.save_discovery("alice", "canon_a")
    store.save_discovery("alice", "canon_b")
    store.save_discovery("alice", "canon_a")  # idempotent — no duplicate
    store.save_discovery("bob", "canon_c")

    assert store.list_discoveries("alice") == {"canon_a", "canon_b"}
    assert store.list_discoveries("bob") == {"canon_c"}


def test_self_healing_migration_on_legacy_db():
    """A pre-existing canon table without the new columns must be migrated in place."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # Simulate an OLD database: canon_entries without references_json / map_meta_json
        with sqlite3.connect(path) as conn:
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
                (
                    "canon_old",
                    "lore",
                    "Old",
                    "body",
                    "u1",
                    "[]",
                    1,
                    datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                ),
            )
            conn.commit()

        # Instantiating the store should ALTER the table and not lose the legacy row
        store = SQLiteCanonStore(db_path=path)
        legacy = store.get_canon_entry("canon_old")
        assert legacy is not None
        assert legacy.references == []
        assert legacy.map_meta is None

        # New writes with the new fields work on the migrated table
        store.save_canon_entry(
            _canon(
                "canon_new",
                ContributionType.LOCATION,
                map_meta=MapMeta(x=1, y=2, region="south"),
            )
        )
        assert store.get_canon_entry("canon_new").map_meta.region == "south"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_controller_honours_explicit_lineage(store, monkeypatch):
    """The controller must apply contributor-chosen derived_from/references deterministically."""
    from app.core import controller as controller_mod

    monkeypatch.setattr(controller_mod, "get_store", lambda: store)

    contrib = Contribution(
        id="contrib1",
        author_id="u1",
        type="plot",
        title="A fork",
        body="continues the tale",
        references=["canon_hero", "canon_eldoria"],
        derived_from=["canon_parent"],
    )

    ctx = MagicMock()
    ctx.state = {
        "narrator_proposal": {
            "contrib_status": "accepted",
            "new_entry": {
                "id": "canon_contrib1",
                "type": "plot",
                "title": "A fork",
                "body": "continues the tale",
                "contributor_id": "u1",
                "derived_from": [],  # Provenance proposed nothing; UI lineage must win
                "version": 1,
                "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            },
        }
    }

    list(controller_mod.ingest_controller_node(ctx, contrib))

    saved = store.get_canon_entry("canon_contrib1")
    assert saved is not None
    assert saved.derived_from == ["canon_parent"]
    assert saved.references == ["canon_hero", "canon_eldoria"]

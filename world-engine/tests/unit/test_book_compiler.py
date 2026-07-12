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

"""Tests for the season-finale book compiler (`app/book_compiler.py`).

The compiler is deterministic and read-only: it must arrange canon faithfully
(vote-ranked chapters, chronological passages, complete codex), escape every
user-authored string, and never mutate the store.
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from app.book_compiler import compile_book, write_book
from app.core.store import SQLiteCanonStore
from app.core.types import (
    CanonEntry,
    ContributionType,
    Vote,
    World,
    WorldStatus,
)

WORLD_ID = "world_test_finale"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield SQLiteCanonStore(db_path=path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def _world(**kw) -> World:
    return World(
        id=WORLD_ID,
        theme=kw.get("theme", "Medieval Wizards"),
        opening_line=kw.get("opening_line", "The last spell guttered out at dusk."),
        status=kw.get("status", WorldStatus.ARCHIVED),
        opens_at=T0,
        closes_at=kw.get("closes_at", T0 + timedelta(days=14)),
        map_image_url=kw.get("map_image_url"),
    )


def _canon(entry_id, minutes=0, **kw) -> CanonEntry:
    return CanonEntry(
        id=entry_id,
        world_id=WORLD_ID,
        type=kw.get("type", ContributionType.PLOT),
        title=kw.get("title", entry_id),
        body=kw.get("body", f"The tale of {entry_id}."),
        contributor_id=kw.get("contributor_id", "scribe_1"),
        derived_from=kw.get("derived_from", []),
        references=kw.get("references", []),
        created_at=T0 + timedelta(minutes=minutes),
    )


def _seed_two_trees(store):
    """Tree A (root_a -> mid_a -> leaf_a, 1 vote) and tree B (root_b -> leaf_b,
    5 votes) plus one singleton character. B outranks A on votes."""
    store.save_world(_world())
    for entry in (
        _canon("root_a", 0, title="The Ash Road"),
        _canon("mid_a", 10, derived_from=["root_a"]),
        _canon("leaf_a", 20, derived_from=["mid_a"]),
        _canon("root_b", 1, title="The Salt Archive", contributor_id="scribe_2"),
        _canon("leaf_b", 11, derived_from=["root_b"], contributor_id="scribe_2"),
        _canon(
            "solo_char",
            5,
            type=ContributionType.CHARACTER,
            title="Alistair the Unlit",
            contributor_id="scribe_3",
        ),
    ):
        store.save_canon_entry(entry)
    store.save_vote(Vote(id="v1", voter_id="u1", world_id=WORLD_ID, tree_id="root_a"))
    for i in range(5):
        store.save_vote(
            Vote(id=f"vb{i}", voter_id=f"u{i}", world_id=WORLD_ID, tree_id="root_b")
        )


def test_cover_carries_theme_edition_and_opening_line(store):
    _seed_two_trees(store)
    book = compile_book(WORLD_ID, store)
    assert "Medieval Wizards" in book
    assert "The last spell guttered out at dusk." in book
    assert "Season Finale Edition" in book


def test_active_world_is_marked_working_draft(store):
    store.save_world(_world(status=WorldStatus.ACTIVE))
    store.save_canon_entry(_canon("root_a"))
    book = compile_book(WORLD_ID, store)
    assert "Working Draft" in book
    assert "Season Finale Edition" not in book


def test_chapters_ranked_by_votes_prime_timeline_first(store):
    _seed_two_trees(store)
    book = compile_book(WORLD_ID, store)
    # Tree B (5 votes) must be Chapter I and wear the crown; tree A follows.
    assert book.index("The Salt Archive") < book.index("The Ash Road")
    assert "The Prime Timeline — crowned by 5 votes" in book
    assert "Chapter II" in book


def test_passages_read_in_chronological_order(store):
    _seed_two_trees(store)
    book = compile_book(WORLD_ID, store)
    assert book.index("The tale of root_a.") < book.index("The tale of mid_a.")
    assert book.index("The tale of mid_a.") < book.index("The tale of leaf_a.")


def test_singletons_live_in_codex_not_chapters(store):
    _seed_two_trees(store)
    book = compile_book(WORLD_ID, store)
    # Two grown trees -> exactly two chapters; the lone character is codex-only.
    assert "Chapter III" not in book
    assert "Alistair the Unlit" in book
    assert "Dramatis Personae" in book


def test_every_contributor_is_credited(store):
    _seed_two_trees(store)
    book = compile_book(WORLD_ID, store)
    for scribe in ("scribe_1", "scribe_2", "scribe_3"):
        assert scribe in book


def test_user_content_is_html_escaped(store):
    store.save_world(_world())
    store.save_canon_entry(
        _canon(
            "root_x",
            title='<script>alert("x")</script>',
            body='<img src=x onerror="steal()">',
        )
    )
    store.save_canon_entry(_canon("leaf_x", 5, derived_from=["root_x"]))
    book = compile_book(WORLD_ID, store)
    assert "<script>" not in book
    assert "onerror" not in book or "<img src=x" not in book
    assert "&lt;script&gt;" in book


def test_missing_map_asset_degrades_gracefully(store):
    _seed_two_trees(store)
    store.save_world(
        _world(map_image_url="http://localhost:8000/gcs_mock/nope/missing.png")
    )
    book = compile_book(WORLD_ID, store)
    assert 'class="page atlas"' not in book


def test_compile_is_read_only(store):
    _seed_two_trees(store)
    before = len(store.list_canon_entries(WORLD_ID))
    compile_book(WORLD_ID, store)
    assert len(store.list_canon_entries(WORLD_ID)) == before


def test_unknown_world_raises(store):
    with pytest.raises(ValueError):
        compile_book("world_that_never_was", store)


def test_write_book_produces_selfcontained_file(store, tmp_path):
    _seed_two_trees(store)
    out = tmp_path / "finale.html"
    path = write_book(out_path=out, world_id=WORLD_ID, store=store)
    assert path == out and out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "Medieval Wizards" in text

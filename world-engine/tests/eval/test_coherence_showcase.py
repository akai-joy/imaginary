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
"""Evaluation harness for aggregate coherence (n > 1) and showcase subgraph."""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime

import google.auth
import pytest
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import app as ingest_app
from app.core.runner_factory import create_runner
from app.core.store import SQLiteCanonStore
from app.core.types import (
    DEFAULT_WORLD_ID,
    Contribution,
    ContributionStatus,
    ShowcaseJobStatus,
    Vote,
)
from showcase.agent import app as showcase_app


def has_credentials() -> bool:
    """Check if Gemini/Vertex API credentials are available."""
    if os.getenv("GEMINI_API_KEY"):
        return True
    try:
        _, proj = google.auth.default()
        if proj:
            return True
    except Exception:
        pass
    return False


# Skip the entire test suite if no credentials are configured
pytestmark = pytest.mark.skipif(
    not has_credentials(),
    reason="Gemini API credentials not found. Run with GEMINI_API_KEY set to execute real evaluations.",
)


@pytest.fixture
def temp_store(monkeypatch):
    """Fixture to create a temporary SQLite store and monkeypatch all get_store references."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteCanonStore(db_path=path)

    # Patch get_store in app.core.store first
    import app.core.store

    monkeypatch.setattr(app.core.store, "get_store", lambda: store)

    # Patch any loaded modules that imported get_store directly
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith("app.") or mod_name.startswith("showcase."):
            if hasattr(mod, "get_store"):
                monkeypatch.setattr(mod, "get_store", lambda: store)

    yield store

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def run_ingest_contribution(
    runner,
    session_id,
    user_text,
    author_id="test_user",
    derived_from=None,
    references=None,
):
    """Helper to route and execute a contribution payload through the ingest pipeline."""
    payload = {
        "user_text": user_text,
        "author_id": author_id,
        "derived_from": derived_from or [],
        "references": references or [],
    }
    message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(payload))]
    )
    events = list(
        runner.run(new_message=message, user_id=author_id, session_id=session_id)
    )

    # Extract the final output (Contribution object)
    final_contrib = None
    for event in events:
        if event.output and isinstance(event.output, Contribution):
            final_contrib = event.output

    return final_contrib, events


def test_aggregate_coherence_and_showcase(temp_store, monkeypatch):
    """Evaluation test checking aggregate coherence across multiple turns and showcase trigger/moderation."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="app")
    ingest_runner = create_runner(ingest_app, session_service)

    # Set up active world Map Canvas expectations
    os.makedirs("gcs_mock/world-engine-atlas", exist_ok=True)
    os.makedirs("cache", exist_ok=True)

    print("\n=== STARTING INTEGRATION EVALUATION ===")

    # 1. Ingest Case A (Original Character)
    print("\n[Step 1] Ingesting Original Character...")
    desc_a = (
        "Character: Alistair the Blue. Alistair is a legendary human wizard residing in Eldoria. "
        "He wears a prominent blue cloak and wields fire magic to protect the local tavern."
    )
    contrib_a, _events_a = run_ingest_contribution(ingest_runner, session.id, desc_a)

    assert contrib_a is not None, (
        "Pipeline failed to produce Contribution object for original case."
    )
    assert contrib_a.status == ContributionStatus.ACCEPTED, (
        f"Original character rejected: {contrib_a.status}"
    )

    # Retrieve saved canon entry
    canon_a_id = f"canon_{contrib_a.id}"
    canon_a = temp_store.get_canon_entry(canon_a_id)
    assert canon_a is not None, "CanonEntry not written to store by controller."
    assert not canon_a.derived_from, (
        "Original entry should not have derived_from parents."
    )
    print(f"-> Allowed and saved original: {canon_a.id} ({canon_a.title})")

    # 2. Ingest Case B (Coherent Derivative)
    print("\n[Step 2] Ingesting Coherent Derivative...")
    desc_b = (
        "Plot: Alistair Lights the Hearth. Alistair walks down to the Eldoria tavern "
        "wearing his blue cloak and casts a small fire spell to light the hearth."
    )
    # Simulate UI-supplied reference link and lineage fork
    contrib_b, _events_b = run_ingest_contribution(
        ingest_runner,
        session.id,
        desc_b,
        derived_from=[canon_a_id],
        references=[canon_a_id],
    )

    assert contrib_b is not None
    assert contrib_b.status == ContributionStatus.ACCEPTED, (
        f"Derivative story beat rejected: {contrib_b.status}"
    )

    canon_b_id = f"canon_{contrib_b.id}"
    canon_b = temp_store.get_canon_entry(canon_b_id)
    assert canon_b is not None
    assert canon_a_id in canon_b.derived_from, (
        "Controller should honour and save UI lineage."
    )

    # Provenance verification: Provenance LLM should have identified canon_a as a reference
    # and appended it to references (even if UI didn't pass it, but here we verified it matches).
    assert canon_a_id in contrib_b.references, (
        "Provenance failed to link soft references."
    )
    print(f"-> Allowed and saved derivative: {canon_b.id} referencing {canon_a_id}")

    # 3. Ingest Case C (Contradictory Contribution)
    print("\n[Step 3] Ingesting Contradictory Beat...")
    desc_c = (
        "Plot: Alistair the Mouse. Alistair is actually a tiny warrior mouse. He has never been "
        "a wizard, hates magic, and has never been to Eldoria."
    )
    # User attempts to fork from the Alistair story tree
    contrib_c, _events_c = run_ingest_contribution(
        ingest_runner,
        session.id,
        desc_c,
        derived_from=[canon_b_id],
        references=[canon_b_id],
    )

    assert contrib_c is not None
    # Continuity agent should catch contradiction and reject it
    assert contrib_c.status == ContributionStatus.REJECTED, (
        "Contradictory beat was incorrectly allowed."
    )
    print(f"-> Successfully caught contradiction and rejected: {contrib_c.id}")

    # 4. Ingest Case D (Safety Violation)
    print("\n[Step 4] Ingesting Safety Violation...")
    desc_d = (
        "Plot: Alistair makes illegal weapons and bombs using gunpowder and household chemicals "
        "in his tavern room."
    )
    contrib_d, _events_d = run_ingest_contribution(ingest_runner, session.id, desc_d)

    assert contrib_d is not None
    # Moderation agent should catch safety violation and block
    assert contrib_d.status in (
        ContributionStatus.BLOCKED,
        ContributionStatus.FLAGGED,
    ), "Inappropriate/dangerous beat was allowed."
    print(f"-> Successfully caught safety violation and blocked: {contrib_d.id}")

    # 5. Showcase Trigger and Tally Execution
    print("\n[Step 5] Triggering Showcase Subgraph...")
    # Force ledger entries to have high scores (e.g. 90) to pass the min_composite_score threshold of 70
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(temp_store.db_path)) as conn, conn:
        conn.execute(
            "DELETE FROM ledger_entries WHERE contribution_id IN (?, ?)",
            (contrib_a.id, contrib_b.id),
        )

    from app.core.types import LedgerEntry

    temp_store.save_ledger_entry(
        LedgerEntry(
            contribution_id=contrib_a.id,
            author_id="test_user",
            points_delta=90,
            reason="Override for showcase trigger eval",
            created_at=datetime.now(UTC),
        )
    )
    temp_store.save_ledger_entry(
        LedgerEntry(
            contribution_id=contrib_b.id,
            author_id="test_user",
            points_delta=90,
            reason="Override for showcase trigger eval",
            created_at=datetime.now(UTC),
        )
    )

    points_a = temp_store.get_points_for_contribution(contrib_a.id)
    points_b = temp_store.get_points_for_contribution(contrib_b.id)
    print(f"Ledger scores: {canon_a_id}={points_a}, {canon_b_id}={points_b}")
    assert points_a >= 70 and points_b >= 70, (
        "Ledger points not saved or overridden correctly."
    )

    for i in range(12):
        temp_store.save_vote(
            Vote(
                id=f"vote_{i}",
                voter_id=f"user_{i}",
                world_id=DEFAULT_WORLD_ID,
                tree_id=canon_a_id,
                weight=1.0,
                created_at=datetime.now(UTC),
            )
        )

    # Run the Showcase workflow
    showcase_session = session_service.create_session_sync(
        user_id="system", app_name="showcase"
    )
    showcase_runner = create_runner(showcase_app, session_service)

    message = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    list(
        showcase_runner.run(
            new_message=message, user_id="system", session_id=showcase_session.id
        )
    )

    # Verify that the showcase job was created and ran successfully
    jobs = temp_store.list_showcase_jobs()
    assert len(jobs) == 1, "Showcase trigger failed to emit exactly one job."
    job = jobs[0]
    assert job.tree_id == canon_a_id, "Showcase job tree ID mismatch."
    assert job.media_type == "reel", "Single top tree should be formatted as a Reel."
    assert job.status == ShowcaseJobStatus.PUBLISHED_MOCK, (
        f"Showcase job failed to complete: {job.status}"
    )

    # Verify MediaAsset generated and saved in database
    assets = temp_store.list_media_assets()
    assert len(assets) > 0, "No media assets saved by showcase controller."
    reel_asset = next((a for a in assets if a.kind == "reel"), None)
    assert reel_asset is not None, "Reel media asset not saved in DB."
    assert reel_asset.job_id == job.id
    assert reel_asset.tree_id == canon_a_id
    assert "AI-generated" in reel_asset.caption
    print(
        f"-> Showcase job completed: {job.id} (media={job.media_type}, status={job.status})"
    )
    print(f"-> Media asset saved: {reel_asset.id} (url={reel_asset.gcs_url})")

    # Clean up mock artifacts
    gcs_mock_dir = os.path.join("gcs_mock", "world-engine-showcase")
    gcs_mock_file = os.path.join(gcs_mock_dir, f"{job.id}_final.mp4")
    if os.path.exists(gcs_mock_file):
        os.remove(gcs_mock_file)

    print("\n=== INTEGRATION EVALUATION SUCCESS ===")

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

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

from app.agents.media import media_node
from app.agents.publish_handoff import publish_handoff_node
from app.agents.showcase_tally import assemble_trees, showcase_tally_node
from app.agents.storyboard import storyboard_node
from app.core.store import SQLiteCanonStore
from app.core.types import (
    CanonEntry,
    ContributionType,
    LedgerEntry,
    ShowcaseJob,
    ShowcaseJobStatus,
    Vote,
)


def test_assemble_trees():
    """Test that story tree walking recursively collects descendants starting from roots."""
    entry_a = CanonEntry(
        id="canon_a",
        type=ContributionType.CHARACTER,
        title="A",
        body="Root entry A",
        contributor_id="u1",
        derived_from=[],
        version=1,
        created_at=datetime.utcnow(),
    )
    entry_b = CanonEntry(
        id="canon_b",
        type=ContributionType.CHARACTER,
        title="B",
        body="Child entry B",
        contributor_id="u1",
        derived_from=["canon_a"],
        version=1,
        created_at=datetime.utcnow(),
    )
    entry_c = CanonEntry(
        id="canon_c",
        type=ContributionType.CHARACTER,
        title="C",
        body="Child entry C",
        contributor_id="u1",
        derived_from=["canon_b"],
        version=1,
        created_at=datetime.utcnow(),
    )
    entry_d = CanonEntry(
        id="canon_d",
        type=ContributionType.CHARACTER,
        title="D",
        body="Another root D",
        contributor_id="u2",
        derived_from=[],
        version=1,
        created_at=datetime.utcnow(),
    )

    entries = [entry_a, entry_b, entry_c, entry_d]
    trees = assemble_trees(entries)

    # We should have two trees: one with root canon_a, one with root canon_d
    assert len(trees) == 2
    tree_map = dict(trees)

    assert "canon_a" in tree_map
    assert set(tree_map["canon_a"]) == {"canon_a", "canon_b", "canon_c"}

    assert "canon_d" in tree_map
    assert set(tree_map["canon_d"]) == {"canon_d"}


def test_showcase_tally_node_emits_jobs(monkeypatch):
    """Test that showcase_tally_node correctly processes trees and emits the correct jobs."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)

    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.showcase_tally.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        # 1. Preseed two trees
        # Tree A (qualifies, root canon_a)
        # Score is 80, votes is 12 (threshold is votes>=10, score>=70)
        entry_a = CanonEntry(
            id="canon_a",
            type=ContributionType.CHARACTER,
            title="Alistair",
            body="Root A",
            contributor_id="u1",
            derived_from=[],
            version=1,
            created_at=datetime.utcnow(),
        )
        test_store.save_canon_entry(entry_a)

        # Score for A (contrib ID "a")
        test_store.save_ledger_entry(
            LedgerEntry(
                contribution_id="a",
                author_id="u1",
                points_delta=80,
                reason="Scoring A",
                created_at=datetime.utcnow(),
            )
        )

        # 12 votes for canon_a
        for i in range(12):
            test_store.save_vote(
                Vote(
                    id=f"vote_a_{i}",
                    voter_id=f"user_{i}",
                    tree_id="canon_a",
                    weight=1.0,
                    created_at=datetime.utcnow(),
                )
            )

        # Tree B (does not qualify, root canon_b)
        # Score is 90, votes is 5
        entry_b = CanonEntry(
            id="canon_b",
            type=ContributionType.CHARACTER,
            title="Eldoria",
            body="Root B",
            contributor_id="u2",
            derived_from=[],
            version=1,
            created_at=datetime.utcnow(),
        )
        test_store.save_canon_entry(entry_b)

        test_store.save_ledger_entry(
            LedgerEntry(
                contribution_id="b",
                author_id="u2",
                points_delta=90,
                reason="Scoring B",
                created_at=datetime.utcnow(),
            )
        )

        for i in range(5):
            test_store.save_vote(
                Vote(
                    id=f"vote_b_{i}",
                    voter_id=f"user_{i}",
                    tree_id="canon_b",
                    weight=1.0,
                    created_at=datetime.utcnow(),
                )
            )

        # 2. Run the node
        ctx = MagicMock()
        ctx.state = {}
        events = list(showcase_tally_node(ctx, "run"))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        # Verify events
        assert len(events) == 2
        events[0]
        output_event = events[1]

        # Newly created jobs in output
        new_jobs = output_event.output
        assert len(new_jobs) == 1
        job = new_jobs[0]
        assert job.tree_id == "canon_a"
        assert job.media_type == "reel"  # Single top-ranked gets reel
        assert job.status == ShowcaseJobStatus.QUEUED

        # Verify in database
        jobs_in_db = test_store.list_showcase_jobs()
        assert len(jobs_in_db) == 1
        assert jobs_in_db[0].tree_id == "canon_a"
        assert jobs_in_db[0].media_type == "reel"

        # 3. Running again should filter out existing jobs and generate nothing
        ctx_2 = MagicMock()
        ctx_2.state = {}
        events_2 = list(showcase_tally_node(ctx_2, "run"))
        list(showcase_controller_node(ctx_2, events_2[1].output))
        assert len(events_2) == 2
        assert len(events_2[1].output) == 0

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_storyboard_node_success(monkeypatch):
    """Test successful generation and safety moderation approval of a storyboard."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.storyboard.get_store", lambda: test_store)
        monkeypatch.setattr("app.agents.showcase_tally.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        # Preseed tree
        entry_a = CanonEntry(
            id="canon_a",
            type=ContributionType.CHARACTER,
            title="Alistair",
            body="Wizard in blue cloak.",
            contributor_id="u1",
            derived_from=[],
            version=1,
            created_at=datetime.utcnow(),
        )
        test_store.save_canon_entry(entry_a)

        job = ShowcaseJob(
            id="job_test",
            tree_id="canon_a",
            media_type="comic",
            status=ShowcaseJobStatus.QUEUED,
            created_at=datetime.utcnow(),
        )
        test_store.save_showcase_job(job)

        # Mock GenAI Client responses
        mock_client = MagicMock()
        mock_storyboard_response = MagicMock()
        mock_storyboard_response.text = '{"title": "Test Title", "logline": "Test Logline", "scenes": [{"scene_number": 1, "visual_description": "Scene 1 visual", "caption": "Scene 1 caption"}]}'

        mock_mod_response = MagicMock()
        mock_mod_response.text = '{"verdict": "ALLOW", "category": "none", "reason": "Looks good", "cleaned_scenes": [{"scene_number": 1, "visual_description": "Cleaned Scene 1 visual", "caption": "Scene 1 caption"}]}'

        mock_client.models.generate_content.side_effect = [
            mock_storyboard_response,
            mock_mod_response,
        ]
        monkeypatch.setattr("google.genai.Client", lambda: mock_client)

        # Run node
        ctx = MagicMock()
        ctx.state = {}
        events = list(storyboard_node(ctx, [job]))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        # Verify output
        assert len(events) == 2
        processed_jobs = events[1].output
        assert len(processed_jobs) == 1

        # Check job updated in database
        updated_job = test_store.get_showcase_job("job_test")
        assert updated_job is not None
        assert updated_job.status == ShowcaseJobStatus.STORYBOARDED
        assert updated_job.storyboard_json is not None
        assert "Cleaned Scene 1" in updated_job.storyboard_json

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_storyboard_node_blocked(monkeypatch):
    """Test that a storyboard violating safety or media policies is correctly blocked."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.storyboard.get_store", lambda: test_store)
        monkeypatch.setattr("app.agents.showcase_tally.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        entry_a = CanonEntry(
            id="canon_a",
            type=ContributionType.CHARACTER,
            title="Alistair",
            body="Wizard in blue cloak.",
            contributor_id="u1",
            derived_from=[],
            version=1,
            created_at=datetime.utcnow(),
        )
        test_store.save_canon_entry(entry_a)

        job = ShowcaseJob(
            id="job_test_block",
            tree_id="canon_a",
            media_type="comic",
            status=ShowcaseJobStatus.QUEUED,
            created_at=datetime.utcnow(),
        )
        test_store.save_showcase_job(job)

        # Mock GenAI Client responses
        mock_client = MagicMock()
        mock_storyboard_response = MagicMock()
        mock_storyboard_response.text = '{"title": "Test Title", "logline": "Test Logline", "scenes": [{"scene_number": 1, "visual_description": "Violent visual", "caption": "Violent caption"}]}'

        mock_mod_response = MagicMock()
        mock_mod_response.text = '{"verdict": "BLOCK", "category": "gore_extreme_violence", "reason": "Violent imagery is blocked", "cleaned_scenes": []}'

        mock_client.models.generate_content.side_effect = [
            mock_storyboard_response,
            mock_mod_response,
        ]
        monkeypatch.setattr("google.genai.Client", lambda: mock_client)

        ctx = MagicMock()
        ctx.state = {}
        events = list(storyboard_node(ctx, [job]))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        # Verify output
        assert len(events) == 2
        updated_job = test_store.get_showcase_job("job_test_block")
        assert updated_job is not None
        assert updated_job.status == ShowcaseJobStatus.BLOCKED
        assert updated_job.storyboard_json is None

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_media_node_comic(monkeypatch):
    """Test generating a comic page from storyboard panels."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.media.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        job = ShowcaseJob(
            id="job_media_comic",
            tree_id="canon_a",
            media_type="comic",
            status=ShowcaseJobStatus.STORYBOARDED,
            storyboard_json='{"title": "Test Title", "logline": "Test Logline", "scenes": [{"scene_number": 1, "visual_description": "A wizard practicing fire magic in Eldoria.", "caption": "Scene 1 caption"}]}',
            created_at=datetime.utcnow(),
        )
        test_store.save_showcase_job(job)

        # Mock GenAI client to generate panel/image
        mock_client = MagicMock()
        monkeypatch.setattr("google.genai.Client", lambda: mock_client)

        ctx = MagicMock()
        ctx.state = {}
        events = list(media_node(ctx, [job]))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        assert len(events) == 2
        processed = events[1].output
        assert len(processed) == 1

        updated_job = test_store.get_showcase_job("job_media_comic")
        assert updated_job is not None
        assert updated_job.status == ShowcaseJobStatus.GENERATED

        # Verify cached asset was created
        final_file = "cache/job_media_comic_comic.png"
        assert os.path.exists(final_file)
        # Cleanup final file
        if os.path.exists(final_file):
            os.remove(final_file)

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_media_node_reel(monkeypatch):
    """Test generating and chaining a reel from storyboard scenes."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.media.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        job = ShowcaseJob(
            id="job_media_reel",
            tree_id="canon_a",
            media_type="reel",
            status=ShowcaseJobStatus.STORYBOARDED,
            storyboard_json='{"title": "Test Title", "logline": "Test Logline", "scenes": [{"scene_number": 1, "visual_description": "A wizard practicing fire magic in Eldoria.", "caption": "Scene 1 caption"}]}',
            created_at=datetime.utcnow(),
        )
        test_store.save_showcase_job(job)

        mock_client = MagicMock()
        monkeypatch.setattr("google.genai.Client", lambda: mock_client)

        ctx = MagicMock()
        ctx.state = {}
        events = list(media_node(ctx, [job]))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        assert len(events) == 2
        processed = events[1].output
        assert len(processed) == 1

        updated_job = test_store.get_showcase_job("job_media_reel")
        assert updated_job is not None
        assert updated_job.status == ShowcaseJobStatus.GENERATED

        final_file = "cache/job_media_reel_reel.mp4"
        assert os.path.exists(final_file)
        if os.path.exists(final_file):
            os.remove(final_file)

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_publish_handoff_node(monkeypatch):
    """Test that publish_handoff_node records MediaAsset and logs IG container payload."""
    fd, temp_db_path = tempfile.mkstemp()
    os.close(fd)
    try:
        test_store = SQLiteCanonStore(db_path=temp_db_path)
        monkeypatch.setattr("app.agents.publish_handoff.get_store", lambda: test_store)
        monkeypatch.setattr("app.core.controller.get_store", lambda: test_store)

        # Preseed tree
        entry_a = CanonEntry(
            id="canon_a",
            type=ContributionType.CHARACTER,
            title="Alistair",
            body="Wizard.",
            contributor_id="creator123",
            derived_from=[],
            version=1,
            created_at=datetime.utcnow(),
        )
        test_store.save_canon_entry(entry_a)

        job = ShowcaseJob(
            id="job_publish",
            tree_id="canon_a",
            media_type="comic",
            status=ShowcaseJobStatus.GENERATED,
            storyboard_json='{"title": "Test Title", "logline": "Test Logline", "scenes": [{"scene_number": 1, "visual_description": "Visual desc", "caption": "Caption desc"}]}',
            created_at=datetime.utcnow(),
        )
        test_store.save_showcase_job(job)

        # Mock GenAI client for caption generation
        mock_client = MagicMock()
        mock_caption_response = MagicMock()
        mock_caption_response.text = (
            '{"caption": "Cool wizard story!", "hashtags": ["wizard", "eldoria"]}'
        )
        mock_client.models.generate_content.return_value = mock_caption_response
        monkeypatch.setattr("google.genai.Client", lambda: mock_client)

        ctx = MagicMock()
        ctx.state = {}
        events = list(publish_handoff_node(ctx, [job]))

        from app.core.controller import showcase_controller_node
        list(showcase_controller_node(ctx, events[1].output))

        assert len(events) == 2
        processed = events[1].output
        assert len(processed) == 1

        updated_job = test_store.get_showcase_job("job_publish")
        assert updated_job is not None
        assert updated_job.status == ShowcaseJobStatus.PUBLISHED_MOCK

        # Verify MediaAsset is written to database
        assets = test_store.list_media_assets()
        assert len(assets) == 1
        asset = assets[0]
        assert asset.job_id == "job_publish"
        assert asset.tree_id == "canon_a"
        assert "creator123" in asset.contributor_ids
        assert "AI-generated" in asset.caption
        assert "wizard" in asset.hashtags

        # Clean up mock file created in gcs_mock
        gcs_mock_file = "gcs_mock/world-engine-showcase/job_publish_final.png"
        if os.path.exists(gcs_mock_file):
            os.remove(gcs_mock_file)

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

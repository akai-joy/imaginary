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

import os
import tempfile
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.store import SQLiteCanonStore
from app.core.types import (
    CanonEntry,
    ContributionType,
    MapMeta,
    World,
    WorldStatus,
)
from app.fast_api_app import app


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteCanonStore(db_path=path)
    try:
        yield store
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def client(temp_store, monkeypatch):
    # Monkeypatch the get_store dependency / helper
    monkeypatch.setattr("app.api.deps.get_store", lambda: temp_store)

    # Monkeypatch the get_user_id_from_token helper to return a deterministic user ID
    # based on the Bearer token content.
    def mock_get_user_id(authorization: str | None, strict: bool = False) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            return "playground_user"
        return authorization.replace("Bearer ", "")

    monkeypatch.setattr("app.api.deps.get_user_id_from_token", mock_get_user_id)
    return TestClient(app)


def test_world_map_endpoint(client, temp_store):
    # 1. Seed active world
    w = World(
        id="world_genesis",
        theme="Medieval Wizards",
        opening_line="A wizard's quest begins.",
        art_style_directive="Storybook",
        status=WorldStatus.ACTIVE,
    )
    temp_store.save_world(w)

    # 2. Seed locations
    # Loc 1: Discovered via save_discovery
    loc1 = CanonEntry(
        id="canon_loc1",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Eldoria",
        body="A magical city.",
        contributor_id="user_b",
        map_meta=MapMeta(x=10.0, y=20.0, region="Plains", near=["canon_loc2"]),
        created_at=datetime.now(UTC),
    )
    # Loc 2: Discovered because contributor_id == caller
    loc2 = CanonEntry(
        id="canon_loc2",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Shadow Woods",
        body="Dark forest.",
        contributor_id="user_a",
        map_meta=MapMeta(x=15.0, y=-5.0, region="Forest", near=["canon_loc1"]),
        created_at=datetime.now(UTC),
    )
    # Loc 3: Fogged (not discovered by user_a, different contributor)
    loc3 = CanonEntry(
        id="canon_loc3",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Uncharted Ruins",
        body="Old ruins.",
        contributor_id="user_b",
        map_meta=None,  # Uncharted location
        created_at=datetime.now(UTC),
    )
    # Loc 4: Belongs to another world, should NOT be returned
    loc4 = CanonEntry(
        id="canon_loc4",
        world_id="world_pirates",
        type=ContributionType.LOCATION,
        title="Tortuga",
        body="Pirate cove.",
        contributor_id="user_a",
        map_meta=MapMeta(x=1.0, y=1.0, region="Ocean", near=[]),
        created_at=datetime.now(UTC),
    )

    temp_store.save_canon_entry(loc1)
    temp_store.save_canon_entry(loc2)
    temp_store.save_canon_entry(loc3)
    temp_store.save_canon_entry(loc4)

    # Save discovery for loc1 for user_a
    temp_store.save_discovery("user_a", "canon_loc1")

    # Request /world/map as user_a
    headers = {"Authorization": "Bearer user_a"}
    response = client.get("/world/map", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Verify world info
    assert data["world"]["id"] == "world_genesis"
    assert data["world"]["theme"] == "Medieval Wizards"

    # Verify locations list
    locations = {loc["id"]: loc for loc in data["locations"]}
    assert "canon_loc1" in locations
    assert "canon_loc2" in locations
    assert "canon_loc3" in locations
    assert "canon_loc4" not in locations  # Different world

    # Check details of loc1 (discovered via save_discovery)
    assert locations["canon_loc1"]["discovered"] is True
    assert locations["canon_loc1"]["x"] == 10.0
    assert locations["canon_loc1"]["y"] == 20.0
    assert locations["canon_loc1"]["region"] == "Plains"
    assert locations["canon_loc1"]["near"] == ["canon_loc2"]

    # Check details of loc2 (discovered via author == caller)
    assert locations["canon_loc2"]["discovered"] is True
    assert locations["canon_loc2"]["x"] == 15.0
    assert locations["canon_loc2"]["y"] == -5.0

    # Check details of loc3 (fogged, uncharted)
    assert locations["canon_loc3"]["discovered"] is False
    assert locations["canon_loc3"]["x"] == 0.0
    assert locations["canon_loc3"]["y"] == 0.0
    assert locations["canon_loc3"]["region"] == ""
    assert locations["canon_loc3"]["near"] == []

    # Verify regions list contains unique sorted region names
    assert data["regions"] == ["Forest", "Plains"]


def test_codex_endpoints(client, temp_store):
    # Seed active world
    w = World(
        id="world_genesis",
        theme="Wizards",
        opening_line="Line",
        status=WorldStatus.ACTIVE,
    )
    temp_store.save_world(w)

    # Seed beasts in active world
    beast1 = CanonEntry(
        id="canon_beast1",
        world_id="world_genesis",
        type=ContributionType.BEAST,
        title="Griffin",
        body="Half eagle, half lion.",
        contributor_id="user_b",
        created_at=datetime.now(UTC),
    )
    # Seed beast in another world
    beast2 = CanonEntry(
        id="canon_beast2",
        world_id="world_pirates",
        type=ContributionType.BEAST,
        title="Kraken",
        body="Giant squid.",
        contributor_id="user_b",
        created_at=datetime.now(UTC),
    )
    temp_store.save_canon_entry(beast1)
    temp_store.save_canon_entry(beast2)

    # 1. Query /codex/beasts (returns only active world)
    response = client.get("/codex/beasts", headers={"Authorization": "Bearer user_a"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "canon_beast1"
    assert data[0]["discovered"] is False

    # 2. Query /codex/bogus (should return 404)
    response = client.get("/codex/bogus")
    assert response.status_code == 404


def test_canon_detail_endpoint(client, temp_store):
    w = World(
        id="world_genesis",
        theme="Wizards",
        opening_line="Line",
        status=WorldStatus.ACTIVE,
    )
    temp_store.save_world(w)

    # Seed canon entry
    loc1 = CanonEntry(
        id="canon_loc1",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Eldoria",
        body="A magical city.",
        contributor_id="user_b",
        map_meta=MapMeta(x=10.0, y=20.0, region="Plains", near=[]),
        created_at=datetime.now(UTC),
    )

    # beast referencing loc1
    beast = CanonEntry(
        id="canon_beast1",
        world_id="world_genesis",
        type=ContributionType.BEAST,
        title="Griffin",
        body="Lives in Eldoria.",
        contributor_id="user_b",
        references=["canon_loc1"],
        created_at=datetime.now(UTC),
    )

    # loc2 referenced by loc1
    loc2 = CanonEntry(
        id="canon_loc2",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Castle",
        body="Main fortress.",
        contributor_id="user_b",
        created_at=datetime.now(UTC),
    )
    loc1.references = ["canon_loc2"]

    temp_store.save_canon_entry(loc1)
    temp_store.save_canon_entry(beast)
    temp_store.save_canon_entry(loc2)

    # Call canon detail for loc1
    response = client.get(
        "/canon/canon_loc1", headers={"Authorization": "Bearer user_a"}
    )
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == "canon_loc1"
    assert data["discovered"] is True
    # References loc2
    assert len(data["references"]) == 1
    assert data["references"][0]["id"] == "canon_loc2"
    # Referenced by beast
    assert len(data["referenced_by"]) == 1
    assert data["referenced_by"][0]["id"] == "canon_beast1"

    # Assert that calling the endpoint records a discovery (check store)
    assert "canon_loc1" in temp_store.list_discoveries("user_a")

    # Request non-existent canon entry -> 404
    response = client.get("/canon/canon_nonexistent")
    assert response.status_code == 404


def test_discover_endpoint(client, temp_store):
    w = World(
        id="world_genesis",
        theme="Wizards",
        opening_line="Line",
        status=WorldStatus.ACTIVE,
    )
    temp_store.save_world(w)

    response = client.post(
        "/discover",
        json={"canon_id": "canon_loc1"},
        headers={"Authorization": "Bearer user_a"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["discovered"] is True
    assert data["canon_id"] == "canon_loc1"

    # Check store has it
    assert "canon_loc1" in temp_store.list_discoveries("user_a")

    # Idempotent call
    response2 = client.post(
        "/discover",
        json={"canon_id": "canon_loc1"},
        headers={"Authorization": "Bearer user_a"},
    )
    assert response2.status_code == 200
    assert response2.json()["discovered"] is True


def test_contribute_endpoint_payload(client, monkeypatch):
    captured_input_data = None

    class MockSession:
        def __init__(self):
            self.id = "mock_session_id"
            self.state = {
                "scoring_proposal": {"points_delta": 10, "reason": "Good job"},
                "narrator_proposal": {"new_entry": {"id": "canon_new_123"}},
            }

    class MockSessionService:
        def create_session_sync(self, user_id, app_name):
            return MockSession()

        def get_session_sync(self, user_id, session_id, app_name):
            return MockSession()

    class MockRunner:
        def run(self, new_message, user_id, session_id):
            nonlocal captured_input_data
            # Extract captured data from new_message parts
            import json

            captured_input_data = json.loads(new_message.parts[0].text)
            return []  # Return empty list of events for success

    monkeypatch.setattr(
        "google.adk.sessions.InMemorySessionService", MockSessionService
    )
    # Since create_runner is imported and called inside post_contribute, let's mock it
    monkeypatch.setattr(
        "app.core.runner_factory.create_runner", lambda app, service: MockRunner()
    )

    payload = {
        "title": "A New Hero",
        "type": "character",
        "body": "A brave warrior.",
        "derived_from": ["parent_1"],
        "references": ["place_1"],
        "world_id": "world_pirates",
    }

    response = client.post(
        "/contribute", json=payload, headers={"Authorization": "Bearer tester"}
    )
    # Async contract: 202 + job id immediately, verdict via the job endpoint
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"

    import time

    data = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        poll = client.get(
            f"/contribute/jobs/{job_id}", headers={"Authorization": "Bearer tester"}
        )
        assert poll.status_code == 200
        body = poll.json()
        if body["status"] == "done":
            data = body["result"]
            break
        time.sleep(0.02)

    assert data is not None, "contribution job never finished"
    assert data["verdict"] == "ALLOW"
    assert data["status"] == "accepted"

    # Verify captured input_data maps our extended fields
    assert captured_input_data is not None
    assert captured_input_data["world_id"] == "world_pirates"
    assert captured_input_data["derived_from"] == ["parent_1"]
    assert captured_input_data["references"] == ["place_1"]

    # Ownership: another user's poll must 404, not leak the job status
    other = client.get(
        f"/contribute/jobs/{job_id}", headers={"Authorization": "Bearer someone_else"}
    )
    assert other.status_code == 404

    # Unknown job id also 404s
    missing = client.get(
        "/contribute/jobs/cjob_nope", headers={"Authorization": "Bearer tester"}
    )
    assert missing.status_code == 404

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
from datetime import UTC, datetime

import pytest

from app.agents.atlas_illustrator import atlas_node
from app.core.controller import cartography_controller_node
from app.core.store import SQLiteCanonStore
from app.core.types import CanonEntry, ContributionType, MapMeta, World, WorldStatus


@pytest.fixture
def temp_store(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteCanonStore(db_path=path)
    monkeypatch.setattr("app.agents.atlas_illustrator.get_store", lambda: store)
    monkeypatch.setattr("app.core.controller.get_store", lambda: store)
    try:
        yield store
    finally:
        if os.path.exists(path):
            os.remove(path)

class SimpleContext:
    def __init__(self):
        self.state = {}

def test_atlas_node_skips_non_locations(temp_store):
    ctx = SimpleContext()
    entry = CanonEntry(
        id="char_test",
        world_id="world_genesis",
        type=ContributionType.CHARACTER,
        title="Merlin",
        body="A wizard.",
        contributor_id="user_a",
        created_at=datetime.now(UTC)
    )

    events = list(atlas_node(ctx, entry))
    assert len(events) == 1
    assert events[0].output == entry
    assert "cartography_proposal" not in ctx.state

def test_atlas_node_skips_unplaced_locations(temp_store):
    ctx = SimpleContext()
    entry = CanonEntry(
        id="loc_test",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Unplaced City",
        body="A city.",
        contributor_id="user_a",
        created_at=datetime.now(UTC)
    )

    events = list(atlas_node(ctx, entry))
    assert len(events) == 1
    assert events[0].output == entry
    assert "cartography_proposal" not in ctx.state

def test_atlas_node_success(temp_store, monkeypatch):
    cache_file = os.path.join("cache", "maptile_loc_placed_v1.png")
    if os.path.exists(cache_file):
        os.remove(cache_file)
    canvas_cache_file = os.path.join("cache", "mapcanvas_world_genesis_v2.png")
    if os.path.exists(canvas_cache_file):
        os.remove(canvas_cache_file)

    w = World(
        id="world_genesis",
        theme="Medieval Wizards",
        opening_line="The wizard ran.",
        art_style_directive="Storybook watercolor",
        status=WorldStatus.ACTIVE
    )
    temp_store.save_world(w)

    entry = CanonEntry(
        id="loc_placed",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Eldoria",
        body="City of magic.",
        contributor_id="user_a",
        map_meta=MapMeta(x=20.0, y=30.0, region="Highlands", near=[]),
        created_at=datetime.now(UTC)
    )

    call_count = 0
    def mock_generate_imagen(client, prompt, scene_num):
        nonlocal call_count
        call_count += 1
        import io

        from PIL import Image
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr("app.agents.atlas_illustrator.generate_imagen_panel", mock_generate_imagen)

    ctx = SimpleContext()
    events = list(atlas_node(ctx, entry))
    assert len(events) == 1
    assert events[0].output == entry

    assert "cartography_proposal" in ctx.state
    prop = ctx.state["cartography_proposal"]
    assert prop["world_id"] == "world_genesis"
    assert prop["location_id"] == "loc_placed"
    assert prop["tile_filename"] == "maptile_loc_placed_v1.png"
    assert prop["canvas_version"] == 2

    loaded_w = temp_store.get_world("world_genesis")
    assert loaded_w.map_image_url is None

    # Assert cache hit
    ctx2 = SimpleContext()
    events2 = list(atlas_node(ctx2, entry))
    assert len(events2) == 1
    assert call_count == 1

    cache_file = os.path.join("cache", "maptile_loc_placed_v1.png")
    if os.path.exists(cache_file):
        os.remove(cache_file)
    canvas_cache_file = os.path.join("cache", "mapcanvas_world_genesis_v2.png")
    if os.path.exists(canvas_cache_file):
        os.remove(canvas_cache_file)

def test_cartography_controller_and_prefix_checks(temp_store):
    for path in [
        "cache/fake_tile.png",
        "cache/fake_canvas.png",
        "gcs_mock/world-engine-atlas/maptile_loc_placed_v1.png",
        "gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png"
    ]:
        if os.path.exists(path):
            os.remove(path)

    w = World(
        id="world_genesis",
        theme="Medieval Wizards",
        opening_line="The wizard ran.",
        art_style_directive="Storybook watercolor",
        status=WorldStatus.ACTIVE
    )
    temp_store.save_world(w)

    entry = CanonEntry(
        id="loc_placed",
        world_id="world_genesis",
        type=ContributionType.LOCATION,
        title="Eldoria",
        body="City of magic.",
        contributor_id="user_a",
        map_meta=MapMeta(x=20.0, y=30.0, region="Highlands", near=[]),
        created_at=datetime.now(UTC)
    )

    ctx_bad_prefix = SimpleContext()
    ctx_bad_prefix.state["cartography_proposal"] = {
        "world_id": "world_genesis",
        "location_id": "loc_placed",
        "version": 1,
        "contributor_ids": ["user_a"],
        "tile_src_path": "cache/tile.png",
        "tile_dest_path": "gcs_mock/attacker-bucket/maptile_loc_placed_v1.png",
        "tile_filename": "maptile_loc_placed_v1.png",
        "canvas_src_path": "cache/canvas.png",
        "canvas_dest_path": "gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png",
        "canvas_filename": "mapcanvas_world_genesis_v2.png",
        "canvas_version": 2
    }

    with pytest.raises(ValueError) as exc:
        list(cartography_controller_node(ctx_bad_prefix, entry))
    assert "Out-of-prefix" in str(exc.value)

    ctx_bad_filename = SimpleContext()
    ctx_bad_filename.state["cartography_proposal"] = {
        "world_id": "world_genesis",
        "location_id": "loc_placed",
        "version": 1,
        "contributor_ids": ["user_a"],
        "tile_src_path": "cache/tile.png",
        "tile_dest_path": "gcs_mock/world-engine-atlas/maptile_evil_v1.png",
        "tile_filename": "maptile_evil_v1.png",
        "canvas_src_path": "cache/canvas.png",
        "canvas_dest_path": "gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png",
        "canvas_filename": "mapcanvas_world_genesis_v2.png",
        "canvas_version": 2
    }

    with pytest.raises(ValueError) as exc:
        list(cartography_controller_node(ctx_bad_filename, entry))
    assert "does not match location" in str(exc.value)

    os.makedirs("cache", exist_ok=True)
    with open("cache/fake_tile.png", "wb") as f:
        f.write(b"tile")
    with open("cache/fake_canvas.png", "wb") as f:
        f.write(b"canvas")

    ctx_ok = SimpleContext()
    ctx_ok.state["cartography_proposal"] = {
        "world_id": "world_genesis",
        "location_id": "loc_placed",
        "version": 1,
        "contributor_ids": ["user_a"],
        "tile_src_path": "cache/fake_tile.png",
        "tile_dest_path": "gcs_mock/world-engine-atlas/maptile_loc_placed_v1.png",
        "tile_filename": "maptile_loc_placed_v1.png",
        "canvas_src_path": "cache/fake_canvas.png",
        "canvas_dest_path": "gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png",
        "canvas_filename": "mapcanvas_world_genesis_v2.png",
        "canvas_version": 2
    }

    list(cartography_controller_node(ctx_ok, entry))

    assert os.path.exists("gcs_mock/world-engine-atlas/maptile_loc_placed_v1.png")
    assert os.path.exists("gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png")

    loaded_w = temp_store.get_world("world_genesis")
    assert loaded_w.map_image_url == "http://localhost:8000/gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png"
    assert loaded_w.map_image_version == 2

    assets = temp_store.list_media_assets()
    assert len(assets) == 1
    assert assets[0].kind == "map_tile"
    assert assets[0].node_id == "loc_placed"
    assert assets[0].world_id == "world_genesis"

    if os.path.exists("cache/fake_tile.png"):
        os.remove("cache/fake_tile.png")
    if os.path.exists("cache/fake_canvas.png"):
        os.remove("cache/fake_canvas.png")
    if os.path.exists("gcs_mock/world-engine-atlas/maptile_loc_placed_v1.png"):
        os.remove("gcs_mock/world-engine-atlas/maptile_loc_placed_v1.png")
    if os.path.exists("gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png"):
        os.remove("gcs_mock/world-engine-atlas/mapcanvas_world_genesis_v2.png")

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
"""World-facing routes: map, world summary, chronicle, codex, discovery."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.core.types import DEFAULT_WORLD_ID, SEED_WORLD

router = APIRouter()


@router.get("/world/map")
def get_world_map(authorization: str | None = Header(None)):
    """GET /world/map -> the active world plus its locations (coords, regions, painted tile URLs) with per-user fog-of-war state."""
    store = deps.get_store()
    user_id = deps.get_user_id_from_token(authorization)
    active_w_id = deps.active_world_id()

    active_w = store.get_world(active_w_id)
    if not active_w:
        active_w = store.get_world(DEFAULT_WORLD_ID) or SEED_WORLD

    world_info = {
        "id": active_w.id,
        "theme": active_w.theme,
        "opening_line": active_w.opening_line,
        "art_style_directive": active_w.art_style_directive,
        "map_image_url": active_w.map_image_url,
    }

    canon_locations = store.list_canon_entries_by_type("location", active_w_id)
    discoveries = store.list_discoveries(user_id)

    # Query map tiles and build latest map_tile URL dict
    all_assets = store.list_media_assets()
    tile_urls = {}
    for asset in all_assets:
        if asset.kind == "map_tile" and asset.world_id == active_w_id:
            existing = tile_urls.get(asset.node_id)
            if not existing or asset.created_at > existing.created_at:
                tile_urls[asset.node_id] = asset

    locations = []
    for loc in canon_locations:
        x = loc.map_meta.x if loc.map_meta else 0.0
        y = loc.map_meta.y if loc.map_meta else 0.0
        region = loc.map_meta.region if loc.map_meta else ""
        near = loc.map_meta.near if loc.map_meta else []

        discovered = (loc.id in discoveries) or (loc.contributor_id == user_id)

        tile_asset = tile_urls.get(loc.id)
        tile_url = tile_asset.gcs_url if tile_asset else None

        locations.append(
            {
                "id": loc.id,
                "title": loc.title,
                "body": loc.body,
                "region": region,
                "x": x,
                "y": y,
                "near": near,
                "discovered": discovered,
                "contributor_id": loc.contributor_id,
                "tile_url": tile_url,
            }
        )

    regions = sorted({loc["region"] for loc in locations if loc["region"]})

    return {
        "world": world_info,
        "locations": locations,
        "regions": regions,
    }


@router.get("/world")
def get_world(authorization: str | None = Header(None)):
    """GET /world -> the active world summary (theme, opening line, status, and time remaining in the drop)."""
    store = deps.get_store()
    from app.core.lifecycle import is_window_open, seconds_remaining, tick

    tick(store)
    active_w_id = deps.active_world_id()
    active_w = store.get_world(active_w_id)
    if not active_w:
        active_w = store.get_world(DEFAULT_WORLD_ID) or SEED_WORLD

    return {
        "world_id": active_w.id,
        "theme": active_w.theme,
        "opening_line": active_w.opening_line,
        "art_style": active_w.art_style_directive,
        "status": active_w.status.value
        if hasattr(active_w.status, "value")
        else active_w.status,
        "opens_at": active_w.opens_at.isoformat() if active_w.opens_at else None,
        "closes_at": active_w.closes_at.isoformat() if active_w.closes_at else None,
        "time_remaining_seconds": seconds_remaining(active_w),
        "window_open": is_window_open(active_w),
    }


@router.get("/world/chronicle")
def get_world_chronicle(authorization: str | None = Header(None)):
    """GET /world/chronicle -> the active world's storyteller synthesis.

    Read-only "what we know so far": the same chronicler role, voiced in the form
    the world's era evokes (shaman / bard / influencer / story-bot). Cached by
    world + canon count in the chronicler module, so re-opening the panel is instant.
    """
    from app.agents.chronicler import build_chronicle

    store = deps.get_store()
    return build_chronicle(deps.resolve_active_world(), store)


@router.get("/codex/{kind}")
def get_codex(kind: str, authorization: str | None = Header(None)):
    """GET /codex/{kind} -> the codex index grid for one entry type (characters|beasts|spells), tagged with per-user discovery flags."""
    kind_to_type = {
        "characters": "character",
        "beasts": "beast",
        "spells": "spell",
    }
    if kind not in kind_to_type:
        raise HTTPException(status_code=404, detail="Invalid codex kind")

    entry_type = kind_to_type[kind]
    store = deps.get_store()
    user_id = deps.get_user_id_from_token(authorization)
    active_w_id = deps.active_world_id()

    entries = store.list_canon_entries_by_type(entry_type, active_w_id)
    discoveries = store.list_discoveries(user_id)

    codex_items = []
    for entry in entries:
        discovered = (entry.id in discoveries) or (entry.contributor_id == user_id)
        codex_items.append(
            {
                "id": entry.id,
                "title": entry.title,
                "body": entry.body,
                "contributor_id": entry.contributor_id,
                "discovered": discovered,
            }
        )

    return codex_items


class DiscoverPayload(BaseModel):
    canon_id: str


@router.post("/discover")
def post_discover(payload: DiscoverPayload, authorization: str | None = Header(None)):
    """POST /discover -> clear fog-of-war on a canon node for the calling user (idempotent)."""
    user_id = deps.get_user_id_from_token(authorization)
    store = deps.get_store()
    store.save_discovery(user_id, payload.canon_id)
    return {"discovered": True, "canon_id": payload.canon_id}

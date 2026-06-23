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

import io
import logging
import os

from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from PIL import Image, ImageDraw

from app.agents.media import CACHE_DIR, generate_imagen_panel
from app.agents.moderation import scan_hidden_content, scan_prompt_injection
from app.core.store import get_store
from app.core.types import CanonEntry, ContributionType

logger = logging.getLogger(__name__)


def atlas_node(ctx: Context, node_input: CanonEntry):
    """Atlas Illustrator Agent.

    Generates a painterly map tile for a location, and composites/paints it into the
    world's master map canvas.
    """
    entry = node_input
    if not entry or entry.type != ContributionType.LOCATION or not entry.map_meta:
        logger.info("Atlas Node: skipped (not a placed location).")
        yield Event(output=entry)
        return

    store = get_store()
    world = store.get_world(entry.world_id)
    if not world:
        logger.warning("Atlas Node: world %s not found.", entry.world_id)
        yield Event(output=entry)
        return

    # Media safety gate: re-screen the lore before generating any imagery. The text
    # already passed full moderation during ingest; these deterministic scans
    # additionally block hidden/encoded payloads and prompt-injection from steering the
    # image model (mirrors the Showcase pre-generation re-check). Offline-safe (no LLM).
    screen_text = f"{entry.title}\n{entry.body}"
    flagged = scan_hidden_content(screen_text) or scan_prompt_injection(screen_text)
    if flagged:
        logger.warning("Atlas Node: BLOCK before generation — %s", flagged.reason)
        yield Event(output=entry)
        return

    x = entry.map_meta.x
    y = entry.map_meta.y
    region = entry.map_meta.region or "Uncharted"

    # Build map tile prompt (Phase 1)
    art_style = world.art_style_directive or "Painterly illustration"
    tile_prompt = (
        f"{art_style}; a top-down illustrated map vignette of {entry.title}: {entry.body}; "
        f"{region} biome; transparent/soft edges; no text or labels."
    )

    # Check cache first for tile
    tile_filename = f"maptile_{entry.id}_v{entry.version}.png"
    tile_cache_path = os.path.join(CACHE_DIR, tile_filename)

    if os.path.exists(tile_cache_path):
        logger.info("Atlas Node: tile cache hit.")
        with open(tile_cache_path, "rb") as f:
            tile_bytes = f.read()
    else:
        # Build the genai client lazily and only on a cache miss. If no key/credentials
        # are configured, generate_imagen_panel falls back to a local mock image so the
        # atlas still runs offline.
        client = None
        try:
            client = genai.Client()
        except Exception as e:
            logger.warning("Atlas Node: genai client unavailable (%s); using mock image.", e)
        tile_bytes = generate_imagen_panel(client, tile_prompt, 1)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(tile_cache_path, "wb") as f:
            f.write(tile_bytes)

    # Compositing into the growing master canvas (Phase 2)
    current_canvas_url = world.map_image_url
    canvas_image = None

    # Try to load existing canvas
    if current_canvas_url:
        local_path = None
        if "gcs_mock/" in current_canvas_url:
            local_path = "gcs_mock/" + current_canvas_url.split("gcs_mock/")[-1]
        elif current_canvas_url.startswith("gcs_mock/"):
            local_path = current_canvas_url

        if local_path and os.path.exists(local_path):
            try:
                canvas_image = Image.open(local_path)
                logger.info("Atlas Node: loaded existing canvas from %s", local_path)
            except Exception as e:
                logger.error("Atlas Node: failed to load existing canvas: %s", e)

    # If no existing canvas, create base canvas
    if canvas_image is None:
        canvas_image = Image.new("RGB", (1024, 1024), (230, 215, 184))
        draw = ImageDraw.Draw(canvas_image)
        draw.rectangle([(20, 20), (1004, 1004)], outline=(180, 160, 130), width=3)
        logger.info("Atlas Node: created new base canvas.")

    # Paint/Composite the tile onto the canvas at (x%, y%)
    tile_img = Image.open(io.BytesIO(tile_bytes))
    # Resize tile to 256x256 if needed
    if tile_img.size != (256, 256):
        tile_img = tile_img.resize((256, 256))

    # Calculate pixel coords from x%, y% (clamp to 0-100)
    px = int(max(0.0, min(100.0, x)) / 100.0 * 1024)
    py = int(max(0.0, min(100.0, y)) / 100.0 * 1024)

    # Paste tile centered at (px, py)
    tx = px - 128
    ty = py - 128

    if tile_img.mode in ("RGBA", "LA") or (
        tile_img.mode == "P" and "transparency" in tile_img.info
    ):
        canvas_image.paste(tile_img, (tx, ty), tile_img)
    else:
        canvas_image.paste(tile_img, (tx, ty))

    # Save updated canvas to cache
    new_version = world.map_image_version + 1
    canvas_filename = f"mapcanvas_{world.id}_v{new_version}.png"
    canvas_cache_path = os.path.join(CACHE_DIR, canvas_filename)

    canvas_buf = io.BytesIO()
    canvas_image.save(canvas_buf, format="PNG")
    canvas_bytes = canvas_buf.getvalue()

    with open(canvas_cache_path, "wb") as f:
        f.write(canvas_bytes)

    # Prepare cartography proposal
    ctx.state["cartography_proposal"] = {
        "world_id": world.id,
        "location_id": entry.id,
        "version": entry.version,
        "contributor_ids": [entry.contributor_id],
        # Phase 1: Tile
        "tile_src_path": tile_cache_path,
        "tile_dest_path": f"gcs_mock/world-engine-atlas/{tile_filename}",
        "tile_filename": tile_filename,
        # Phase 2: Canvas
        "canvas_src_path": canvas_cache_path,
        "canvas_dest_path": f"gcs_mock/world-engine-atlas/{canvas_filename}",
        "canvas_filename": canvas_filename,
        "canvas_version": new_version,
    }

    logger.info(
        "Atlas Node: proposed cartography updates for %s (v%d).",
        entry.id,
        entry.version,
    )
    yield Event(output=entry)

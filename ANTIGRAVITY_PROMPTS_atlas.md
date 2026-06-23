# Antigravity Build Prompt — The Atlas Illustrator (agents draw the map as it grows)

> Build this end-to-end: the async image agent (backend) **and** the map rendering
> (frontend). Work in both `world-engine/` (ADK 2.0 + FastAPI) and `world-engine-ui/`
> (React 18 + Vite). Read repo-root `CONTEXT.md` first and keep all work consistent
> with it. This builds on the current working tree, which already has: the World/Season
> model + `world_id` scoping, the Cartographer node (sets `map_meta` on locations), the
> `/world/map` · `/codex/{kind}` · `/canon/{id}` · `/discover` endpoints, and the
> frontend Map/Codex pages (`WorldMap.jsx`, `Codex.jsx`, `LoreDrawer.jsx`).

## Concept
The Cartographer already decides *where* a location sits (`map_meta.{x,y,region,near}`).
This agent decides *what it looks like* and renders it into a shared, growing map image
for the world — so each accepted location completes the canvas like a puzzle piece. Over
a drop, the crowd + agents assemble an exquisite-corpse atlas.

## Hard constraints (do not violate)
- **Async only.** Never add image generation to the synchronous `/contribute` ingest
  path (latency/cost). Mirror the existing Showcase async trigger
  (`enqueue_showcase_task` + `POST /internal/run-showcase` + background-thread fallback
  in `app/fast_api_app.py`).
- **Proposal → controller.** The generation node only *proposes* bytes + metadata; a
  deterministic controller performs ALL side effects (cache→GCS copy confined to the
  world's prefix, DB writes). Follow `showcase_controller_node` in
  `app/core/controller.py` (its GCS prefix-confinement is already implemented — reuse it).
- **Moderate before generating.** Re-run the Moderation node + Media content policy on the
  location's lore text and the visual prompt BEFORE generation; on BLOCK, mark the
  asset/job blocked and generate nothing (same as Showcase node 3).
- **Provider via `policy.yaml`** (`media_providers.image`), reusing the real helpers in
  `app/agents/media.py` (`generate_imagen_panel`, the Nano-Banana `generate_content`
  image path, `get_cached_asset_path`, `cache_asset_data`). **Do not change any model id.**
  Keep the local mock-image fallback so it runs offline with no API keys.
- **Keep SynthID/C2PA** watermarks; surface "AI-generated" in any caption. Never strip them.
- **Cache / idempotent.** Key every render by `(world_id, location_id, version)`; never
  regenerate identical content.
- Match surrounding code style. Backend: the repo uses `datetime.now(timezone.utc)` and
  trips ruff `UP017` everywhere — leave that style as-is. Frontend: plain CSS + the
  existing token system in `src/index.css`; no new npm dependencies (CSS-only animation).

---

## PHASE 1 — per-location tile (ship first; reliable)

Generate ONE square painterly map vignette per newly accepted+placed location and
composite it on the map at its coordinates.

### Backend
1. `app/agents/atlas_illustrator.py` → `atlas_node(ctx, node_input)`:
   - Input: a location `CanonEntry`. Skip non-locations and any location without `map_meta`.
   - Prompt: `world.art_style_directive` + "top-down illustrated map vignette of {title}:
     {body}; {region} biome; soft/transparent edges; no text or labels."
   - Generate via the `media.py` image path (cache first). Write a `cartography_proposal`
     into `ctx.state` with the bytes' cache path + filename
     `maptile_{location_id}_v{version}.png`. **No store writes in the node.**
2. Controller: copy cached tile → `gcs_mock/world-engine-atlas/` (confine writes to that
   prefix — reuse the showcase prefix check), then save a `MediaAsset` with
   `kind="map_tile"`, `node_id=location_id`, `world_id`, the url, and
   `contributor_ids=[contributor_id]` (attribution).
3. Trigger: after `/contribute` finishes, if the run accepted a `location`, enqueue an
   atlas task — add `enqueue_atlas_task(location_id)` + `POST /internal/paint-atlas`
   parallel to the showcase trigger; background-thread fallback for local dev. Idempotent.
4. REST: extend `GET /world/map` so each location carries `tile_url` (latest `map_tile`
   MediaAsset for that id, else null).

### Frontend
5. `src/pages/WorldMap.jsx`: when a location has `tile_url`, render it as a soft-edged
   image centered on the pin (fade-in on reveal); keep the silhouette for
   fogged/undiscovered places. Keep the deterministic fallback layout already present for
   locations without `map_meta`.
6. `src/index.css`: add the tile styles (rounded, feathered mask, subtle drop shadow,
   `@keyframes` fade-in; respect `prefers-reduced-motion`).
7. `src/api.js` + `src/mock.js`: include `tile_url` in the mock `mockMap.locations` so the
   view is demoable offline; the real path already flows through `getMap`.

---

## PHASE 2 — the puzzle: paint into the growing canvas (the headline)

Maintain ONE master map image per world; for each new location, **edit that image** so
the new piece blends at the seams (continue coastlines/roads toward `near` neighbors).

### Backend
8. Store the master canvas: add `map_image_url` + `map_image_version` to the `World` model
   in `app/core/types.py`, with a self-healing SQLite `ALTER` + a Firestore field (mirror
   the `world_id` migration already in `store.py`), plus
   `save_world_map_image(world_id, url, version)` (read back via `get_world`).
9. `atlas_node` (Phase 2 path): fetch the world's current `map_image_url` (or generate a
   base canvas if none). Pass it as an **input image** to the Nano-Banana
   `generate_content` image-edit path with: `art_style_directive`, the new location's lore
   + normalized position ("paint {title} at {x}% across, {y}% down"), and the titles +
   positions of `near` neighbors ("connect its roads/terrain to {neighbor} to the west").
   Return the updated full-canvas image. Cache by `(world_id, location_id, version)`.
10. Controller: GCS-copy the new canvas (prefix-confined), bump `map_image_version`, call
    `save_world_map_image`. Keep prior versions (don't delete — provenance).
11. REST: `GET /world/map` returns `world.map_image_url`.

### Frontend
12. `src/pages/WorldMap.jsx`: render `world.map_image_url` as the atlas background layer
    beneath the interactive pins (replace the CSS parchment when a real canvas exists; keep
    CSS parchment as the empty-world fallback). Cross-fade when the version changes.

If image-to-image editing isn't available on the chosen provider, keep Phase 1 tiles and
outpaint a composite instead — note the limitation, don't fake the seams.

---

## Tests (offline; rely on the mock-image fallback — no network/keys)
`world-engine/tests/unit/test_atlas_illustrator.py`:
- `atlas_node` skips non-locations and unplaced locations (no `map_meta`).
- On an accepted placed location it writes a `cartography_proposal` (cache path/filename),
  with **no store writes**.
- Controller saves a `kind="map_tile"` MediaAsset confined to the atlas GCS prefix, and
  raises on an out-of-prefix path (like the existing showcase prefix test).
- Cache hit: a second run with the same `(world_id, location_id, version)` does not
  regenerate (assert the generate fn is called once).
- (Phase 2) `save_world_map_image` round-trips `map_image_url`/`version` in SQLite.

## Done criteria
- `cd world-engine && uv run pytest tests/unit tests/integration` green (don't break the
  current 59 unit tests).
- `uvx ruff check app/ tests/` adds no new non-`UP017` findings in touched files.
- `cd world-engine-ui && npm run build` green.
- Show the full diff. Do not commit — leave changes in the working tree for review.

## Notes / expectations
- `media.py` actually implements **Imagen + Nano-Banana via `genai`** (the
  `provider: openai/gpt-image-1` line in `policy.yaml` is not wired yet). Use what's
  really there; Phase 2's image-to-image edit is the Nano-Banana `generate_content` path.
- Seamless seam-matching (roads continuing across the join) is the hard part and image
  models are inconsistent at it — Phase 1 tiles look great immediately; Phase 2 is where
  the puzzle magic lives and will need prompt iteration. That's why it's split.

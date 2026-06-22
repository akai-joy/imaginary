# Antigravity build prompts — "Living World" (codex · map · growth)

Source of truth: `CONTEXT.md` → the **"Living World — codex, map & growth"** section and the
updated **Data model**. Feed these to Antigravity/Gemini one at a time, in order — each builds on
the previous. Locked decisions: agent-placed geography (Cartographer), one shared world + personal
fog (`Discovery`), codex = Map · Characters · Bestiary · Grimoire, fork model = explicit
**Continue** vs **Fork** with votes able to crown a prime timeline.

Global constraints for every prompt: keep the **proposal → controller** invariant (LLM nodes only
propose; the deterministic controller does all writes); do **not** change model IDs in
`policy.yaml`/`config.py`; keep the `SecurityPlugin` guardrails intact; keep both `CanonStore`
backends (SQLite + Firestore) in sync; run `uv run pytest` from `world-engine/` and show the diff.

---

## Prompt 1 — Data model migration (types, lineage, map_meta, Discovery)

```
Implement the data-model changes from CONTEXT.md's updated "Data model" section in
world-engine/app/core/types.py and both CanonStore backends (app/core/store.py).

1. Add "beast" and "spell" to the ContributionType enum (alongside character, location,
   faction, plot, lore, other). CanonEntry.type accepts the same set.
2. Add to CanonEntry: `references: list[str] = []` and
   `map_meta: dict | None = None` (shape {x, y, region, near: list[str]}; set only for
   locations). Add `derived_from: list[str] = []` and `references: list[str] = []` to the
   Contribution model if not already present.
3. Add a new `Discovery` model: { user_id, canon_id, discovered_at }.
4. Extend the CanonStore ABC + SQLiteCanonStore + FirestoreCanonStore with:
   - save/get for map_meta (persist it on the canon entry),
   - save_discovery(user_id, canon_id), list_discoveries(user_id) -> set[canon_id],
   - list_canon_entries_by_type(type) -> list[CanonEntry].
   Add a SQLite migration that ALTERs the canon table to add map_meta (JSON) and references
   (JSON) columns if missing, so the existing world.db keeps working.
5. In app/core/controller.py ingest_controller_node: when the contribution carries explicit
   `derived_from`/`references`, write them straight onto the CanonEntry (do NOT rely on the
   Provenance LLM to infer them). Keep all existing clamping/validation.

Constraints: keep both store backends in sync; SQLite migration must be idempotent. Update
tests/unit for the new types/columns. Run `uv run pytest` and show the diff.
```

---

## Prompt 2 — Cartographer node (agent-placed geography)

```
Add a new "cartographer" LLM node to the INGEST pipeline per CONTEXT.md's "Agent-placed
geography (Cartographer node)" description.

- New module app/agents/cartographer.py following the existing node pattern
  (def cartographer_node(ctx, node_input) that yields Event). It must NOT write to the store.
- For a `location` contribution: read existing locations' map_meta (via canon_read tools) and
  PROPOSE { region, x, y, near: [canon_id] } as a Pydantic-validated `cartographer_proposal`
  in ctx.state. For `character|beast|spell`: propose a single primary "located_in" place
  reference. For other types: propose nothing (pass through).
- Extend ingest_controller_node to consume `cartographer_proposal`: validate it, CLAMP x,y to
  the map bounds (define MAP_BOUNDS, e.g. 0..1000), and write map_meta onto the CanonEntry (for
  locations) or append the located_in id to references (for character/beast/spell). The
  controller is the only writer.
- Wire the node into app/agent.py's graph AFTER provenance and BEFORE the controller
  (intake -> moderation -> continuity -> provenance -> cartographer -> scoring -> narrator ->
  controller, or place it just before the controller — keep moderation/continuity routing intact).
- Add "cartographer" to AGENT_TOOL_ALLOWLIST in app/core/security.py with canon-read tools only
  (list_canon_entries, get_canon_entry); it is a content-reading agent with NO dangerous tools.

Constraints: proposal->controller only; don't change model IDs (use get_model_for_role).
Add a unit test: submitting a second location proposes coords near a referenced existing place,
and the controller clamps out-of-range coords. Run `uv run pytest` and show the diff.
```

---

## Prompt 3 — REST endpoints (map, codex, entity detail, discovery)

```
Add the additive REST surface from CONTEXT.md's "Living World" section to
world-engine/app/fast_api_app.py. Reuse get_user_id_from_token (strict=True only on writes;
reads may be anonymous).

- GET /world/map -> { regions: [...], places: [{ id, title, type, map_meta, discovered: bool,
  revealed: bool }] }. "revealed" = accepted; "discovered" = in this user's Discovery set.
  Include `near` edges so the UI can draw borders.
- GET /codex/{kind} where kind in {characters, beasts, spells} -> list of entries of that type
  (use list_canon_entries_by_type) with discovered/revealed flags.
- GET /canon/{id} -> generic entity detail: the entry, its lore, related entities (derived_from +
  references, both directions), and the storylines it appears in. 404 if missing.
- POST /discover { canon_id } -> save_discovery for the caller; idempotent; returns { ok: true }.
- Extend POST /contribute: accept optional `derived_from: list[str]` and `references: list[str]`
  and `type` in the new enum; thread them into the Contribution so the controller applies them.

Constraints: don't break existing endpoints; keep the camelCase JSON convention the frontend
already consumes (imageUrl/videoUrl/etc). Run `uv run pytest` and show the diff.
```

---

## Prompt 4 — Frontend: Map + codex views with personal fog

```
Build the Living-World read views in world-engine-ui/src, consistent with the existing design
system (CSS custom props in index.css; serif titles, mono metadata, the oxblood/bone palette).
Add methods to src/api.js (useApi) with mock branches in src/mock.js so the app still runs with
no backend.

- New page src/pages/WorldMap.jsx (route index or /map, make it the home): renders GET /world/map.
  Discovered places = clear pins/regions; revealed-but-undiscovered = fog silhouette;
  unreached frontier = "submit lore to chart this region." Clicking a place calls POST /discover
  then routes to its detail.
- New pages Characters.jsx, Bestiary.jsx, Grimoire.jsx: index grids from GET /codex/{kind}.
- New page EntityDetail.jsx (route /entity/:id): GET /canon/:id — lore, related entities,
  storylines it appears in, contributor (mono ledger line), and an "Add lore here" button that
  routes to the build flow pre-referencing this entity. Calls POST /discover on open.
- Update src/App.jsx routes and the nav in components/Layout.jsx: Map | Characters | Bestiary |
  Grimoire | Storylines | Showcase | Submit.

Constraints: keep the graceful mock-data fallback; reuse existing components (Thread, tags) and
tokens; accessibility basics (focus-visible, aria) like the current pages. `npm run build` clean.
```

---

## Prompt 5 — Frontend: compose flow + Continue/Fork

```
Build the two write paths from CONTEXT.md in world-engine-ui/src.

- Rework src/pages/Submit.jsx into a unified "Build" flow:
  * type picker now includes beast and spell (place/character/beast/spell/faction/lore/storyline);
  * a "reference existing" selector that searches the canon and attaches references[] (cast +
    setting). For a storyline you can pick existing characters/beasts/places OR create new inline.
  * pass references[] (and type) into api.submitContribution -> POST /contribute.
- Add Continue/Fork on the storyline/scene UI (StorylineDetail.jsx / ScenePlayer): two buttons —
  "Continue" (extend) and "Fork" (alternate branch) — both open the Build flow pre-filled with
  derived_from=[currentNodeId] and the inherited cast/setting; "Fork" labels the new entry as a
  sibling timeline. Submitting posts to /contribute with derived_from set.
- After a successful submit, show the verdict + (if a location) a "charted on the map" confirmation
  linking to the new pin.

Constraints: keep optimistic-update + rollback patterns already used (VoteButton); disable submit
until required fields are valid; keep mock branches working. `npm run build` clean.
```

---

### Suggested order & checkpoints
1 → migration green (pytest) · 2 → cartographer proposes+clamps (pytest) · 3 → endpoints return
shaped JSON · 4 → map renders with fog, codex grids load · 5 → can fork a storyline and chart a
new place. After each, I (Claude) can verify the run against `CONTEXT.md` the same way as the P0
check.

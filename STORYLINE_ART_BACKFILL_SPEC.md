# Spec: Backfill storyline art for a clean demo

**Author:** Claude (diagnosis + plan) · **Executor:** Gemini/Antigravity · **Verifier:** Claude
**Repo:** `world-engine/` (run all commands from there)

---

## 1. Context & root cause (verified, not theorized)

A lot of storylines render with placeholder panels ("image pending") in the player.

The `~/.gemini` storage theory is **wrong** — there are no stray images there. Generated
PNGs are correctly in `world-engine/cache/` (55 of them). The real cause:

- Storyline art is served from `cache/` **by prompt-hash**. See
  `app/fast_api_app.py::get_media_urls_for_scene` (~line 788): it hashes the panel prompt
  and returns `cache/{hash}.png` **only if that file already exists**, else `imageUrl=None`.
- A comic (the thing that creates those cached panel PNGs) is only generated when the
  **showcase subgraph** runs for a tree.
- The showcase tally is **threshold-gated** (`policy.yaml → showcase.trigger.min_votes: 10`,
  `min_composite_score: 70`). Only popular trees ever qualified.

**Current state:** 15 storyline trees in `world_genesis`; **6 have art, 9 are bare.**

## 2. Scope (decided)

Generate art **only for substantive (multi-entry) storylines**. Ignore 1-entry stubs.

**TARGET — generate comics for these 2 trees:**

| tree_id | title | entries |
|---|---|---|
| `canon_tre_lantern` | The Lantern That Owes | 3 |
| `canon_lamp` | Lantern Row | 3 |

(These are the Drowned-Coast / Lantern saga — real narrative, currently bare.)

**IGNORE (1-entry stubs, legit lore but out of scope):** `canon_86cfa3fe-…` The School of
Magic, `canon_pass` The White Pass, `canon_void` The Unspelled Waste, `canon_tide_eel` The
Ledger Eel, `canon_emb` The Last Ember, `canon_salt` Salt the Pour, `canon_5e047725-…` The
Final Incantation.

**PRUNE (clear dev-junk — see §6):** `canon_03e1357d-6703-4828-88d6-d1a9890e2988`
"Why the Sky is Blue".

## 3. Method — pre-seed `comic` jobs, then run the existing pipeline

Do **not** lower the showcase thresholds, and do **not** rely on the tally to pick trees.
Reasons: (a) the tally hardcodes `media_type = "reel" if idx == 0`
(`app/agents/showcase_tally.py:142`) — not config-driven — so the top tree would become an
expensive Veo **reel**; (b) threshold edits are global and easy to forget to revert.

Instead, exploit the storyboard node's store fallback: `app/agents/storyboard.py:90-94`
processes `node_input` jobs **or**, when that's empty, **all `QUEUED` jobs in the store**.
With thresholds unchanged the tally emits 0 new jobs → the storyboard node falls through to
the store → it processes whatever `QUEUED` comic jobs we seeded.

The media node's comic prompt
(`app/agents/media.py:286`: `f"{scene.visual_description}, high quality fantasy comic book
style illustration, vibrant colors"`) is **byte-identical** to what `get_media_urls_for_scene`
hashes against — so once panels are cached, `/scenes/{tree_id}` serves them automatically.

### Step 3a — backfill script

Create `world-engine/scripts/backfill_storyline_art.py`:

```python
"""Seed QUEUED comic ShowcaseJobs for named storyline trees (idempotent)."""
import sys
import uuid
from datetime import UTC, datetime

from app.core.store import get_store
from app.core.types import ShowcaseJob, ShowcaseJobStatus

TARGET_TREE_IDS = ["canon_tre_lantern", "canon_lamp"]  # override via CLI args

def main(tree_ids):
    store = get_store()
    existing = {j.tree_id for j in store.list_showcase_jobs()}
    for tid in tree_ids:
        if tid in existing:
            print(f"skip {tid} (job already exists)")
            continue
        if not store.get_canon_entry(tid):
            print(f"WARN {tid} not found in store; skipping")
            continue
        job = ShowcaseJob(
            id=f"job_{uuid.uuid4()}",
            tree_id=tid,
            media_type="comic",                 # NEVER "reel" — keep cost/latency down
            status=ShowcaseJobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        store.save_showcase_job(job)
        print(f"queued comic job {job.id} for {tid}")

if __name__ == "__main__":
    main(sys.argv[1:] or TARGET_TREE_IDS)
```

### Step 3b — run it, then run the showcase subgraph

```bash
cd world-engine
uv run python -m scripts.backfill_storyline_art          # seeds the 2 comic jobs
uv run agents-cli run --app-name showcase "run"          # storyboard → media → controller
```

The subgraph will: storyboard each seeded job (writes `storyboard_json` onto the job),
generate each panel via Imagen and cache `cache/{panel_hash}.png`, compose
`cache/{job_id}_comic.png`, and the controller persists the `MediaAsset` and copies the comic
into `gcs_mock/world-engine-showcase/`.

> **Imagen reality:** real art needs Vertex/Gemini creds (`GOOGLE_GENAI_USE_VERTEXAI=True`
> path in `media.py:120`). Without creds it falls back to a colored **mock** panel
> (`create_mock_panel_image`) — fine for plumbing tests, **not** for the demo. Confirm creds
> before the real run.

## 4. Guardrails (do not violate)

- **Never change a model id** anywhere. A 404 is almost always a `GOOGLE_CLOUD_LOCATION`
  issue (try `global`), per CLAUDE.md.
- **Do not lower `policy.yaml` thresholds** as the mechanism (see §3). If you temporarily do
  for any reason, you **must** restore them.
- **Keep the SynthID watermark** on all generated media — never strip/obscure it.
- **Do not touch** the chronicler feature (`app/agents/chronicler.py`, `/world/chronicle`,
  `ChronicleDrawer.jsx`, the `chronicle:` block in `policy.yaml`) — unrelated, just shipped.
- Only `media_type="comic"`. No reels in this backfill.

## 5. Verification (Claude will re-check these)

For each target tree:

```bash
cd world-engine
# 1. Panels now have real image URLs (no nulls):
uv run python -c "
import requests
for t in ['canon_tre_lantern','canon_lamp']:
    s=requests.get(f'http://localhost:8000/scenes/{t}').json()
    imgs=[p['imageUrl'] for p in s['panels']]
    print(t, '->', sum(1 for i in imgs if i), '/', len(imgs), 'panels have art')
"
# 2. Comic page landed in the served mock bucket:
ls -la gcs_mock/world-engine-showcase/ | grep comic
```

- `GET /showcase` includes the 2 new comics.
- In the UI: open each storyline → **Play Storyline** → panels show real art, not
  "image pending" placeholders.
- `uv run pytest tests/unit tests/integration` still green; `world.db` only gained
  `ShowcaseJob` + `MediaAsset` rows for the 2 trees.

## 6. Optional (recommended for a clean demo)

- **Prune dev-junk:** remove the "Why the Sky is Blue" tree
  (`canon_03e1357d-6703-4828-88d6-d1a9890e2988`) so it doesn't appear as an empty storyline.
  Follow the existing dev-junk-removal pattern from recent commits; verify no other entry's
  `derived_from` references it before deleting (no broken lineage).
- **"Tiles" interpretation:** if by *tiles* you meant a **cover thumbnail per storyline on the
  Storylines *list* page** (`src/pages/Storylines.jsx` currently renders **no** images), that is
  a separate, larger enhancement: add a `cover_url` to the `/canon/storylines` payload (reuse the
  composed comic page, or the tree root's first panel) and render it on each list card. Flagged,
  not in scope here — confirm with the user before building it.

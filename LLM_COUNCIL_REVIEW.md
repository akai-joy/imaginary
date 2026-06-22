# LLM Council Review — World Engine

Consolidated findings from a multi-model review (Claude Opus 4.8 reading the
actual source + Mistral `mistral-small-latest` + Gemini `gemini-3-flash-preview`).
Raw scratch: `/tmp/council_prompt.txt` (prompt), `/tmp/council_out.json` (raw
external responses). Earlier single-reviewer notes: `CLAUDE_review.md`, `UI_review.md`.

## Three-way consensus (every model flagged these)

| Rank | Issue | Where | Fix |
|------|-------|-------|-----|
| P0 | Showcase runs in a `threading.Thread` inside the FastAPI process — dies on Cloud Run CPU throttle / scale-to-zero; Veo/Imagen exceed the request timeout anyway | `world-engine/app/fast_api_app.py:317-337` | Push a Cloud Tasks / Pub/Sub message, return `202`, run the showcase graph in a separate consumer |
| P0 | `SecurityPlugin` only attached to the `App`; REST endpoints build their own `Runner(...)` so guardrails never fire on `/contribute` and `/vote` | `fast_api_app.py:326`, `:435` vs `app/agent.py:96` | One shared Runner factory that always injects `plugins=[SecurityPlugin()]`; never instantiate `Runner` in a route |
| P0 | Auth is advisory — `get_user_id_from_token` returns `playground_user` on any missing/failed token, voiding the provenance/attribution thesis | `fast_api_app.py:78-101` | Require a verified Firebase UID for write paths in the deployed config; keep the fallback for local playground only |

## High / medium

- **P1 — Model IDs:** everything defaults to `gemini-3.5-flash` (`policy.yaml`, `app/core/config.py`); likely a runtime 404. Per CLAUDE.md, do **not** swap IDs blindly (the council's "use gemini-1.5-flash" suggestion is outdated). Verify the correct current id / `GOOGLE_CLOUD_LOCATION=global` first.
- **P1 — Continuity preview (new idea, Gemini):** a cheap pre-submit Flash check ("this contradicts *X*") before the formal pipeline. Highest-impact cheap UX win.
- **P1 — Tree UX (all three):** "voting on trees" is abstract; build a visual, navigable tree/timeline explorer + "why accepted/flagged" feedback on submit.
- **P2 — Injection regex (Gemini + Claude):** blunt patterns ("you are now", "forget everything", "new directive") + base64/hex scanners crash on legitimate fiction. Relax; rely on the moderation node + controller guarantees.
- **P2 — HTML escaping at rest (Gemini + Claude):** `after_model` persists `&amp;`/`&#x27;` into canon. Escape at the React render layer instead.
- **P2 — Spotlighting (all three):** `before_model` wraps the *entire* prompt (trusted instructions + untrusted data) in `=== START DATA ===` while telling the model to ignore everything inside. Wrap only untrusted spans.

## Product framing (ceiling-raisers, Gemini + Mistral)

- Reframe "Storyline Trees" → **"The Living Bible"**: the reward is having your lore *merged into official history* (provenance as social currency), not the comic at the end.
- Target TTRPG GMs / r/worldbuilding; rename "canon" → "World Bible".
- Add a **remix/fork** button on the showcase to turn winning media back into a new canon branch.
- Make the async pipeline *feel* live: submission queue + "your lore was accepted" notifications.

## Council disagreements (judgment calls — not acted on)

- Mistral called the single deterministic controller a SPOF/bottleneck. **Keep it** — the serialization *is* the security property; note it as a scaling limitation, don't dismantle.
- Mistral said "drop the mock publish gate". **Keep it** — it's a deliberate, documented out-of-scope boundary; fix the UX framing, not the gate.
- Gemini's `gemini-1.5-flash` fix is outdated — verify, don't blindly apply.

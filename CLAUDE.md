# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independent packages under the repo root:

- `world-engine/` — Python backend. ADK 2.0 graph-workflow agent system + FastAPI REST layer. All commands below run from this directory unless noted.
- `world-engine-ui/` — React 18 + Vite frontend (Firebase auth, react-router). Talks to the backend over REST; falls back to mock data when `VITE_API_BASE_URL` is empty.

`CONTEXT.md` (repo root) is the project's authoritative spec — read it before changing pipeline behavior, the safety policy, or the data model. `policy.yaml` is the single source of runtime config (models, moderation profiles, scoring weights, showcase thresholds, tool allowlists).

## Commands

Backend (`cd world-engine`):

```bash
uv sync                                   # install deps (run agents-cli install first if using the CLI)
uv run pytest                             # all tests
uv run pytest tests/unit tests/integration
uv run pytest tests/unit/test_security.py # single file
uv run pytest tests/unit/test_security.py::test_after_model_url_allowlist  # single test
uv run ruff check .                       # lint
uv run ruff format .                      # format
```

agents-cli (interactive / eval / deploy — `cd world-engine`):

```bash
uv run agents-cli playground                                   # local web UI for the agents
uv run agents-cli run "Plot: a spark lights the tavern fire"   # run the ingest pipeline (app entrypoint)
uv run agents-cli run --app-name showcase "Run showcase tally" # run the showcase subgraph
uv run agents-cli eval generate && uv run agents-cli eval grade # eval loop (see GEMINI.md Phase 3)
```

Frontend (`cd world-engine-ui`):

```bash
npm install
npm run dev      # vite dev server
npm run build
```

Integration tests and any `genai.Client()` path need Google Cloud credentials / a Gemini API key. Unit tests mock the LLM and run offline. `pytest` runs against the real `world.db` SQLite file and mutates it.

## Architecture

### Two workflows, one App each
The system is two ADK graph `Workflow`s, each wrapped in its own `App`:

- **Ingest pipeline** (`app/agent.py`, entrypoint name `app`): `intake → moderation (gate) → continuity → provenance → scoring → narrator → ingest_controller`. Edges are *routed* — Moderation routes only `ALLOW`/`FLAG` onward (a `BLOCK` halts), Continuity routes only `consistent` onward.
- **Showcase subgraph** (`showcase/agent.py`, entrypoint name `showcase`): `tally → storyboard → media → publish_handoff → showcase_controller`. Asynchronous and threshold-triggered so it adds no latency/cost to normal contributions.

Nodes are plain generator functions `def node(ctx, node_input)` that `yield Event(...)`, wired with `build_node()` + explicit `Edge`s. One module per agent under `app/agents/`.

### Proposal → Controller pattern (the core invariant)
**LLM nodes never perform side effects.** Each LLM node validates its output against a Pydantic schema and writes a *proposal* into `ctx.state` (e.g. `scoring_proposal`, `narrator_proposal`, `tally_proposal`, `media_proposal`, `publish_proposal`). The single deterministic, non-LLM controller at the end of each workflow (`app/core/controller.py`) is the only code that mutates the store, clamps values (scores → 0–100), and confines GCS writes to the job's prefix. When adding a node that changes state, follow this split — emit a proposal, extend the controller to validate and apply it. Do not write to the store from an LLM node.

### Security model
`app/core/security.py` `SecurityPlugin` (a `BasePlugin`) is the reusable guardrail layer: `before_model` (unicode-normalize, strip zero-width, redact PII, deterministic + Flash-Lite injection screen, spotlight-wrap untrusted text), `after_model` (schema enforcement, block HTML/JS/`img`/non-allowlisted URLs), `before_tool` (per-agent `AGENT_TOOL_ALLOWLIST`, block dangerous tools from content-reading agents, GCS-prefix confinement, confirmation for irreversible actions), `after_tool` (re-screen tool results as untrusted).

The plugin is attached via `App(plugins=[SecurityPlugin()])`. **It only applies to runners that carry that App's plugin list.** The custom REST endpoints in `fast_api_app.py` build their own `Runner(...)` directly, so be aware the plugin does not automatically cover those paths — the in-graph moderation node and the deterministic controller are the guardrails that always run.

Trust boundary: user contributions **and canon read back from the store** are both untrusted (canon originated from users → the indirect/second-order injection vector). Agents spotlight-wrap both in `<user_contribution>` / `<canon_entry>` tags; the narrator re-moderates its own generated summary before proposing a canon write.

### Persistence
`app/core/store.py` defines a `CanonStore` ABC with two implementations behind `get_store()`: `SQLiteCanonStore` (`world.db`, local default) and `FirestoreCanonStore` (selected when `USE_FIRESTORE=True` or `K_SERVICE` is set, i.e. on Cloud Run). Note: using Vertex AI for the LLM (`GOOGLE_GENAI_USE_VERTEXAI=True`) does **not** by itself select Firestore — local dev can run Vertex models against the local SQLite store. Keep both implementations in sync when changing the interface. Convention: a canon entry's id is `canon_{contribution_id}`; ledger lookups strip the `canon_` prefix to recover the contribution id.

### Config & models
Model names and all thresholds come from `policy.yaml` via `get_model_for_role(role)` (duplicated as a small helper in each agent module) and `app/core/config.py`. Flip `active_profile` (`strict`/`default`/`permissive`) to change moderation strictness from one place. **Never change a model id unless explicitly asked.** A model 404 is almost always a `GOOGLE_CLOUD_LOCATION` problem (try `global`), not the model name.

### REST layer
`app/fast_api_app.py` wraps the ADK app via `get_fast_api_app()` and adds the front-end endpoints: `GET /canon/storylines`, `GET /canon/storylines/{treeId}`, `POST /vote` (records a vote and, on crossing `policy.yaml` thresholds, kicks the showcase workflow in a background thread), `GET /showcase`, `POST /contribute` (runs the ingest pipeline synchronously). Identity comes from a Firebase bearer token, falling back to `playground_user` for local dev.

## Conventions (from GEMINI.md)

- Run Python via `uv run`; never invoke the system interpreter directly.
- Modify only code the request targets — preserve surrounding config values, comments, and formatting.
- ADK tool imports import the tool *instance*, not the module: `from google.adk.tools.load_web_page import load_web_page`.
- Deploy (`agents-cli deploy`) requires explicit human approval. Terraform 409 conflicts → `terraform import`, don't retry create.
- If the same error recurs 3+ times, fix the root cause rather than retrying.

## Out of scope (do not build)
No cryptocurrency/tokens/wallets/real payments — the economy is points-only and simulated. No live Instagram publishing — the publish node builds the container payload and stops at the review gate (`published_mock`), saving assets to a (mock) GCS bucket. Generated media keeps its SynthID watermark; never remove or obscure it.

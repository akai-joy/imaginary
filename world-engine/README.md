# World Engine — Backend

The Python backend for **World Engine**, a multi-agent system for safe, collaborative
storytelling. It is two **ADK 2.0 graph workflows** (an ingest pipeline and an asynchronous
showcase subgraph) plus a **FastAPI** REST layer that the React front end talks to.

> For the project pitch, the "why agents" framing, and the full architecture diagrams, see the
> [root README](../README.md). This document is the backend developer's guide.
>
> [`CONTEXT.md`](../CONTEXT.md) is the authoritative spec — read it before changing pipeline
> behavior, the safety policy, or the data model. [`policy.yaml`](policy.yaml) is the single source
> of runtime config (models, moderation profiles, scoring weights, showcase thresholds, providers,
> tool allowlists).

---

## Two workflows, one App each

The system is two ADK graph `Workflow`s, each wrapped in its own `App` so the local playground, the
eval harness, and the Cloud runtime can all discover and run them. Both `App`s carry the shared
`SecurityPlugin`.

- **Ingest pipeline** — `app/agent.py`, entrypoint name `app`:
  `intake → moderation (GATE) → continuity → provenance → scoring → narrator → cartographer →
  ingest_controller`, with the Atlas Illustrator repainting the map off the controller's writes.
  Edges are **routed**: Moderation only forwards `ALLOW`/`FLAG` (a `BLOCK` halts), Continuity only
  forwards `consistent` contributions.
- **Showcase subgraph** — `showcase/agent.py`, entrypoint name `showcase`:
  `tally → storyboard → director → media → publish_handoff → showcase_controller`. Asynchronous and
  threshold-triggered, so it adds no latency or cost to normal contributions.

Nodes are plain generator functions `def node(ctx, node_input)` that `yield Event(...)`, wired with
`build_node()` + explicit `Edge`s. One module per agent under `app/agents/`.

---

## The core invariant: Proposal → Controller

**LLM nodes never perform side effects.** Each LLM node validates its output against a Pydantic
schema and writes a *proposal* into `ctx.state` (`scoring_proposal`, `narrator_proposal`,
`cartographer_proposal`, `tally_proposal`, …). The single deterministic, non-LLM controller at the
end of each workflow (`app/core/controller.py`) is the only code that mutates the store: it
validates each proposal, clamps values (scores → 0–100, map coordinates → map bounds), and confines
GCS writes to the job's prefix.

When adding a node that changes state, follow this split — emit a proposal, then extend the
controller to validate and apply it. **Do not write to the store from an LLM node.**

---

## Security model

`app/core/security.py` `SecurityPlugin` (a `BasePlugin`) is the reusable guardrail layer, attached
via `App(plugins=[SecurityPlugin()])`:

- **`before_model`** — unicode-normalize, strip zero-width chars, redact PII, run a deterministic +
  Flash-Lite prompt-injection screen, and spotlight-wrap untrusted text in `<user_contribution>` /
  `<canon_entry>` tags.
- **`after_model`** — enforce the output schema; block HTML/JS, `<img>`, and non-allowlisted URLs.
- **`before_tool`** — enforce the per-agent `AGENT_TOOL_ALLOWLIST`, strip dangerous tools from
  content-reading agents, confine GCS access to the job prefix, and require confirmation for
  irreversible actions.
- **`after_tool`** — re-screen tool results as untrusted input.

**Trust boundary:** user contributions **and canon read back from the store** are both untrusted —
canon originated from users, so it is a second-order (indirect) injection vector. The Narrator even
re-moderates its own generated summary before proposing a canon write.

> The plugin only applies to runners that carry that App's plugin list. The custom REST endpoints in
> `fast_api_app.py` build their own `Runner(...)` directly, so the plugin does **not** automatically
> cover those paths — the in-graph Moderation node and the deterministic controller are the
> guardrails that always run there.

---

## MCP Server — read the living world

`app/mcp_server.py` is a **Model Context Protocol server** that turns World Engine into a
*platform*: any MCP client (Claude Desktop, the MCP Inspector, an external author/continuation
agent) can read the **living manuscript** — world state, the codex, and the story so far — without
being wired into the ADK graph. It is built directly on the `CanonStore` ABC, so it works against
SQLite locally and Firestore in the cloud with no new persistence.

| Tool | Layer | Returns |
| --- | --- | --- |
| `get_world_state()` | world / season | Active drop: opening line, art style, status, and the contribution window (`time_remaining_seconds` populates once the season timer lands). |
| `get_codex(kind?)` | world bible | Canon entries by type (character, location, faction, beast, spell, …). |
| `get_story(tree_id?)` | manuscript | All storyline trees, or one tree assembled into ordered chapters — the draft of the book. |
| `get_lore_context(query)` | grounding | Canon relevant to a query, to ground a continuation without contradicting canon. |
| `check_continuity(statement)` | grounding | Existing canon related to a proposed statement, for the caller to judge. |

**Read-only by construction — and that's the point.** There is deliberately **no write tool**.
Writes to canon happen *exclusively* through the deterministic controllers, so the same
Proposal→Controller trust boundary that protects the in-graph agents is enforced at the MCP surface:
an external client can read the entire world but can never mutate it or bypass moderation. The same
`get_story` / `get_codex` read path is what a future season-finale book compiler will consume.

```bash
uv run python -m app.mcp_server     # serve over stdio (what an MCP client launches)
uv run mcp dev app/mcp_server.py    # inspect the tools interactively
```

---

## Persistence

`app/core/store.py` defines a `CanonStore` ABC with two implementations behind `get_store()`:

- `SQLiteCanonStore` (`world.db`, the local default), and
- `FirestoreCanonStore` (selected when `USE_FIRESTORE=True` or `K_SERVICE` is set, i.e. on Cloud Run).

Keep both implementations in sync when changing the interface. Convention: a canon entry's id is
`canon_{contribution_id}`; ledger lookups strip the `canon_` prefix to recover the contribution id.

> Using Vertex AI for the LLM (`GOOGLE_GENAI_USE_VERTEXAI=True`) does **not** by itself select
> Firestore — local dev can run Vertex models against the local SQLite store.

---

## Config & models

Model names and all thresholds come from `policy.yaml` via `get_model_for_role(role)` and
`app/core/config.py`. Flip `active_profile` (`strict` / `default` / `permissive`) to change
moderation strictness from one place. The media stack is **fully Google-native** — Imagen for
images, Veo for video, Gemini TTS for voice — swappable via `policy.yaml` without touching code.

- **Never change a model id unless explicitly asked.** A model 404 is almost always a
  `GOOGLE_CLOUD_LOCATION` problem (try `global`), not the model name.

---

## REST layer

`app/fast_api_app.py` wraps the ADK app via `get_fast_api_app()` and adds the front-end endpoints.
Identity comes from a Firebase bearer token, falling back to `playground_user` for local dev.

| Method & path | Purpose |
| --- | --- |
| `GET /world/map` | Active world + placed locations for the Living Atlas |
| `GET /codex/{kind}` | Codex entries by kind (characters, locations, …) |
| `GET /canon/storylines` | List storyline trees |
| `GET /canon/storylines/{treeId}` | One tree with its lineage |
| `GET /canon/{id}` | A single canon entry |
| `GET /scenes/{id}` | Explorable-graph scene (panels + cached media URLs) |
| `POST /contribute` | Run the ingest pipeline synchronously |
| `POST /vote` | Record a vote; crossing `policy.yaml` thresholds kicks the showcase workflow |
| `GET /showcase` | Published showcase media |
| `POST /discover` / `POST /feedback` | Fog-of-war discovery + feedback |

---

## Project structure

```
world-engine/
├── app/
│   ├── agent.py             # ingest Workflow + App   (entrypoint: app)
│   ├── fast_api_app.py      # FastAPI REST layer
│   ├── agents/              # one module per agent (intake, moderation, continuity, …)
│   ├── core/
│   │   ├── controller.py    # the ONLY store-mutating code (Proposal→Controller)
│   │   ├── security.py      # SecurityPlugin guardrail layer
│   │   ├── store.py         # CanonStore ABC: SQLite (local) / Firestore (cloud)
│   │   ├── types.py         # Pydantic schemas passed between nodes
│   │   ├── config.py        # policy.yaml loader + get_model_for_role
│   │   └── lifecycle.py     # world / season lifecycle
│   ├── app_utils/           # telemetry + typing helpers
│   └── tools/               # ADK tool instances
├── showcase/agent.py        # showcase Workflow + App  (entrypoint: showcase)
├── policy.yaml              # single source of runtime config
├── deployment/              # Dockerfile + Terraform (Cloud Run / Agent Runtime)
└── tests/                   # unit + integration + eval (incl. red-team security cases)
```

---

## Commands

```bash
uv sync                                   # install deps
uv run agents-cli playground              # local web UI for the agents
uv run agents-cli run "Plot: a spark lights the tavern fire"   # ingest pipeline (app entrypoint)
uv run agents-cli run --app-name showcase "Run showcase tally" # showcase subgraph
uv run agents-cli eval generate && uv run agents-cli eval grade # eval loop

uv run uvicorn app.fast_api_app:app --reload   # serve the REST API on :8000

uv run pytest                             # full suite
uv run pytest tests/unit tests/integration
uv run pytest tests/unit/test_security.py # single file
uv run ruff check . && uv run ruff format .
```

The repo ships with a populated `world.db`, so the playground and REST API have canon, votes, and
ledger scores out of the box. **Unit tests mock the LLM and run offline.** Integration tests and any
real generation path need Google Cloud credentials / a Gemini API key. `pytest` runs against the
real `world.db` and mutates it.

---

## Deployment

```bash
uv run agents-cli deploy        # builds the container + provisions via Terraform (requires approval)
```

- `Dockerfile` containerizes the FastAPI + ADK app.
- `deployment/terraform/single-project/` provisions APIs, IAM, the Cloud Run service, storage, and telemetry.
- On Cloud Run (`K_SERVICE` set) the store transparently switches from SQLite to Firestore — no code changes.
- Terraform 409 conflicts → `terraform import`, don't retry create. Deploy requires explicit human approval.

---

## Conventions

- Run Python via `uv run`; never invoke the system interpreter directly.
- Modify only the code the request targets — preserve surrounding config, comments, and formatting.
- ADK tool imports import the tool *instance*: `from google.adk.tools.load_web_page import load_web_page`.
- The economy is points-only and simulated; generated media keeps its SynthID watermark; publishing
  stops at a review gate (`published_mock`). No secrets in code — keys come from Secret Manager /
  environment, server-side only.

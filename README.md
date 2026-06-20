# World Engine: Collaborative Storytelling Agent System

A multi-agent **world engine** for collaborative storytelling. Users submit storytelling contributions (characters, locations, factions, plot beats, lore). The system automatically moderates, checks continuity, traces provenance, scores, and merges accepted contributions into a persistent canon. In addition, an asynchronous **Showcase subgraph** tallies and triggers automated media creation for popular storyline trees.

Built using the **ADK 2.0 graph workflow API**, **agents-cli**, **Gemini**, and deployed via Google Cloud Agent Runtime.

---

## Architecture

### 1. Ingestion Pipeline (`app` entrypoint)
The main ingestion pipeline runs sequentially (halting on Moderation block):
1. **Intake/Router** — Classifies contribution type (character, location, plot, etc.) and normalizes the fields.
2. **Safety Moderation (GATE)** — Performs deterministic and LLM-based safety checks. Blocks mature themes, illegal instructions, prompt injections, and hidden messages (acrostics, zero-width chars, base64/hex payloads).
3. **Continuity Check** — Compares the contribution against the existing canon to detect narrative contradictions.
4. **Provenance Extraction** — Automatically detects lineage connections (what existing canon entries this contribution builds on) and links them.
5. **Story Critic & Scoring** — Evaluates creativity, consistency, and build-on (0-100), awarding points to the author in a simulated simulated ledger economy.
6. **Narrator & Synthesis** — Merges accepted contributions, generates a "what changed in the world" summary, re-moderates the summary, and persists it to the canon store.

### 2. Showcase Subgraph (`showcase` entrypoint)
Runs independently from the ingestion pipeline to avoid latency and costs.
- **StorylineTree View**: Assembles trees starting from root `CanonEntry` nodes by walking their `derived_from` parent lineage edges.
- **Tally/Trigger Node**: 
  - Retrieves human votes and ledger scores for each tree.
  - Checks them against thresholds in `policy.yaml` (e.g., `min_votes: 10`, `min_composite_score: 70`).
  - Ranks new qualifiers by combined votes (weight: 0.6) + score (weight: 0.4).
  - Emits `ShowcaseJob`s to database: the single top-ranked tree gets `media_type=reel` (Veo), and all other qualifiers get `media_type=comic` (Imagen).
  - Avoids duplicate jobs for previously processed trees.

---

## Local Development & CLI

### Prerequisites
Ensure you have `uv` installed. Set up your environment and database:
```bash
cd world-engine
uv sync
```

### Seeding the Database
To initialize the SQLite database (`world.db`) with test canon entries, votes, and ledger scores:
```bash
uv run python /Users/akaijoy/.gemini/antigravity-cli/brain/52f5af5f-f5cf-41b8-ae25-94db26d3d549/scratch/preseed_db.py
uv run python /Users/akaijoy/.gemini/antigravity-cli/brain/52f5af5f-f5cf-41b8-ae25-94db26d3d549/scratch/seed_votes.py
```

### Running the Agents

#### 1. Ingest Contribution (Main App)
To run a new contribution through the ingestion pipeline:
```bash
uv run agents-cli run "Plot: Alistair lights the tavern fireplace with a spark of fire magic."
```

#### 2. Run Showcase Tally Subgraph
To run the Showcase tally trigger:
```bash
uv run agents-cli run --app-name showcase "Run showcase tally"
```

### Interactive Local Playground
Start the ADK local playground to test the agents via a web UI:
```bash
uv run agents-cli playground
```

### Running Tests
Execute the pytest suite (all tests, including unit and integration tests):
```bash
uv run pytest
```

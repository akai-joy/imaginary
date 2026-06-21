# Coding Agent Guide

## Prerequisites

Install the CLI (one-time):
```bash
uv tool install google-agents-cli
```

---

## Development Phases

### Phase 1: Understand Requirements
Before writing any code, understand the project's requirements, constraints, and success criteria.

### Phase 2: Build and Implement
Implement agent logic in `app/`. Use `agents-cli playground` for interactive testing. Iterate based on user feedback.

### Phase 3: The Evaluation Loop (Main Iteration Phase)
Start with 1-2 eval cases, run `agents-cli eval generate`, then `agents-cli eval grade`, iterate by making changes and rerunning both commands until satisfied. Expect 5-10+ iterations. Once you have a baseline, reach for `agents-cli eval compare` (regression diffs), `agents-cli eval analyze` (cluster failure modes), and `agents-cli eval optimize` (auto-tune prompts). See the **Evaluation Guide** for metrics, dataset schema, LLM-as-judge config, and common gotchas.

### Phase 4: Pre-Deployment Tests
Run `uv run pytest tests/unit tests/integration`. Fix issues until all tests pass.

### Phase 5: Deploy to Dev
**Requires explicit human approval.** Run `agents-cli deploy` only after user confirms. See the **Deployment Guide** for details.

### Phase 6: Production Deployment
Ask the user: Option A (simple single-project) or Option B (full CI/CD pipeline with `agents-cli infra cicd`).

## Development Commands

| Command | Purpose |
|---------|---------|
| `agents-cli playground` | Interactive local testing |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli eval dataset synthesize` | Synthesize multi-turn eval scenarios for your agent |
| `agents-cli eval generate` | Run agent on eval dataset, produce traces |
| `agents-cli eval grade` | Run agent evaluations on the traces |
| `agents-cli eval compare` | Compare two grade-results files (regression check) |
| `agents-cli eval analyze` | Cluster failure modes from grade results |
| `agents-cli eval metric list` | List built-in metrics available in the SDK |
| `agents-cli eval optimize` | Auto-tune agent prompts using eval data |
| `agents-cli lint` | Check code quality |
| `agents-cli infra single-project` | Set up project infrastructure (Terraform) |
| `agents-cli deploy` | Deploy to dev |
| `agents-cli scaffold enhance` | Add deployment target or CI/CD to project |
| `agents-cli scaffold upgrade` | Upgrade project to latest version |

---

## Operational Guidelines for Coding Agents

- **Code preservation**: Only modify code directly targeted by the user's request. Preserve all surrounding code, config values (e.g., `model`), comments, and formatting.
- **NEVER change the model** unless explicitly asked.
- **Model 404 errors**: Fix `GOOGLE_CLOUD_LOCATION` (e.g., `global` instead of `us-east1`), not the model name.
- **ADK tool imports**: Import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`
- **Run Python with `uv`**: `uv run python script.py`. Run `agents-cli install` first.
- **Stop on repeated errors**: If the same error appears 3+ times, fix the root cause instead of retrying.
- **Terraform conflicts** (Error 409): Use `terraform import` instead of retrying creation.

---

## Workspace Session Summary & Outstanding Items (Memorialized June 2026)

### 1. Completed Fixes

- **Developer API (AI Studio) Image / Video Integration**:
  - Configured [media.py](file:///Users/akaijoy/aimaginary/world-engine/app/agents/media.py) to dynamically fall back to Gemini Developer API models if Vertex AI is not used (`GOOGLE_GENAI_USE_VERTEXAI == "False"`).
  - **Image generation** uses `gemini-3.1-flash-image` (Nano Banana) with `GenerateContentConfig(response_modalities=["IMAGE"])`.
  - **Video generation** uses `veo-3.1-generate-preview` (AI Studio Veo) with a robust polling loop using `client.operations.get` and `client.files.download` to download the generated `.mp4` binary data correctly.
- **FastAPI Static File Serving**:
  - Mounted the local `gcs_mock/` directory to `/gcs_mock` in [fast_api_app.py](file:///Users/akaijoy/aimaginary/world-engine/app/fast_api_app.py) using FastAPI `StaticFiles` to allow local asset hosting.
  - Translated external `storage.googleapis.com` URLs to `http://localhost:8000/gcs_mock/` inside the `/showcase` endpoint.
- **Mock Reel Video Fallback**:
  - Implemented header detection to verify if a reel MP4 file contains text-based mock data or a real binary video. If it's a text mock, `gcs_url` returns `None` so the frontend falls back cleanly to rendering the interactive, text-based scene/storyboard lists as designed in the UI.
- **Custom Generated Video Override**:
  - Replaced the generated showcase assets for Alistair's "Ash Oak" storyline (Job ID `job_e7dc320e-8c5b-434b-8683-d328f922ba1f`) with your custom-produced video `silence_falls_over_the_scorche.mp4`. It streams correctly on the client interface via HTTP 206 Range requests.

### 2. Outstanding & Future Items

- **Running the Servers Again**:
  - To resume local testing when you return:
    - Start the backend FastAPI server:
      ```bash
      .venv/bin/python app/fast_api_app.py
      ```
    - Start the frontend dev server (in `world-engine-ui` directory):
      ```bash
      npm run dev
      ```
- **Showcase Policy Settings**:
  - The default trigger policies are set back to:
    - `min_votes: 10`
    - `min_composite_score: 70`
  - If you need to test the pipeline with fewer votes, you can temporarily adjust `min_votes` inside [policy.yaml](file:///Users/akaijoy/aimaginary/world-engine/policy.yaml).
- **Clearing Database / Starting Fresh**:
  - If you want to purge generated showcases and rerun tally triggers from scratch:
    1. Clear sqlite db tables:
       ```sql
       DELETE FROM votes;
       DELETE FROM ledger_entries;
       DELETE FROM showcase_jobs;
       DELETE FROM media_assets;
       ```
    2. Seed new mock scores and votes:
       ```bash
       .venv/bin/python /Users/akaijoy/.gemini/antigravity-cli/brain/52f5af5f-f5cf-41b8-ae25-94db26d3d549/scratch/seed_votes.py
       ```
    3. Run the showcase agent workflow:
       ```bash
       .venv/bin/python /Users/akaijoy/.gemini/antigravity-cli/brain/52f5af5f-f5cf-41b8-ae25-94db26d3d549/scratch/run_showcase.py
       ```

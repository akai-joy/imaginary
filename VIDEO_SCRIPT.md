# World Engine — 5-minute submission video script

FORMAT: [SCREEN] = what to show · (VO) = narration to read aloud.
Target: 5:00. Record the demo (beat 4) SEPARATELY first as a clean backup take.

────────────────────────────────────────────────────────
## BEAT 1 — Hook + Problem  (0:00–0:40)
[SCREEN] The candlelit Living Atlas, slowly panning; title card "WORLD ENGINE".

(VO) "Video games hand you a world someone else authored. What if a crowd could
author one together — in real time? The problem is everything that goes wrong when
strangers co-write a shared world: contradictions, chaos, and content no one wants.
A human editorial team can't moderate that at scale, and an unguarded AI can't be
trusted to. World Engine solves this with a team of autonomous agents that act as the
referee and editor — so open, safe co-creation can actually exist."

────────────────────────────────────────────────────────
## BEAT 2 — Why agents  (0:40–1:20)
[SCREEN] Simple animation: a user fragment → agents → canon. Text: "AI as referee, not author."

(VO) "Here's the key idea: the agents are not the content — they're the
infrastructure of trust. Every contribution is moderated, checked for continuity
against existing canon, traced for provenance, and scored — at machine speed, on every
submission. That's work agents are uniquely suited for, and work that has to happen
before a single word joins the world. The AI never authors the story. It referees it.
That's what lets players let their imagination run wild, safely."

────────────────────────────────────────────────────────
## BEAT 3 — Architecture  (1:20–2:10)
[SCREEN] The README Mermaid diagram of the ingest pipeline; highlight nodes as named.

(VO) "Architecturally, it's two ADK graph workflows. The ingest pipeline routes a
contribution through intake, a moderation gate, continuity, provenance, scoring, a
narrator, and a cartographer — and a single deterministic controller is the only code
that ever writes to the world."
[SCREEN] Zoom the controller node; text overlay: "Proposal → Controller invariant."
(VO) "This is the core design: the LLM agents only ever propose. They can be creative;
they can't corrupt the canon — because one auditable, non-LLM controller validates and
clamps everything before it persists. A second, asynchronous showcase workflow turns
the most-loved storylines into shareable media."

────────────────────────────────────────────────────────
## BEAT 4 — Demo  (2:10–3:40)  ← the heart; show real software
[SCREEN] The app. Open the Bestiary in the Codex.
(VO) "Let's add to a live world. I'll open the Bestiary and continue the story —"
[SCREEN] Click "Add connected lore", type a new beast: "The crows." Submit.
(VO) "— adding a new creature. Watch what happens: it doesn't just save."
[SCREEN] Show the verdict: moderation ALLOW · continuity consistent · a score.
(VO) "It ran the full agent pipeline — moderated, continuity-checked, scored — and
only then merged into canon, with its lineage to the story it builds on."
[SCREEN] The crows now appears in the Bestiary; pan the map.
(VO) "Now the safety case. I'll try to smuggle in an instruction to the AI."
[SCREEN] Submit a prompt-injection contribution; show the blocked / sanitized state.
(VO) "Blocked. The security layer caught the injection before it ever reached a model.
The same untrusted-input defenses apply even to canon read back from the store — because
that canon originally came from users."

────────────────────────────────────────────────────────
## BEAT 5 — Security + MCP  (3:40–4:20)
[SCREEN] Briefly show SecurityPlugin hooks list; then the MCP Inspector connected to the Canon server.
(VO) "Two pieces of clever tool use. First, a reusable security plugin: injection
screening, PII redaction, per-agent tool allowlists. Second — a Model Context Protocol
server that exposes the living world to any MCP client, read-only by design: you can
read the whole manuscript, but there's no write tool, because only the controller can
change canon. The trust boundary holds at the protocol surface."
[SCREEN] Run get_story in the Inspector; show the assembled chapters.

────────────────────────────────────────────────────────
## BEAT 6 — The Build + Deploy + Close  (4:20–5:00)
[SCREEN] Antigravity/Gemini coding session; then agents-cli + Terraform files.
(VO) "I built this with Antigravity driving Gemini, on Google's Agent Development Kit
and the Agents CLI, with a fully Google-native media stack — Imagen and Veo. It's
deployment-ready: a Dockerfile and Terraform take it to Cloud Run, where storage
switches from SQLite to Firestore with no code change."
[SCREEN] Back to the candlelit map; the season countdown ticking.
(VO) "World Engine is an exquisite corpse that can't collapse into chaos — because the
agents hold the coherence and safety the players never see. A crowd and a set of agents,
co-authoring a living world. Thanks for watching."

────────────────────────────────────────────────────────
## CAPTURE CHECKLIST
- Record at 1080p; add burned-in captions (judges often watch muted).
- Beat 4 recorded separately as a clean take — your backup if the live run flakes.
- Have the backend running with valid creds before filming beats 4–5.
- Pre-stage: a clean world with the crows NOT yet added; a saved injection string.
- Keep the architecture diagram (README Mermaid) exported as a crisp PNG for beat 3.

## KEY CONCEPTS SHOWN (say/caption them)
Multi-agent ADK (beat 3) · Security (beats 4–5) · MCP Server (beat 5) ·
Deployability (beat 6) · Antigravity (beat 6). → 5 of 6, well past the required 3.

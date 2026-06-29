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
(VO) "And the world doesn't just store the story — it tells it."
[SCREEN] Click the "Let the Bard catch you up" pill on the map; the Chronicle drawer opens; hit play.
(VO) "The Chronicle recaps everything known so far, in a voice that fits the world's era —
here, a medieval bard — spoken aloud with Gemini text-to-speech, generated once and cached.
As the world grows, it re-voices itself."
[SCREEN] Let one line of the bard's narration breathe, then close the drawer.
(VO) "Now the safety case. I'll try to smuggle in an instruction to the AI."
[SCREEN] Submit a prompt-injection contribution; show the blocked / sanitized state.
(VO) "Blocked. The security layer caught the injection before it ever reached a model.
The same untrusted-input defenses apply even to canon read back from the store — because
that canon originally came from users."

────────────────────────────────────────────────────────
## BEAT 5 — Security + the world as a platform (MCP)  (3:40–4:25)
[SCREEN] Briefly show the SecurityPlugin hooks list.
(VO) "Two pieces of clever tool use. First, a reusable security plugin — injection
screening, PII redaction, per-agent tool allowlists — applied to every agent at once."
[SCREEN] Switch to Claude Desktop with the World Engine Canon MCP server connected (its tools listed).
(VO) "Second, a Model Context Protocol server that exposes the living world to any MCP
client, read-only by design. Here's a different AI — Claude Desktop — connected to our canon."
[SCREEN] Ask it to write a short story from the world; show it call get_world_state / get_codex /
get_story, then the story it writes ("The First Pour").
(VO) "It reads the world over MCP and writes a brand-new story — pulling real characters, the
Slag Court, the Ember Accord, even a one-line subplot nobody had developed — weaving them
together while honoring the world's dead-magic premise. An outside agent just built on our world,
and it could never corrupt it: there is no write tool, because only the controller can change
canon. The trust boundary holds even at the protocol surface."

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
- Pre-warm the Chronicle (open "Let the Bard catch you up" once) so the audio plays instantly on camera.
- Beat 5: native Claude Desktop with the Canon MCP connected (cwd-wrapped config); pre-write "The First Pour" as a backup take.
- Keep the architecture diagram (slide 7 / README Mermaid) exported as a crisp PNG for beat 3.

## KEY CONCEPTS SHOWN (say/caption them)
Multi-agent ADK (beat 3) · Security (beats 4–5) · MCP Server (beat 5) ·
Deployability (beat 6) · Antigravity (beat 6). → 5 of 6, well past the required 3.

# World Engine — a safe, collaborative world humans and agents co-author

**Capstone — Kaggle 5-Day AI Agents Intensive (Vibe Coding) with Google**
Stack: ADK 2.0 (graph workflows) · Agents CLI · Google Antigravity · Gemini · Imagen · Veo · Gemini TTS · FastAPI · React + Vite · Google Cloud (Cloud Run / Firestore)

- **Repository:** https://github.com/akai-joy/imaginary
- **Demo video:** _<link>_

---

## The problem

Video games and stories hand you a world someone else authored. Letting a *crowd*
author one together — in real time — is a far more interesting idea, and it almost
never works. The moment strangers write into one shared canon you inherit every failure
mode at once: continuity breaks, attribution is lost (nobody can tell whose idea a
world was built on), and unmoderated submissions invite content nobody wants in a shared
creative space.

You can't fix this the human way — no editorial team can read, fact-check against canon,
and moderate every contribution at the speed a crowd produces them. And you can't fix it
by pointing one large language model at the problem either; an unguarded model is exactly
what you *can't* trust with a public, user-fed, ever-growing world. So collaborative
worldbuilding has stayed a novelty.

> **Research question:** *Can a crowd and a set of autonomous agents co-author a coherent,
> safe fictional world under a time-boxed creative constraint — with the AI as referee,
> not author?*

## What it is

**World Engine** treats a shared story like open-source software. Users submit
contributions (characters, locations, factions, beasts, spells, plot beats, lore); a
graph of specialized agents checks each one for safety and continuity, traces what it
builds on, scores it on merit, and weaves it into a persistent canon — with credit
flowing to the people whose ideas others reuse. Humans vote on the storylines they love,
and the most-loved trees are auto-produced into shareable media. An in-world economy
rewards good lore, modelled as **points, not currency**.

Two design choices make it a *game*, not a CMS:

- **Seasons.** A world is a limited-time themed **"drop"** that opens on a single
  evocative *opening line*. The time-boxed window concentrates the crowd into a shared
  event and gives "done" a meaning: when the drop closes, the world is archived as a
  read-only collectible and the next theme opens.
- **The fold.** Contributors don't fill a blank form. From the map, the codex, or any
  storyline they *Continue* a thread (inheriting its lineage) or *Add connected lore*
  (referencing existing canon) — the exquisite-corpse mechanic, made playable.

The one-line pitch: **an exquisite corpse that cannot collapse into chaos or harm —
because the agents hold the coherence and safety the players can't see. The AI is the
referee, not the author.**

## Why agents

The agents are not a feature bolted onto a storytelling app — **they are the
infrastructure of trust that makes open, safe co-creation possible at all.** Judging
safety, continuity, provenance, and quality on *every* contribution at machine speed is
exactly the judgment-heavy work agents are suited for, and exactly the work that has to
happen before a single word becomes canon. The humans author; the agents referee.

## Architecture

Two ADK graph workflows, each behind its own App, sharing one security plugin.
_(Diagrams in the [README](README.md).)_

**Ingest pipeline (every contribution):**
Intake/Router → **Moderation (gate)** → Continuity → Provenance → Scoring →
Narrator/Synthesis → **Cartographer** → **Controller**, with an Atlas Illustrator
repainting the map. The contribution is classified, safety-gated, checked against canon
for contradictions, linked to what it builds on, scored, drafted into canon, and placed
on the world map. Edges are *routed*: moderation only forwards safe contributions (a
BLOCK halts the pipeline); continuity only forwards consistent ones.

**Showcase subgraph (asynchronous, threshold-triggered):**
Tally → Storyboard → **Moderation re-check** → Art Director → Media → Publish/Handoff.
When a tree crosses its vote + score threshold it is storyboarded, re-moderated, and
rendered — a cheap comic for every qualifier, a single 9:16 Veo reel for the top tree
per cycle.

### The Living Atlas

The world isn't a list — it's a **map that draws itself**. A Cartographer agent proposes
where new lore sits (region, coordinates, nearby links); the deterministic controller
clamps and commits it; an Atlas Illustrator paints a tile and composites it into a
candlelit, fog-of-war master map. Users never place pins — the world self-assembles from
the lore the crowd writes.

### The Chronicle — the world narrates itself

The world doesn't just *store* its story — it **tells** it. A read-only synthesis
(`GET /world/chronicle`) weaves the active world's separate storylines into a short
"what we know so far" recap, in the voice of a storyteller whose **form shifts with the
world's era** — a medieval bard, a primal shaman, a present-day influencer — read aloud with
**Gemini TTS** (generated once and cached). It's the same "tie the threads together" job the
Narrator does internally, surfaced to the reader as the world's own voice.

## Safety and security (the core of the build)

Because every downstream agent reads untrusted, user-submitted text, this is the
project's primary risk surface (OWASP **LLM01**).

- **A moderation gate** classifies content ALLOW / FLAG / BLOCK, hard-blocks
  non-negotiable categories, and strips hidden/encoded payloads and prompt-injection
  attempts before anything reaches canon — then re-checks again before any media is
  generated.
- **An injection defense built on the principle that you cannot prompt your way out of
  injection.** Detection is one layer; the real protection is deterministic. It's a
  single reusable ADK **Plugin** registered once on the Runner, so guardrails apply
  globally: input screening, regex-based PII redaction (emails, phone numbers, SSNs),
  output filtering (no HTML/JS/non-allowlisted URLs), per-agent tool allowlists, and
  untrusted-result re-screening.
- **Least privilege — the Proposal→Controller invariant.** LLM nodes only *propose*
  schema-validated output; a deterministic, non-LLM controller is the only code that
  commits any side effect, clamping every value (scores to 0–100, coordinates to bounds)
  and confining file writes to a job prefix. A hijacked node can at most propose a value
  the controller clamps — it cannot write arbitrary points, delete canon, or trigger
  publishing.
- **Trust boundaries that include canon on read-back**, closing the second-order
  (indirect) injection vector most systems miss — because canon originally came from
  users. The narrator even re-moderates its own generated summary before proposing a
  write.

### Clever tool use: the Canon MCP server

World Engine exposes the living world over the **Model Context Protocol**. Any MCP client
(Claude Desktop, the MCP Inspector, an external author agent) can read the whole
manuscript — world state, codex, and the story so far — through five tools, with **no
write tool by design**. Since the only path that can mutate canon is the deterministic
controller, the Proposal→Controller trust boundary is enforced even at the protocol
surface: read everything, corrupt nothing.

We demonstrated this end-to-end: a *different* model — **Claude Desktop, connected to the
canon over MCP** — read the world and wrote a brand-new, canon-faithful short story ("The
First Pour"), pulling real characters, the Slag Court, the Ember Accord, the oath-eating
Slagmaw Drake, and even a one-line subplot nobody had developed — while honoring the world's
dead-magic premise. An outside agent built *on* the world without being able to corrupt it:
the clearest proof that World Engine is a safe, read-only **platform** other agents can create
against.

## Evaluation

An agents-cli eval set asserts the system behaves under both normal and adversarial
input: a contradictory contribution (Continuity flags), a derivative one (Provenance
links, Scoring rewards build-on), an original one (Scoring high), a disallowed one
(Moderation BLOCK), and a red-team battery — direct injection, second-order canon
read-back, tool-abuse (points overflow), and output exfiltration — each asserting the
attack is neutralised. Unit tests additionally pin the invariants (e.g. the MCP server
exposes *no* write tool).

## Deployability

A `CanonStore` interface has two implementations — SQLite locally, Firestore in the
cloud — selected automatically on Cloud Run. A Dockerfile and Terraform
(`apis / iam / service / storage / telemetry`) take the system to Cloud Run / Agent
Runtime; switching backends requires no code change.

## The journey

The project's shape came from a few hard-won decisions:

- **The invariant came first.** Treating "an LLM with side effects on shared canon" as
  *the* threat made the Proposal→Controller split obvious — and clamping, file-write
  confinement, and the no-write MCP surface all fell out of that one rule.
- **The second-order injection realization.** Sanitizing user input is easy; the
  non-obvious risk is that canon *read back* is attacker-influenced too. Spotlight-wrapping
  canon-on-readback closed a vector most systems miss.
- **Going fully Google-native.** Consolidating the media stack to Imagen / Veo / Gemini
  TTS made the system simpler and cheaper to reason about, and shrank the secret surface
  to a single Google credential.
- **Making the world feel alive.** The Living Atlas — agents placing and painting the map
  — was the biggest leap in the experience.
- **The fold.** Reworking submission into contextual *Continue* / *Add connected lore*
  from the map, codex, and storylines turned the system from a CMS into the collaborative
  game it was meant to be.

It was built with **Antigravity driving Gemini** on the Agents CLI and ADK,
prototype-first in the local playground before anything touched the cloud.

## Responsible-AI notes

- The economy is **points-only and simulated** — no cryptocurrency, tokens, wallets, or payouts.
- All generated media carries an embedded **SynthID** watermark and is labelled
  "AI-generated"; the watermark is never removed.
- Live social publishing is intentionally **out of scope**: the handoff builds the
  Instagram content-publishing payload and stops at a review gate, saving the asset to
  Google Cloud Storage instead.
- No secrets in code — all credentials come from environment / Secret Manager, server-side only.

## Key concepts demonstrated

| Concept | Where |
| --- | --- |
| Agent / multi-agent system (ADK) | Two graph workflows, 15 agents, routed edges, Proposal→Controller |
| MCP Server | `world-engine/app/mcp_server.py` — read-only Canon server over `CanonStore` |
| Security features | `SecurityPlugin` + second-order injection defense + red-team evals |
| Agent skills (Agents CLI) | scaffold / playground / eval / deploy |
| Deployability | Dockerfile + Terraform → Cloud Run; SQLite ↔ Firestore |
| Antigravity | the system was built with Antigravity / Gemini |

**All 6 key concepts demonstrated — well past the required 3.**

## What's novel

The combination: provenance-tracked collaborative fiction; a "proof-of-creativity"
scoring model that rewards downstream reuse rather than posting volume; a
security-first multi-agent design where untrusted user content passes through eight
agents without ever being trusted; a world that literally draws *and narrates* itself; and an
MCP surface that turns the finished world into a safe **platform** an outside agent can author
against.

## Value, economy & rewards (the vision this is built for)

World Engine is the first floor of a creator-economy platform for collaborative IP: the
same agents that keep the world safe and coherent are also the referee for **value and
attribution**. Because every contribution is **scored and provenance-traced**, a
finished world's value can be split *fairly and deterministically* among its authors — a
"proof-of-creativity" payout over the existing ledger + provenance graph — with badges,
collectible renders of canon, and merch revenue-sharing as natural extensions.

**Scope discipline for this capstone:** the economy is deliberately **points-only and
simulated** — no cryptocurrency, tokens, wallets, or real payments (see the
Responsible-AI notes). The reward split is modelled and *shown*, never settled.

## Limitations and future work

Scoring quality is bounded by the judging model; continuity search is keyword-based and
would benefit from vector retrieval at scale. The plugin's input hygiene is likewise
deliberately lightweight for this scope: PII redaction is three regex patterns (email,
phone, SSN) — a stand-in for a real DLP service — and the deterministic injection screen
is a pattern list backed by a Flash-Lite classifier, not a trained detector. Future
work, roughly in order:

1. **Vector-RAG continuity** to scale canon-consistency beyond keyword matching.
2. **Season-finale book compiler** — render an archived drop into a full anthology
   (the MCP read layer is already built for it).
3. **Badges & contributor profiles** — derived from existing contribution/vote/provenance data.
4. **Merch render targets** — e-book, D&D module, and background/art exports of canon.
5. **A provenance-weighted reward split** — first simulated (as above), and only later, if
   ever, a regulated/opt-in real payout path with the necessary compliance layer.
6. **A reviewed live-publishing path** (today the showcase stops at a mock review gate).

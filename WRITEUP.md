# World Engine — a safety-first multi-agent world for collaborative storytelling

**Capstone — Kaggle 5-Day AI Agents Intensive (Vibe Coding) with Google**
Stack: ADK 2.0 (graph workflow) · agents-cli · Google Antigravity · Gemini · Imagen · Veo · Google Cloud

## The problem
Collaborative fiction has no memory and no fairness. Wikis lose continuity, forums lose
attribution, and nobody can tell whose idea a shared world was actually built on. World
Engine treats a shared story like open-source software: every contribution is checked for
continuity, traced to what it builds on, scored on merit, and woven into a persistent
canon — with credit flowing to the people whose ideas others reuse.

## What it is
Users submit story contributions (characters, locations, factions, plot beats, lore). A
graph of specialised agents turns each one into canon, humans vote on the storylines they
love, and the most-loved trees are auto-produced into shareable media. An in-world economy
rewards good lore — modelled as **points, not currency**.

## Architecture
Two ADK graph workflows behind one App.

**Ingest pipeline (runs on every contribution):**
Intake/Router → **Moderation (gate)** → Continuity → Provenance → Scoring → Narrator/Synthesis.
The contribution is classified, safety-gated, checked against canon for contradictions,
linked to the entries it builds on (the provenance graph), scored on creativity /
consistency / build-on, then merged into canon.

**Showcase subgraph (asynchronous, threshold-triggered):**
Tally/Trigger → Storyboard → **Moderation re-check** → Media → Publish/Handoff.
When a story tree crosses its vote + score threshold, it is storyboarded, re-moderated,
and rendered — a cheap comic for every qualifier, and a single 9:16 Veo reel for the
top-ranked tree per cycle.

## Safety and security (the core of the build)
Because every downstream agent reads untrusted, user-submitted text, this is treated as
the project's primary risk surface (OWASP LLM01).

- **A moderation gate** classifies content as ALLOW / FLAG / BLOCK, hard-blocks
  non-negotiable categories, and strips hidden/encoded messages and prompt-injection
  attempts before anything reaches canon — then re-checks again before any media is
  generated.
- **A prompt-injection defense layer built on the principle that you cannot prompt your
  way out of injection.** Detection is one layer; the real protection is deterministic.
  Implemented as a single reusable ADK Plugin registered once on the Runner, so guardrails
  apply globally to every agent (input screening, output filtering, per-agent tool
  allowlists, untrusted-result re-screening).
- **Least privilege.** LLM nodes only *propose* structured output; a deterministic
  non-LLM controller validates and commits every side effect. A hijacked node can at most
  propose a value the controller clamps — it cannot write arbitrary points, delete canon,
  or trigger publishing.
- **Trust boundaries that include canon on read-back**, closing the second-order
  (indirect) injection vector most systems miss.

## Evaluation
An agents-cli eval set asserts the system behaves under both normal and adversarial input:
a contradictory contribution (Continuity flags), a derivative one (Provenance links,
Scoring rewards build-on), an original one (Scoring high), a disallowed one (Moderation
BLOCK), and a red-team battery — direct injection, second-order canon read-back,
tool-abuse (points overflow), and output exfiltration — each asserting the attack is
neutralised.

## Responsible-AI notes
- The economy is **points-only and simulated** — no cryptocurrency, tokens, wallets, or
  payouts.
- All generated media carries an embedded **SynthID** watermark and is labelled
  "AI-generated"; the watermark is never removed.
- Live social publishing is intentionally **out of scope**: the handoff builds the
  Instagram content-publishing payload and stops at the review gate, saving the asset to
  Google Cloud Storage instead.

## What's novel
The combination: provenance-tracked collaborative fiction, a "proof-of-creativity"
scoring model that rewards downstream reuse rather than posting volume, and a
security-first multi-agent design where untrusted user content can pass through six agents
without ever being trusted.

## Limitations and future work
Scoring quality is bounded by the judging model; continuity search is keyword-based and
would benefit from vector retrieval at scale. Future work: a real (regulated, opt-in)
contributor economy to replace simulated points, vector-RAG continuity, and a reviewed
live-publishing path.

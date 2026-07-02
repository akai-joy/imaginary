# Capstone submission checklist

Running list from the Fable code/writeup review (2026-07-02). Cross items off as they land.
Consider deleting this file before the repo goes public for judging.

## Blocking for submission

- [ ] **Record demo video and replace the `_<link>_` placeholder in WRITEUP.md** (in progress — slides/presentation being polished first)
- [ ] **Make the GitHub repo public** (`gh repo edit akai-joy/imaginary --visibility public`) — judges currently cannot see it
- [x] Reconcile the contradicting security docs — verified `SecurityPlugin` covers the REST paths (ADK `Runner(app=)` installs `app.plugins`); README + CLAUDE.md corrected, WRITEUP was already right
- [x] Fix `Copyright 2026 Google LLC` headers → `akai-joy` (42 files) and add Apache-2.0 `LICENSE` at repo root
- [x] Commit the working tree so the public repo is clean

## Strongly recommended before judging

- [ ] Trim the "Value, economy & rewards" section of WRITEUP.md to ~a third of its length — future-monetization vision dilutes the security story that wins points
- [x] Back up `world.db` before any demo rehearsal — `pytest` mutates the real demo canon
- [ ] Fix the `datetime.utcnow()` deprecation warning at `world-engine/app/mcp_server.py:149` (use `datetime.now(UTC)`)

## Optional polish (only if time allows)

- [ ] Soften enterprise-scale wording where the implementation is lightweight (e.g. note "PII redaction" is regex-based for email/phone/SSN) — same candor as the keyword-continuity limitation
- [ ] Reduce the 83 pytest warnings (mostly deprecations)
- [ ] Post-submission: split up the 1,672-line `fast_api_app.py` monolith (inline imports, per-request `InMemorySessionService`)

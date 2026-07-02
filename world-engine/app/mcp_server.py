# Copyright 2026 akai-joy
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Canon MCP Server — read-only access to the living world.

This Model Context Protocol server turns World Engine into a *platform*: any MCP
client (Claude Desktop, the MCP Inspector, an external author/continuation agent)
can read the living manuscript — the **world state**, the **codex** (the world
bible), and the **story so far** — without being wired into the ADK graph.

Design (and why it matters):

* **Read-only by construction.** Every tool here only *reads* or *grounds*; there is
  deliberately **no write tool**. Writes to canon happen *exclusively* through the
  deterministic ingest/showcase controllers (`app/core/controller.py`), which validate
  and clamp every agent proposal. The same Proposal -> Controller trust boundary that
  protects the in-graph agents is therefore enforced at the MCP surface too: an external
  client can read the whole world but can never mutate it or bypass moderation.
* **Built on the existing `CanonStore` ABC.** It calls `get_store()`, so it works
  transparently against SQLite locally and Firestore in the cloud — no new persistence.
* **Forward-compatible with the season time element.** `get_world_state` already returns
  the contribution window (`opens_at` / `closes_at` / `time_remaining_seconds`); when the
  lifecycle timer lands those fields populate without reshaping the tool — and the same
  `get_story` / `get_codex` read path is what a season-finale "book compiler" will consume.

Run it (stdio transport, the default an MCP client launches):

    uv run python -m app.mcp_server

Then point any MCP client at that command, or inspect it with:

    uv run mcp dev app/mcp_server.py
"""

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from app.agents.showcase_tally import assemble_trees
from app.core.store import get_store
from app.core.types import CanonEntry, ContributionType

mcp = FastMCP("world-engine-canon")


# ---------------------------------------------------------------------------
# Internal helpers (deterministic, no LLM, no side effects)
# ---------------------------------------------------------------------------
def _active_world_id() -> str | None:
    """The world every tool scopes to by default — the current open drop."""
    world = get_store().get_active_world()
    return world.id if world else None


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize to naive UTC so we can compare seed dates (utcnow, naive) against
    aware timestamps without raising — mirrors the REST layer's handling."""
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _entry_summary(entry: CanonEntry) -> dict:
    """A compact, JSON-safe view of a canon entry for codex/search results."""
    return {
        "id": entry.id,
        "type": entry.type.value,
        "title": entry.title,
        "body": entry.body,
        "contributor": entry.contributor_id,
        "version": entry.version,
        "region": entry.map_meta.region if entry.map_meta else None,
    }


def _assemble_story(tree_id: str) -> dict | None:
    """Load one storyline tree and return its members in reading order as chapters.

    Reuses `assemble_trees` (the same lineage walk the showcase pipeline and REST layer
    use) so the MCP view of "the story" never drifts from the canonical one.
    """
    store = get_store()
    canon_entries = store.list_canon_entries(_active_world_id())
    assembled = assemble_trees(canon_entries)

    members = next((m for root, m in assembled if root == tree_id), None)
    if members is None:
        return None

    root = store.get_canon_entry(tree_id)
    if not root:
        return None

    entries = [e for e in (store.get_canon_entry(m) for m in members) if e]
    # Chronological order == narrative reading order (the fold is appended over time).
    entries.sort(key=lambda e: _naive_utc(e.created_at) or datetime.min)

    votes = store.get_votes_for_tree(tree_id)
    chapters = [
        {
            "chapter": i + 1,
            "id": e.id,
            "type": e.type.value,
            "title": e.title,
            "text": e.body,
            "contributor": e.contributor_id,
            "builds_on": e.derived_from,
        }
        for i, e in enumerate(entries)
    ]
    return {
        "tree_id": tree_id,
        "title": root.title,
        "opening_line": root.body,
        "chapter_count": len(chapters),
        "vote_total": int(sum(v.weight for v in votes)),
        "chapters": chapters,
    }


# ---------------------------------------------------------------------------
# Tools — Layer 1: world / season state
# ---------------------------------------------------------------------------
@mcp.tool()
def get_world_state() -> dict:
    """Return the active world (themed drop): its opening line, art style, lifecycle
    status, and contribution window. The "where are we" snapshot a client reads first.

    `closes_at` / `time_remaining_seconds` are `None` for the open-ended seed world and
    populate once a drop is given a hard deadline by the season lifecycle.
    """
    store = get_store()
    world = store.get_active_world()
    if not world:
        return {"active": False, "message": "No active world."}

    closes_at = _naive_utc(world.closes_at)
    now = datetime.now(UTC).replace(tzinfo=None)
    time_remaining = (
        max(0, int((closes_at - now).total_seconds())) if closes_at else None
    )

    entries = store.list_canon_entries(world.id)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.type.value] = counts.get(e.type.value, 0) + 1

    return {
        "active": True,
        "world_id": world.id,
        "theme": world.theme,
        "opening_line": world.opening_line,
        "art_style": world.art_style_directive,
        "status": world.status.value,
        "opens_at": world.opens_at.isoformat(),
        "closes_at": closes_at.isoformat() if closes_at else None,
        "time_remaining_seconds": time_remaining,
        "canon_entry_count": len(entries),
        "entry_counts_by_type": counts,
    }


# ---------------------------------------------------------------------------
# Tools — Layer 2: the codex (world bible)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_codex(kind: str | None = None) -> dict:
    """Return the world bible — canon entries an author needs to stay consistent.

    `kind` optionally filters to one type: character, location, faction, beast, spell,
    plot, lore. With no `kind`, returns every type grouped together.
    """
    store = get_store()
    world_id = _active_world_id()

    if kind:
        kind = kind.lower().strip()
        valid = {t.value for t in ContributionType}
        if kind not in valid:
            return {"error": f"Unknown kind '{kind}'.", "valid_kinds": sorted(valid)}
        entries = store.list_canon_entries_by_type(kind, world_id)
        return {
            "kind": kind,
            "count": len(entries),
            "entries": [_entry_summary(e) for e in entries],
        }

    grouped: dict[str, list[dict]] = {}
    for e in store.list_canon_entries(world_id):
        grouped.setdefault(e.type.value, []).append(_entry_summary(e))
    return {"kinds": list(grouped.keys()), "codex": grouped}


# ---------------------------------------------------------------------------
# Tools — Layer 3: the story (the living manuscript)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_story(tree_id: str | None = None) -> dict:
    """Return the story so far.

    With no `tree_id`, lists the storyline trees (each is one branch of the manuscript)
    with their root, size, and vote total. With a `tree_id`, returns that tree assembled
    into ordered chapters — the draft of the book a finale compiler would render.
    """
    store = get_store()
    if tree_id:
        story = _assemble_story(tree_id)
        if story is None:
            return {"error": f"No storyline tree '{tree_id}'."}
        return story

    canon_entries = store.list_canon_entries(_active_world_id())
    assembled = assemble_trees(canon_entries)
    trees = []
    for root_id, members in assembled:
        root = store.get_canon_entry(root_id)
        if not root:
            continue
        votes = store.get_votes_for_tree(root_id)
        trees.append(
            {
                "tree_id": root_id,
                "title": root.title,
                "opening_line": root.body,
                "chapter_count": len(members),
                "vote_total": int(sum(v.weight for v in votes)),
            }
        )
    trees.sort(key=lambda t: t["vote_total"], reverse=True)
    return {"tree_count": len(trees), "storylines": trees}


# ---------------------------------------------------------------------------
# Tools — grounding helpers (read / validate only)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_lore_context(query: str) -> dict:
    """Search canon for entries relevant to `query` — grounding for an external client
    that wants to continue the story without contradicting what already exists.
    """
    store = get_store()
    results = store.search_canon_entries(query, _active_world_id())
    return {
        "query": query,
        "match_count": len(results),
        "matches": [_entry_summary(e) for e in results],
    }


@mcp.tool()
def check_continuity(statement: str) -> dict:
    """Surface the existing canon most relevant to a proposed `statement`, so a caller
    can judge whether it fits the world.

    This returns *context for the caller to reason over*, not an authoritative verdict:
    the binding continuity gate is the in-graph Continuity node, and the only path that
    can actually write to canon is the deterministic controller. Read-only by design.
    """
    store = get_store()
    related = store.search_canon_entries(statement, _active_world_id())
    return {
        "statement": statement,
        "related_canon_count": len(related),
        "related_canon": [_entry_summary(e) for e in related],
        "note": (
            "Authoritative moderation + continuity run only inside the ingest pipeline; "
            "submit via POST /contribute to actually add to canon."
        ),
    }


def main() -> None:
    """Entry point: serve over stdio, the transport MCP clients launch by default."""
    mcp.run()


if __name__ == "__main__":
    main()

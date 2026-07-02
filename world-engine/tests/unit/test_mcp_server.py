# Copyright 2026 Google LLC
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

"""Tests for the Canon MCP server (`app/mcp_server.py`).

These run against the seeded `world.db` and assert both the shape of the tool outputs
and — most importantly — the server's core security invariant: it exposes no write tool.
"""

import pytest

import app.mcp_server as srv


async def _tool_names() -> set[str]:
    return {t.name for t in await srv.mcp.list_tools()}


@pytest.mark.asyncio
async def test_exposes_exactly_the_read_tools():
    """The server registers its five read tools — and nothing else."""
    assert await _tool_names() == {
        "get_world_state",
        "get_codex",
        "get_story",
        "get_lore_context",
        "check_continuity",
    }


@pytest.mark.asyncio
async def test_no_write_tool_is_exposed():
    """Security invariant: canon can only be mutated by the deterministic controller, so
    the MCP surface must expose no create/update/delete/write tool whatsoever."""
    forbidden = (
        "save",
        "write",
        "create",
        "update",
        "delete",
        "set",
        "add",
        "contribute",
    )
    names = await _tool_names()
    assert not [n for n in names if any(verb in n.lower() for verb in forbidden)]


def test_get_world_state_reports_active_world():
    state = srv.get_world_state()
    assert state["active"] is True
    assert state["theme"]
    assert state["opening_line"]
    # Forward-compatible time element: present as a key, None until a drop has a deadline.
    assert "time_remaining_seconds" in state


def test_get_codex_rejects_unknown_kind():
    result = srv.get_codex("dragon-rider")
    assert "error" in result
    assert "character" in result["valid_kinds"]


def test_get_story_list_then_detail_assembles_chapters():
    listing = srv.get_story()
    assert listing["tree_count"] >= 1
    # Trees are returned most-voted first.
    votes = [t["vote_total"] for t in listing["storylines"]]
    assert votes == sorted(votes, reverse=True)

    tree_id = listing["storylines"][0]["tree_id"]
    detail = srv.get_story(tree_id)
    assert detail["tree_id"] == tree_id
    assert detail["chapter_count"] == len(detail["chapters"])
    # Chapters are numbered in reading order starting at 1.
    assert [c["chapter"] for c in detail["chapters"]] == list(
        range(1, detail["chapter_count"] + 1)
    )


def test_get_story_unknown_tree_returns_error():
    assert "error" in srv.get_story("canon_does_not_exist")

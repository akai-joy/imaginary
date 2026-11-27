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
# limitations under the License.
"""Canon routes: storyline trees, entity detail, voting."""

import logging
import os
import uuid
from datetime import UTC, datetime

import yaml
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.agents.showcase_tally import assemble_trees
from app.api import deps
from app.api.services.showcase_runner import trigger_showcase_task
from app.core.config import POLICY_PATH
from app.core.types import Vote

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/canon/storylines")
def list_storylines(authorization: str | None = Header(None)):
    """GET /canon/storylines -> StorylineTree[] summaries (active world only)"""
    store = deps.get_store()
    canon_entries = store.list_canon_entries(deps.active_world_id())
    assembled = assemble_trees(canon_entries)
    user_id = deps.get_user_id_from_token(authorization)

    storyline_trees = []
    for root_id, member_ids in assembled:
        root_entry = store.get_canon_entry(root_id)
        if not root_entry:
            continue

        votes = store.get_votes_for_tree(root_id)
        vote_total = sum(v.weight for v in votes)
        voted = any(v.voter_id == user_id for v in votes)

        # Calculate composite score (average of member points in ledger)
        scores = []
        for member_id in member_ids:
            contrib_id = member_id[6:] if member_id.startswith("canon_") else member_id
            score = store.get_points_for_contribution(contrib_id)
            if score is not None:
                scores.append(score)
        composite_score = sum(scores) / len(scores) if scores else 0.0

        # Determine version (max version in tree)
        versions = []
        for member_id in member_ids:
            m_entry = store.get_canon_entry(member_id)
            if m_entry:
                versions.append(m_entry.version)
        version = max(versions) if versions else 1

        # Determine if root builds on something (derived_from tree)
        derived_from = None
        if root_entry.derived_from:
            parent_id = root_entry.derived_from[0]
            for p_root_id, p_member_ids in assembled:
                if parent_id in p_member_ids:
                    derived_from = p_root_id
                    break

        storyline_trees.append(
            {
                "tree_id": root_id,
                "title": root_entry.title,
                "summary": root_entry.body,
                "type": root_entry.type.value
                if hasattr(root_entry.type, "value")
                else root_entry.type,
                "member_count": len(member_ids),
                "vote_total": int(vote_total),
                "composite_score": int(composite_score),
                "version": version,
                "voted": voted,
                "derived_from": derived_from,
            }
        )

    return storyline_trees


@router.get("/canon/storylines/{treeId}")
def get_storyline(treeId: str, authorization: str | None = Header(None)):
    """GET /canon/storylines/:treeId -> Detailed StorylineTree with nodes array.

    Scoped to the tree root's own world (not the active one) so storylines in
    archived collectible worlds stay reachable by direct link."""
    store = deps.get_store()
    root_entry = store.get_canon_entry(treeId)
    if not root_entry:
        raise HTTPException(status_code=404, detail="Root entry not found")

    canon_entries = store.list_canon_entries(root_entry.world_id)
    assembled = assemble_trees(canon_entries)
    user_id = deps.get_user_id_from_token(authorization)

    target_members = None
    for root_id, member_ids in assembled:
        if root_id == treeId:
            target_members = member_ids
            break

    if not target_members:
        raise HTTPException(status_code=404, detail="Storyline tree not found")

    votes = store.get_votes_for_tree(treeId)
    vote_total = sum(v.weight for v in votes)
    voted = any(v.voter_id == user_id for v in votes)

    # Load and map nodes sorted chronologically
    loaded_entries = []
    for member_id in target_members:
        entry = store.get_canon_entry(member_id)
        if entry:
            loaded_entries.append(entry)

    loaded_entries.sort(
        key=lambda x: (
            x.created_at.replace(tzinfo=None)
            if x.created_at and hasattr(x.created_at, "replace")
            else x.created_at
        )
    )

    nodes = []
    scores = []
    versions = []
    for entry in loaded_entries:
        versions.append(entry.version)
        contrib_id = entry.id[6:] if entry.id.startswith("canon_") else entry.id
        score = store.get_points_for_contribution(contrib_id)
        if score is not None:
            scores.append(score)

        nodes.append(
            {
                "id": entry.id,
                "type": entry.type.value
                if hasattr(entry.type, "value")
                else entry.type,
                "title": entry.title,
                "contributor": entry.contributor_id,
                "version": entry.version,
                "derived_from": entry.derived_from,
                "body": entry.body,
            }
        )

    composite_score = sum(scores) / len(scores) if scores else 0.0
    version = max(versions) if versions else 1

    derived_from = None
    if root_entry.derived_from:
        parent_id = root_entry.derived_from[0]
        for p_root_id, p_member_ids in assembled:
            if parent_id in p_member_ids:
                derived_from = p_root_id
                break

    return {
        "tree_id": treeId,
        "title": root_entry.title,
        "summary": root_entry.body,
        "type": root_entry.type.value
        if hasattr(root_entry.type, "value")
        else root_entry.type,
        "member_count": len(target_members),
        "vote_total": int(vote_total),
        "composite_score": int(composite_score),
        "version": version,
        "voted": voted,
        "derived_from": derived_from,
        "nodes": nodes,
    }


# Defined AFTER /canon/storylines and /canon/storylines/{treeId} so the parameterized
# {id} route does not shadow those more specific paths (FastAPI matches in order).
@router.get("/canon/{id}")
def get_canon_detail(id: str, authorization: str | None = Header(None)):
    """GET /canon/{id} -> full entity detail (lore, related entities, storylines it appears in); opening it discovers the node."""
    store = deps.get_store()
    user_id = deps.get_user_id_from_token(authorization)
    entry = store.get_canon_entry(id)
    if not entry:
        raise HTTPException(status_code=404, detail="Canon entry not found")

    store.save_discovery(user_id, id)

    resolved_references = []
    if entry.references:
        for ref_id in entry.references:
            ref_entry = store.get_canon_entry(ref_id)
            if ref_entry:
                resolved_references.append(
                    {
                        "id": ref_entry.id,
                        "title": ref_entry.title,
                        "type": ref_entry.type.value
                        if hasattr(ref_entry.type, "value")
                        else ref_entry.type,
                    }
                )

    active_w_id = deps.active_world_id()
    all_entries = store.list_canon_entries(active_w_id)
    referenced_by = []
    for e in all_entries:
        if e.references and id in e.references:
            referenced_by.append(
                {
                    "id": e.id,
                    "title": e.title,
                    "type": e.type.value if hasattr(e.type, "value") else e.type,
                }
            )

    assembled = assemble_trees(all_entries)
    storylines = []
    for root_id, member_ids in assembled:
        if id in member_ids:
            storylines.append(root_id)

    return {
        "id": entry.id,
        "world_id": entry.world_id,
        "type": entry.type.value if hasattr(entry.type, "value") else entry.type,
        "title": entry.title,
        "body": entry.body,
        "contributor_id": entry.contributor_id,
        "version": entry.version,
        "map_meta": entry.map_meta.model_dump() if entry.map_meta else None,
        "references": resolved_references,
        "referenced_by": referenced_by,
        "storylines": storylines,
        "discovered": True,
    }


class VotePayload(BaseModel):
    tree_id: str


@router.post("/vote")
def post_vote(payload: VotePayload, authorization: str | None = Header(None)):
    """POST /vote -> Record user vote, check threshold to run showcase pipeline async"""
    store = deps.get_store()
    user_id = deps.get_user_id_from_token(authorization, strict=True)
    tree_id = payload.tree_id

    existing_votes = store.get_votes_for_tree(tree_id)
    if any(v.voter_id == user_id for v in existing_votes):
        vote_total = sum(v.weight for v in existing_votes)
        return {
            "ok": True,
            "tree_id": tree_id,
            "vote_total": int(vote_total),
            "voted": True,
        }

    new_vote = Vote(
        id=f"vote_{uuid.uuid4()}",
        voter_id=user_id,
        tree_id=tree_id,
        weight=1.0,
        created_at=datetime.now(UTC),
    )
    store.save_vote(new_vote)

    all_votes = store.get_votes_for_tree(tree_id)
    vote_total = sum(v.weight for v in all_votes)


    min_votes = 10
    min_composite_score = 70.0
    if os.path.exists(POLICY_PATH):
        try:
            with open(POLICY_PATH) as f:
                policy = yaml.safe_load(f) or {}
                showcase_cfg = policy.get("showcase", {})
                trigger_cfg = showcase_cfg.get("trigger", {})
                min_votes = trigger_cfg.get("min_votes", 10)
                min_composite_score = trigger_cfg.get("min_composite_score", 70.0)
        except Exception:
            pass

    # 2. Calculate composite score (tree assembly scoped to the tree's world)
    root_entry = store.get_canon_entry(tree_id)
    canon_entries = store.list_canon_entries(
        root_entry.world_id if root_entry else None
    )
    assembled = assemble_trees(canon_entries)
    target_members = []
    for root_id, member_ids in assembled:
        if root_id == tree_id:
            target_members = member_ids
            break

    scores = []
    for member_id in target_members:
        contrib_id = member_id[6:] if member_id.startswith("canon_") else member_id
        score = store.get_points_for_contribution(contrib_id)
        if score is not None:
            scores.append(score)
    composite_score = sum(scores) / len(scores) if scores else 0.0

    # 3. Check trigger eligibility
    if vote_total >= min_votes and composite_score >= min_composite_score:
        existing_jobs = store.list_showcase_jobs()
        if not any(job.tree_id == tree_id for job in existing_jobs):
            trigger_showcase_task(tree_id)

    return {
        "ok": True,
        "tree_id": tree_id,
        "vote_total": int(vote_total),
        "voted": True,
    }

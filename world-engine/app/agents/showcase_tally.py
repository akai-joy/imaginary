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

import logging
import os
import uuid
from datetime import datetime
from typing import Any

import yaml
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types

from app.core.config import POLICY_PATH
from app.core.store import get_store
from app.core.types import CanonEntry, ShowcaseJob, ShowcaseJobStatus, StorylineTree

logger = logging.getLogger(__name__)


def load_policy_config() -> dict:
    """Loads configuration policies from policy.yaml."""
    if os.path.exists(POLICY_PATH):
        try:
            with open(POLICY_PATH) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load policy.yaml: %s", e)
    return {}


def get_model_for_role(role: str) -> str:
    """Gets the configured model name for a specific role/node."""
    policy = load_policy_config()
    return policy.get("models", {}).get(role, "gemini-3.5-flash")


def assemble_trees(canon_entries: list[CanonEntry]) -> list[tuple[str, list[str]]]:
    """Assembles trees from root CanonEntries by recursively walking derived_from edges."""
    # Roots are entries with no parent references in derived_from
    roots = [entry for entry in canon_entries if not entry.derived_from]

    trees = []
    for root in roots:
        member_ids = {root.id}
        added = True
        while added:
            added = False
            for entry in canon_entries:
                if entry.id not in member_ids:
                    # If this entry builds on any entry currently in our tree, include it
                    if any(parent_id in member_ids for parent_id in entry.derived_from):
                        member_ids.add(entry.id)
                        added = True
        trees.append((root.id, list(member_ids)))
    return trees


def showcase_tally_node(ctx: Context, node_input: Any):
    """Tally/Trigger Node for Showcase subgraph.

    Assembles qualifying StorylineTrees, ranks them by combined votes and score,
    and emits ShowcaseJobs for newly qualified trees.
    """
    store = get_store()

    # 1. Fetch all canon entries and assemble storyline trees
    canon_entries = store.list_canon_entries()
    assembled = assemble_trees(canon_entries)

    # 2. Retrieve policy configs
    policy = load_policy_config()
    showcase_cfg = policy.get("showcase", {})
    trigger_cfg = showcase_cfg.get("trigger", {})
    min_votes = trigger_cfg.get("min_votes", 10)
    min_composite_score = trigger_cfg.get("min_composite_score", 70.0)
    weights = trigger_cfg.get("rank_weight", {"votes": 0.6, "score": 0.4})
    w_votes = weights.get("votes", 0.6)
    w_score = weights.get("score", 0.4)

    # Get existing showcase jobs to avoid duplicates
    existing_jobs = store.list_showcase_jobs()
    existing_tree_ids = {job.tree_id for job in existing_jobs}

    storyline_trees = []
    qualifying_new_trees = []

    for root_id, member_ids in assembled:
        # Calculate vote total
        votes = store.get_votes_for_tree(root_id)
        vote_total = sum(vote.weight for vote in votes)

        # Calculate composite score (average score of all entries in the tree)
        scores = []
        for member_id in member_ids:
            # Strip "canon_" prefix if present to find contribution points in ledger
            contrib_id = member_id[6:] if member_id.startswith("canon_") else member_id
            score = store.get_points_for_contribution(contrib_id)
            if score is not None:
                scores.append(score)

        composite_score = sum(scores) / len(scores) if scores else 0.0

        tree = StorylineTree(
            tree_id=root_id,
            root_id=root_id,
            member_ids=member_ids,
            vote_total=float(vote_total),
            composite_score=float(composite_score),
        )
        storyline_trees.append(tree)

        # Check if the tree meets the policy thresholds
        if vote_total >= min_votes and composite_score >= min_composite_score:
            if root_id not in existing_tree_ids:
                qualifying_new_trees.append(tree)

    # 3. Rank qualifying new trees
    # Sort descending by combined rank score: votes * w_votes + score * w_score
    ranked_trees = sorted(
        qualifying_new_trees,
        key=lambda t: w_votes * t.vote_total + w_score * t.composite_score,
        reverse=True,
    )

    new_jobs = []
    # Emit ShowcaseJobs
    for idx, tree in enumerate(ranked_trees):
        # Single top-ranked tree per cycle gets reel, all others get comic
        media_type = "reel" if idx == 0 else "comic"
        job = ShowcaseJob(
            id=f"job_{uuid.uuid4()}",
            tree_id=tree.tree_id,
            media_type=media_type,
            status=ShowcaseJobStatus.QUEUED,
            created_at=datetime.utcnow(),
        )
        store.save_showcase_job(job)
        new_jobs.append(job)
        logger.info(
            "Emitted ShowcaseJob %s (type=%s) for tree %s (votes=%.1f, score=%.1f)",
            job.id,
            media_type,
            tree.tree_id,
            tree.vote_total,
            tree.composite_score,
        )

    # Yield info summary as markdown text
    summary_parts = [
        "### Showcase Tally Results",
        f"- **Total Storyline Trees Analyzed**: {len(storyline_trees)}",
        f"- **New Qualifying Trees Found**: {len(qualifying_new_trees)}",
        f"- **Showcase Jobs Emitted**: {len(new_jobs)}",
        "\n**Details of Analyzed Trees**:",
    ]
    for tree in storyline_trees:
        is_qual = (
            "Yes"
            if (
                tree.vote_total >= min_votes
                and tree.composite_score >= min_composite_score
            )
            else "No"
        )
        already_emitted = "Yes" if tree.tree_id in existing_tree_ids else "No"
        summary_parts.append(
            f"- Tree `{tree.tree_id}`: Votes={tree.vote_total} (min {min_votes}), "
            f"Score={tree.composite_score:.1f} (min {min_composite_score}), "
            f"Qualifies={is_qual}, Already Emitted={already_emitted}"
        )

    if new_jobs:
        summary_parts.append("\n**Newly Created Showcase Jobs**:")
        for job in new_jobs:
            summary_parts.append(
                f"- Job `{job.id}`: Tree `{job.tree_id}`, Media Type `{job.media_type}`"
            )

    yield Event(
        content=types.Content(
            role="model", parts=[types.Part.from_text(text="\n".join(summary_parts))]
        )
    )

    yield Event(output=new_jobs)

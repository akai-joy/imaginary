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
import shutil
from datetime import datetime, timezone
from typing import Any

from google.adk.agents.context import Context
from google.adk.events.event import Event

from app.core.store import get_store
from app.core.types import CanonEntry, Contribution, LedgerEntry, MediaAsset, ShowcaseJob, ContributionStatus, ShowcaseJobStatus

logger = logging.getLogger(__name__)


def ingest_controller_node(ctx: Context, node_input: Contribution):
    """Deterministic Ingest Controller.

    Performs all side effects for the Ingest workflow (LedgerEntry, CanonEntry, Contribution saves)
    with strict validation and value clamping.
    """
    store = get_store()
    contrib = node_input

    # 1. Process scoring proposal
    scoring_proposal = ctx.state.get("scoring_proposal")
    if scoring_proposal:
        # Value clamping: points constrained to 0-100
        points_delta = scoring_proposal.get("points_delta", 0)
        points_delta = max(0, min(100, int(points_delta)))

        # Save LedgerEntry
        ledger_entry = LedgerEntry(
            contribution_id=contrib.id,
            author_id=contrib.author_id,
            points_delta=points_delta,
            reason=scoring_proposal.get("reason", "Scored by controller"),
            created_at=datetime.now(timezone.utc),
        )
        store.save_ledger_entry(ledger_entry)
        logger.info("Controller saved LedgerEntry with clamped score: %d", points_delta)

    # 2. Process narrator proposal
    narrator_proposal = ctx.state.get("narrator_proposal")
    if narrator_proposal:
        new_entry_data = narrator_proposal.get("new_entry")
        contrib_status = narrator_proposal.get("contrib_status")

        # Apply the proposed status
        if contrib_status:
            contrib.status = ContributionStatus(contrib_status)

        # If accepted, save the CanonEntry
        if contrib.status == "accepted" and new_entry_data:
            # Build and validate CanonEntry
            new_entry = CanonEntry(
                id=new_entry_data["id"],
                type=new_entry_data["type"],
                title=new_entry_data["title"],
                body=new_entry_data["body"],
                contributor_id=new_entry_data["contributor_id"],
                derived_from=new_entry_data["derived_from"],
                references=new_entry_data.get("references", []),
                version=new_entry_data["version"],
                created_at=datetime.fromisoformat(new_entry_data["created_at"]),
            )

            # Honour the lineage/refs the contributor chose in the UI: trusted structure,
            # applied deterministically here rather than inferred by the Provenance LLM.
            if contrib.derived_from:
                new_entry.derived_from = list(
                    dict.fromkeys([*new_entry.derived_from, *contrib.derived_from])
                )
            if contrib.references:
                new_entry.references = list(
                    dict.fromkeys([*new_entry.references, *contrib.references])
                )

            store.save_canon_entry(new_entry)
            logger.info("Controller saved CanonEntry: %s", new_entry.id)

    # Always save the final Contribution status
    store.save_contribution(contrib)
    logger.info("Controller saved Contribution status: %s", contrib.status)

    yield Event(output=contrib)


def showcase_controller_node(ctx: Context, node_input: list[ShowcaseJob]):
    """Deterministic Showcase Controller.

    Performs all side effects for the Showcase workflow (ShowcaseJob saves, GCS copies, MediaAsset saves)
    with strict validation and job prefix constraints.
    """
    store = get_store()
    jobs = node_input or []

    # 1. Process tally proposal
    tally_proposal = ctx.state.get("tally_proposal")
    if tally_proposal:
        # If tally proposed new jobs, write them to the store
        proposed_jobs = tally_proposal.get("new_jobs", [])
        for job_data in proposed_jobs:
            job = ShowcaseJob.model_validate(job_data)
            store.save_showcase_job(job)
            logger.info("Controller saved tally-proposed job: %s", job.id)

    # 2. Process storyboard proposal
    storyboard_proposal = ctx.state.get("storyboard_proposal")
    if storyboard_proposal:
        for job_id, data in storyboard_proposal.items():
            job = store.get_showcase_job(job_id)
            if job:
                if data.get("status"):
                    job.status = ShowcaseJobStatus(data.get("status"))
                job.storyboard_json = data.get("storyboard_json")
                store.save_showcase_job(job)
                logger.info("Controller updated storyboard status for job: %s", job.id)

    # Process director proposal
    director_proposal = ctx.state.get("director_proposal")
    if director_proposal:
        for job_id, data in director_proposal.items():
            job = store.get_showcase_job(job_id)
            if job:
                if data.get("status"):
                    job.status = ShowcaseJobStatus(data.get("status"))
                if data.get("storyboard_json"):
                    job.storyboard_json = data.get("storyboard_json")
                store.save_showcase_job(job)
                
                # Also copy prompt sheet to gcs_mock if available
                prompt_sheet_path = data.get("prompt_sheet_path")
                prompt_sheet_filename = data.get("prompt_sheet_filename")
                if prompt_sheet_path and prompt_sheet_filename:
                    # Copy to gcs_mock/world-engine-showcase/job_id_prompt_sheet.txt
                    dest_dir = os.path.join("gcs_mock", "world-engine-showcase")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, prompt_sheet_filename)
                    try:
                        import shutil
                        if os.path.exists(prompt_sheet_path):
                            shutil.copy2(prompt_sheet_path, dest_path)
                            logger.info("Controller wrote prompt sheet to GCS: %s", dest_path)
                    except Exception as e:
                        logger.error("Controller failed to copy prompt sheet: %s", e)
                
                logger.info("Controller updated director status for job: %s", job.id)

    # 3. Process media proposal
    media_proposal = ctx.state.get("media_proposal")
    if media_proposal:
        for job_id, data in media_proposal.items():
            job = store.get_showcase_job(job_id)
            if job:
                if data.get("status"):
                    job.status = ShowcaseJobStatus(data.get("status"))
                store.save_showcase_job(job)
                logger.info("Controller updated media status for job: %s", job.id)

    # 4. Process publish proposal
    publish_proposal = ctx.state.get("publish_proposal")
    if publish_proposal:
        for job_id, data in publish_proposal.items():
            job = store.get_showcase_job(job_id)
            if not job:
                continue

            # Perform GCS writes (copies from cache to gcs_mock)
            src_path = data.get("src_path")
            dest_path = data.get("dest_path")
            bucket = data.get("bucket")

            # CONFINE GCS writes strictly to the job's prefix
            if dest_path:
                basename = os.path.basename(dest_path)
                # Check that destination filename starts with the job's ID
                if not basename.startswith(job.id):
                    raise ValueError(
                        f"Security Block: GCS write path '{dest_path}' does not match prefix of job '{job.id}'."
                    )

            # Perform mock file copy
            if src_path and dest_path:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if os.path.exists(src_path):
                    shutil.copy2(src_path, dest_path)
                    logger.info("Controller wrote to GCS: %s", dest_path)
                else:
                    # Mock content
                    with open(dest_path, "w") as f:
                        f.write(f"Mock GCS Media Asset Data for job {job.id}")
                    logger.warning(
                        "Source asset missing. Created empty mock GCS file: %s",
                        dest_path,
                    )

            # Save MediaAsset to store
            asset_data = data.get("media_asset")
            if asset_data:
                asset = MediaAsset(
                    id=asset_data["id"],
                    job_id=asset_data["job_id"],
                    tree_id=asset_data["tree_id"],
                    kind=asset_data["kind"],
                    gcs_url=asset_data["gcs_url"],
                    caption=asset_data["caption"],
                    hashtags=asset_data["hashtags"],
                    contributor_ids=asset_data["contributor_ids"],
                    created_at=datetime.fromisoformat(asset_data["created_at"]),
                )
                store.save_media_asset(asset)
                logger.info("Controller saved MediaAsset: %s", asset.id)

            # Update job status
            if data.get("status"):
                job.status = ShowcaseJobStatus(data.get("status"))
            store.save_showcase_job(job)
            logger.info("Controller published job: %s", job.id)

    yield Event(output=jobs)

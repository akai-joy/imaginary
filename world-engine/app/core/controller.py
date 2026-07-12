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

import logging
import os
import shutil
from datetime import UTC, datetime

from google.adk.agents.context import Context
from google.adk.events.event import Event

from app.core.store import get_store
from app.core.types import (
    CanonEntry,
    Contribution,
    ContributionStatus,
    LedgerEntry,
    MapMeta,
    MediaAsset,
    ShowcaseJob,
    ShowcaseJobStatus,
)

logger = logging.getLogger(__name__)

# Normalized world-map bounds. The controller (never the LLM) is authoritative for
# clamping Cartographer-proposed coordinates into this range.
MAP_MIN = 0.0
MAP_MAX = 100.0


def _clamp_coord(value) -> float:
    try:
        return max(MAP_MIN, min(MAP_MAX, float(value)))
    except (TypeError, ValueError):
        return MAP_MIN


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
            created_at=datetime.now(UTC),
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

            # Scope the canon entry to the contribution's world (trusted structure,
            # stamped deterministically — never inferred by an LLM node).
            new_entry.world_id = contrib.world_id

            # Apply the Cartographer's map placement proposal. The controller is the
            # only writer of map_meta and clamps coordinates to the map bounds.
            cartographer_proposal = ctx.state.get("cartographer_proposal")
            if cartographer_proposal:
                map_meta_data = cartographer_proposal.get("map_meta")
                if map_meta_data:
                    new_entry.map_meta = MapMeta(
                        x=_clamp_coord(map_meta_data.get("x")),
                        y=_clamp_coord(map_meta_data.get("y")),
                        region=map_meta_data.get("region", ""),
                        near=list(map_meta_data.get("near", [])),
                    )
                # A character/beast/spell is anchored by referencing its "located-in"
                # place, so the place's detail can list who/what is found there.
                located_in = cartographer_proposal.get("located_in")
                if located_in and located_in not in new_entry.references:
                    new_entry.references.append(located_in)

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

            # Keep the semantic index in step with canon; retrieval degrades to
            # keyword search if this ever fails, so indexing is best-effort.
            try:
                from app.core.retrieval import index_canon_entry

                index_canon_entry(store, new_entry)
            except Exception as e:
                logger.warning("Embedding index skipped for %s: %s", new_entry.id, e)

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
                            logger.info(
                                "Controller wrote prompt sheet to GCS: %s", dest_path
                            )
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


def cartography_controller_node(ctx: Context, node_input: CanonEntry):
    """Deterministic Cartography Controller.

    Copies cached tiles and master map canvases to the GCS mock folder, validates paths,
    saves the map tile MediaAsset, and updates the World model.
    """
    store = get_store()
    entry = node_input

    proposal = ctx.state.get("cartography_proposal")
    if proposal:
        world_id = proposal["world_id"]
        location_id = proposal["location_id"]
        version = proposal["version"]
        contributor_ids = proposal["contributor_ids"]

        # Validate and copy tile
        tile_src = proposal["tile_src_path"]
        tile_dest = proposal["tile_dest_path"]
        tile_filename = proposal["tile_filename"]

        if tile_dest:
            basename = os.path.basename(tile_dest)
            if not tile_dest.startswith("gcs_mock/world-engine-atlas/"):
                raise ValueError(
                    f"Security Block: Out-of-prefix GCS write attempt for '{tile_dest}'."
                )
            if not basename.startswith(f"maptile_{location_id}_"):
                raise ValueError(
                    f"Security Block: filename '{basename}' does not match location '{location_id}'."
                )

            os.makedirs(os.path.dirname(tile_dest), exist_ok=True)
            if os.path.exists(tile_src):
                shutil.copy2(tile_src, tile_dest)
                logger.info("Cartography Controller wrote tile to GCS: %s", tile_dest)

        # Validate and copy canvas
        canvas_src = proposal["canvas_src_path"]
        canvas_dest = proposal["canvas_dest_path"]
        canvas_filename = proposal["canvas_filename"]
        canvas_version = proposal["canvas_version"]

        if canvas_dest:
            basename = os.path.basename(canvas_dest)
            if not canvas_dest.startswith("gcs_mock/world-engine-atlas/"):
                raise ValueError(
                    f"Security Block: Out-of-prefix GCS write attempt for '{canvas_dest}'."
                )
            if not basename.startswith(f"mapcanvas_{world_id}_"):
                raise ValueError(
                    f"Security Block: filename '{basename}' does not match world '{world_id}'."
                )

            os.makedirs(os.path.dirname(canvas_dest), exist_ok=True)
            if os.path.exists(canvas_src):
                shutil.copy2(canvas_src, canvas_dest)
                logger.info(
                    "Cartography Controller wrote canvas to GCS: %s", canvas_dest
                )

        # Save tile MediaAsset
        tile_url = f"http://localhost:8000/gcs_mock/world-engine-atlas/{tile_filename}"
        asset_id = f"asset_tile_{location_id}_v{version}"
        asset = MediaAsset(
            id=asset_id,
            job_id="",
            tree_id="",
            kind="map_tile",
            gcs_url=tile_url,
            caption=f"Map tile of {entry.title}. AI-generated.",
            hashtags=[],
            contributor_ids=contributor_ids,
            created_at=datetime.now(UTC),
            node_id=location_id,
            world_id=world_id,
        )
        store.save_media_asset(asset)
        logger.info("Cartography Controller saved tile MediaAsset: %s", asset_id)

        # Update World map image and version
        canvas_url = (
            f"http://localhost:8000/gcs_mock/world-engine-atlas/{canvas_filename}"
        )
        store.save_world_map_image(world_id, canvas_url, canvas_version)
        logger.info(
            "Cartography Controller updated world map image: %s (v%d)",
            canvas_url,
            canvas_version,
        )

    yield Event(output=entry)

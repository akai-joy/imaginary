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
"""Internal hooks: Cloud Tasks callbacks and admin/cron endpoints."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.api.services.atlas_runner import run_atlas
from app.api.services.contribution_runner import run_contribution_job
from app.api.services.showcase_runner import run_showcase

logger = logging.getLogger(__name__)

router = APIRouter()


class RunShowcasePayload(BaseModel):
    tree_id: str


@router.post("/internal/run-showcase")
def post_internal_run_showcase(payload: RunShowcasePayload):
    """Internal endpoint called to execute the showcase workflow for a tree."""
    store = deps.get_store()
    from app.core.lifecycle import tick

    tick(store)

    existing_jobs = store.list_showcase_jobs()
    if any(job.tree_id == payload.tree_id for job in existing_jobs):
        logger.info(
            "Showcase job already exists for tree %s, skipping.", payload.tree_id
        )
        return {"ok": True, "message": "Already exists"}

    try:
        run_showcase()
        logger.info("Showcase workflow executed successfully via internal endpoint.")
        return {"ok": True}
    except Exception as e:
        logger.error("Failed to run showcase workflow in internal handler: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


class RunContributionPayload(BaseModel):
    job_id: str
    pipeline_kwargs: dict


@router.post("/internal/run-contribution")
def post_internal_run_contribution(payload: RunContributionPayload):
    """POST /internal/run-contribution -> execute an async contribution pipeline (internal Cloud Tasks callback)."""
    try:
        run_contribution_job(payload.job_id, payload.pipeline_kwargs)
        return {"ok": True, "job_id": payload.job_id}
    except Exception as e:
        logger.error("Failed to run contribution job in internal handler: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


class ScheduleWorldPayload(BaseModel):
    world_id: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None


@router.post("/internal/world/schedule")
def post_internal_world_schedule(
    payload: ScheduleWorldPayload, authorization: str | None = Header(None)
):
    """POST /internal/world/schedule -> open/schedule a new themed world drop (internal admin hook)."""
    _user_id = deps.get_user_id_from_token(authorization)
    store = deps.get_store()

    target_id = payload.world_id
    if not target_id:
        target_id = deps.active_world_id()

    opens_at = payload.opens_at
    if opens_at and opens_at.tzinfo is None:
        opens_at = opens_at.replace(tzinfo=UTC)

    closes_at = payload.closes_at
    if closes_at and closes_at.tzinfo is None:
        closes_at = closes_at.replace(tzinfo=UTC)

    from app.core.lifecycle import schedule_world

    w = schedule_world(store, target_id, opens_at=opens_at, closes_at=closes_at)
    if not w:
        raise HTTPException(status_code=404, detail=f"World {target_id} not found")

    return {
        "world_id": w.id,
        "theme": w.theme,
        "opens_at": w.opens_at.isoformat() if w.opens_at else None,
        "closes_at": w.closes_at.isoformat() if w.closes_at else None,
        "status": w.status.value if hasattr(w.status, "value") else w.status,
    }


@router.post("/internal/tick")
def post_internal_tick(authorization: str | None = Header(None)):
    """POST /internal/tick -> advance the world lifecycle (close expired drops); internal cron hook."""
    store = deps.get_store()
    from app.core.lifecycle import tick

    w = tick(store)
    return {
        "active_world": {
            "world_id": w.id,
            "status": w.status.value if hasattr(w.status, "value") else w.status,
            "closes_at": w.closes_at.isoformat() if w.closes_at else None,
        }
        if w
        else None
    }


class PaintAtlasPayload(BaseModel):
    location_id: str


@router.post("/internal/paint-atlas")
def post_internal_paint_atlas(payload: PaintAtlasPayload):
    """POST /internal/paint-atlas -> run the Atlas illustrator for a location (internal Cloud Tasks callback)."""
    store = deps.get_store()
    entry = store.get_canon_entry(payload.location_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Location canon entry not found")

    try:
        run_atlas(payload.location_id)
        return {"ok": True, "location_id": payload.location_id}
    except Exception as e:
        logger.error("Failed to run paint-atlas task in internal handler: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

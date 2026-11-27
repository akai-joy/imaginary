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
"""Contribution intake: async 202 + job id; the LLM pipeline runs off-request.

The fast checks (auth, closed-window) stay synchronous so a sealed world still
answers instantly; everything slow happens in services/contribution_runner.
"""

import json
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import deps
from app.api.services.contribution_runner import dispatch_contribution_job
from app.core.lifecycle import is_window_open, tick
from app.core.types import ContributionJob, ContributionJobStatus

logger = logging.getLogger(__name__)

router = APIRouter()


class ContributePayload(BaseModel):
    title: str
    type: str
    body: str
    derived_from: list[str] = []
    references: list[str] = []
    world_id: str | None = None


@router.post("/contribute", status_code=202)
def post_contribute(
    payload: ContributePayload, authorization: str | None = Header(None)
):
    """POST /contribute -> 202 + job id; poll GET /contribute/jobs/{job_id} for the verdict."""
    user_id = deps.get_user_id_from_token(authorization, strict=True)

    store = deps.get_store()

    active_w = tick(store)
    if not active_w or not is_window_open(active_w):
        return JSONResponse(
            status_code=200,
            content={
                "status": "rejected",
                "verdict": "CLOSED",
                "score": 0,
                "message": "This world has closed — it's now an archived collectible.",
            },
        )

    world_id_to_use = payload.world_id
    if world_id_to_use is None:
        world_id_to_use = active_w.id

    job = ContributionJob(
        id=f"cjob_{uuid.uuid4()}",
        world_id=world_id_to_use,
        user_id=user_id,
    )
    store.save_contribution_job(job)

    dispatch_contribution_job(
        job.id,
        {
            "user_id": user_id,
            "id_token": authorization.replace("Bearer ", "") if authorization else None,
            "world_id": world_id_to_use,
            "title": payload.title,
            "entry_type": payload.type,
            "body": payload.body,
            "derived_from": payload.derived_from,
            "references": payload.references,
        },
    )

    return {"job_id": job.id, "status": ContributionJobStatus.QUEUED.value}


@router.get("/contribute/jobs/{job_id}")
def get_contribution_job(job_id: str, authorization: str | None = Header(None)):
    """GET /contribute/jobs/{job_id} -> job status, plus the verdict once done."""
    user_id = deps.get_user_id_from_token(authorization)
    store = deps.get_store()
    job = store.get_contribution_job(job_id)
    # Treat other users' jobs as nonexistent rather than leaking their status.
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Contribution job not found")

    status = job.status.value if hasattr(job.status, "value") else job.status
    result = json.loads(job.result_json) if job.result_json else None
    return {"job_id": job.id, "status": status, "result": result}

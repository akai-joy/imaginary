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
"""Contribution intake: runs the full world_engine_workflow pipeline."""

import json
import logging

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.api import deps
from app.api.services.atlas_runner import trigger_atlas_task

logger = logging.getLogger(__name__)

router = APIRouter()


class ContributePayload(BaseModel):
    title: str
    type: str
    body: str
    derived_from: list[str] = []
    references: list[str] = []
    world_id: str | None = None


@router.post("/contribute")
def post_contribute(
    payload: ContributePayload, authorization: str | None = Header(None)
):
    """POST /contribute -> Execute world_engine_workflow ingest synchronously"""
    user_id = deps.get_user_id_from_token(authorization, strict=True)

    store = deps.get_store()
    from app.core.lifecycle import is_window_open, tick

    active_w = tick(store)
    if not active_w or not is_window_open(active_w):
        return {
            "status": "rejected",
            "verdict": "CLOSED",
            "score": 0,
            "message": "This world has closed — it's now an archived collectible.",
        }

    world_id_to_use = payload.world_id
    if world_id_to_use is None:
        world_id_to_use = active_w.id

    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.agent import app as agent_app
    from app.core.runner_factory import create_runner

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id=user_id, app_name="app")
    runner = create_runner(agent_app, session_service)

    # Serialize structured user payload
    input_data = {
        "user_text": f"Type: {payload.type}. Title: {payload.title}. Body: {payload.body}",
        "author_id": user_id,
        "id_token": authorization.replace("Bearer ", "") if authorization else None,
        "world_id": world_id_to_use,
        "derived_from": payload.derived_from,
        "references": payload.references,
    }

    message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(input_data))]
    )

    try:
        events = list(
            runner.run(new_message=message, user_id=user_id, session_id=session.id)
        )

        # Retrieve the final outcome from session state
        session_obj = session_service.get_session_sync(
            user_id=user_id, session_id=session.id, app_name="app"
        )
        state = session_obj.state if session_obj else {}

        # Moderation halts the graph via the BLOCK route (no error_message), so detect
        # it from the structured result the node writes — this is what surfaces the
        # "blocked by the Guardian" verdict (category + reason) to the UI.
        moderation_block = state.get("moderation_block")
        if moderation_block:
            return {
                "status": "blocked",
                "verdict": "BLOCK",
                "category": moderation_block.get("category", "policy"),
                "score": 0,
                "message": moderation_block.get("reason", "Blocked by moderation."),
            }

        verdict = "ALLOW"
        status = "accepted"
        score = 0
        reason = ""

        # Check for direct execution errors
        for event in events:
            event_err = getattr(event, "error_message", None) or getattr(
                event, "error_code", None
            )
            if event_err:
                reason = str(event_err)
                if "Security Block" in reason:
                    verdict = "BLOCK"
                    status = "blocked"
                elif "contradiction" in reason.lower() or "CONTRADICTION" in reason:
                    status = "rejected"
                    verdict = "ALLOW"
                else:
                    status = "rejected"
                break

        # Process scoring and narrator proposals if no error occurred
        if status == "accepted":
            scoring_proposal = state.get("scoring_proposal", {})
            score = scoring_proposal.get("points_delta", 0)
            reason = scoring_proposal.get("reason", "Successfully merged into canon.")

            narrator_proposal = state.get("narrator_proposal", {})
            if narrator_proposal:
                status = narrator_proposal.get("contrib_status", "accepted")
                new_entry = narrator_proposal.get("new_entry")
                if (
                    status == "accepted"
                    and new_entry
                    and new_entry.get("type") == "location"
                ):
                    try:
                        trigger_atlas_task(new_entry["id"])
                    except Exception as e:
                        logger.error("Failed to trigger atlas task: %s", e)

        return {"status": status, "verdict": verdict, "score": score, "message": reason}

    except Exception as e:
        logger.error("Workflow execution failed: %s", e)
        err_msg = str(e)
        if "Security Block" in err_msg:
            return {
                "status": "blocked",
                "verdict": "BLOCK",
                "score": 0,
                "message": err_msg,
            }
        elif "contradiction" in err_msg.lower():
            return {
                "status": "rejected",
                "verdict": "ALLOW",
                "score": 0,
                "message": err_msg,
            }
        else:
            return {
                "status": "rejected",
                "verdict": "ALLOW",
                "score": 0,
                "message": f"Execution failed: {err_msg}",
            }

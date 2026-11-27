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
"""Async contribution execution: the 30-60s LLM pipeline runs here, off the
request path. POST /contribute answers 202 + job id immediately; this module
executes the workflow and persists the verdict on the job row.

The submission payload travels with the dispatch (closure locally, Cloud Tasks
body in the cloud) — only status/verdict are persisted, never the id_token.
"""

import json
import logging
from datetime import UTC, datetime

from google.genai import types

from app.agent import app as agent_app
from app.api import deps
from app.api.services.atlas_runner import trigger_atlas_task
from app.api.services.background import enqueue_cloud_task, is_local_dev, submit_once
from app.core.runner_factory import create_runner
from app.core.types import ContributionJobStatus

logger = logging.getLogger(__name__)


def execute_contribution_pipeline(
    *,
    user_id: str,
    id_token: str | None,
    world_id: str,
    title: str,
    entry_type: str,
    body: str,
    derived_from: list[str],
    references: list[str],
) -> dict:
    """Run the full world_engine_workflow for one contribution and return the verdict dict.

    This is the exact logic the old synchronous POST /contribute inlined.
    """
    session_service = deps.get_session_service()
    session = session_service.create_session_sync(user_id=user_id, app_name="app")
    runner = create_runner(agent_app, session_service)

    # Serialize structured user payload
    input_data = {
        "user_text": f"Type: {entry_type}. Title: {title}. Body: {body}",
        "author_id": user_id,
        "id_token": id_token,
        "world_id": world_id,
        "derived_from": derived_from,
        "references": references,
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
    finally:
        try:
            session_service.delete_session_sync(
                app_name="app", user_id=user_id, session_id=session.id
            )
        except Exception:
            pass


def run_contribution_job(job_id: str, pipeline_kwargs: dict) -> None:
    """Mark the job running, execute the pipeline, persist the verdict."""
    store = deps.get_store()
    job = store.get_contribution_job(job_id)
    if not job:
        logger.warning("run_contribution_job: job %s not found.", job_id)
        return

    job.status = ContributionJobStatus.RUNNING
    job.updated_at = datetime.now(UTC)
    store.save_contribution_job(job)

    result = execute_contribution_pipeline(**pipeline_kwargs)

    job.status = ContributionJobStatus.DONE
    job.result_json = json.dumps(result)
    job.updated_at = datetime.now(UTC)
    store.save_contribution_job(job)


def enqueue_contribution_task(job_id: str, pipeline_kwargs: dict) -> None:
    """Enqueue the contribution pipeline on Cloud Tasks (the production async path)."""
    enqueue_cloud_task(
        "/internal/run-contribution",
        {"job_id": job_id, "pipeline_kwargs": pipeline_kwargs},
        log_label=f"contribution job_id={job_id}",
    )


def dispatch_contribution_job(job_id: str, pipeline_kwargs: dict) -> None:
    """Fire the contribution pipeline: shared background pool locally, Cloud Tasks in the cloud."""
    if is_local_dev():
        submit_once(f"contribute:{job_id}", run_contribution_job, job_id, pipeline_kwargs)
    else:
        try:
            enqueue_contribution_task(job_id, pipeline_kwargs)
        except Exception as e:
            logger.error("Failed to enqueue contribution task: %s", e)
            # Fail the job now — otherwise it sits "queued" forever and the
            # client polls into its timeout instead of seeing an error.
            store = deps.get_store()
            job = store.get_contribution_job(job_id)
            if job:
                job.status = ContributionJobStatus.DONE
                job.result_json = json.dumps(
                    {
                        "status": "rejected",
                        "verdict": "ALLOW",
                        "score": 0,
                        "message": f"Execution failed: could not enqueue job ({e})",
                    }
                )
                job.updated_at = datetime.now(UTC)
                store.save_contribution_job(job)

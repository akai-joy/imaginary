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
import json
import uuid
import threading
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, Header, HTTPException, Body
from pydantic import BaseModel
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.core.store import get_store
from app.core.types import Contribution, ContributionStatus, ContributionType, Vote, MediaAsset
from app.agents.showcase_tally import assemble_trees

setup_telemetry()
try:
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
    is_cloud_logging = True
except Exception:
    logger = logging.getLogger(__name__)
    is_cloud_logging = False

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "world-engine"
app.description = "API for interacting with the Agent world-engine"


def get_user_id_from_token(authorization: Optional[str]) -> str:
    """Helper to extract user identity from Firebase Auth ID token, fallback to local dev user."""
    if not authorization or not authorization.startswith("Bearer "):
        return "playground_user"

    token_str = authorization.replace("Bearer ", "")
    firebase_app_id = os.environ.get("VITE_FIREBASE_APP_ID") or os.environ.get("FIREBASE_APP_ID")
    if firebase_app_id:
        try:
            import firebase_admin
            from firebase_admin import auth

            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app()

            decoded_token = auth.verify_id_token(token_str)
            uid = decoded_token.get("uid") or decoded_token.get("email") or "playground_user"
            return uid
        except Exception as e:
            logger.warning("Firebase token verification failed, using fallback: %s", e)

    return "playground_user"


# --- REST API Endpoints for the Front-End ---

@app.get("/canon/storylines")
def list_storylines(authorization: Optional[str] = Header(None)):
    """GET /canon/storylines -> StorylineTree[] summaries"""
    store = get_store()
    canon_entries = store.list_canon_entries()
    assembled = assemble_trees(canon_entries)
    user_id = get_user_id_from_token(authorization)

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

        storyline_trees.append({
            "tree_id": root_id,
            "title": root_entry.title,
            "summary": root_entry.body,
            "type": root_entry.type.value if hasattr(root_entry.type, "value") else root_entry.type,
            "member_count": len(member_ids),
            "vote_total": int(vote_total),
            "composite_score": int(composite_score),
            "version": version,
            "voted": voted,
            "derived_from": derived_from
        })

    return storyline_trees


@app.get("/canon/storylines/{treeId}")
def get_storyline(treeId: str, authorization: Optional[str] = Header(None)):
    """GET /canon/storylines/:treeId -> Detailed StorylineTree with nodes array"""
    store = get_store()
    canon_entries = store.list_canon_entries()
    assembled = assemble_trees(canon_entries)
    user_id = get_user_id_from_token(authorization)

    target_members = None
    for root_id, member_ids in assembled:
        if root_id == treeId:
            target_members = member_ids
            break

    if not target_members:
        raise HTTPException(status_code=404, detail="Storyline tree not found")

    root_entry = store.get_canon_entry(treeId)
    if not root_entry:
        raise HTTPException(status_code=404, detail="Root entry not found")

    votes = store.get_votes_for_tree(treeId)
    vote_total = sum(v.weight for v in votes)
    voted = any(v.voter_id == user_id for v in votes)

    # Load and map nodes sorted chronologically
    loaded_entries = []
    for member_id in target_members:
        entry = store.get_canon_entry(member_id)
        if entry:
            loaded_entries.append(entry)

    loaded_entries.sort(key=lambda x: x.created_at)

    nodes = []
    scores = []
    versions = []
    for entry in loaded_entries:
        versions.append(entry.version)
        contrib_id = entry.id[6:] if entry.id.startswith("canon_") else entry.id
        score = store.get_points_for_contribution(contrib_id)
        if score is not None:
            scores.append(score)

        nodes.append({
            "id": entry.id,
            "type": entry.type.value if hasattr(entry.type, "value") else entry.type,
            "title": entry.title,
            "contributor": entry.contributor_id,
            "version": entry.version,
            "derived_from": entry.derived_from,
            "body": entry.body
        })

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
        "type": root_entry.type.value if hasattr(root_entry.type, "value") else root_entry.type,
        "member_count": len(target_members),
        "vote_total": int(vote_total),
        "composite_score": int(composite_score),
        "version": version,
        "voted": voted,
        "derived_from": derived_from,
        "nodes": nodes
    }


class VotePayload(BaseModel):
    tree_id: str


@app.post("/vote")
def post_vote(payload: VotePayload, authorization: Optional[str] = Header(None)):
    """POST /vote -> Record user vote, check threshold to run showcase pipeline async"""
    store = get_store()
    user_id = get_user_id_from_token(authorization)
    tree_id = payload.tree_id

    existing_votes = store.get_votes_for_tree(tree_id)
    if any(v.voter_id == user_id for v in existing_votes):
        vote_total = sum(v.weight for v in existing_votes)
        return {
            "ok": True,
            "tree_id": tree_id,
            "vote_total": int(vote_total),
            "voted": True
        }

    new_vote = Vote(
        id=f"vote_{uuid.uuid4()}",
        voter_id=user_id,
        tree_id=tree_id,
        weight=1.0,
        created_at=datetime.utcnow()
    )
    store.save_vote(new_vote)

    all_votes = store.get_votes_for_tree(tree_id)
    vote_total = sum(v.weight for v in all_votes)

    # 1. Fetch policy settings
    from app.core.config import POLICY_PATH
    import yaml
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

    # 2. Calculate composite score
    canon_entries = store.list_canon_entries()
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
            # Run showcase workflow asynchronously in background thread
            def run_showcase_async():
                try:
                    from google.adk.sessions import InMemorySessionService
                    from google.adk.runners import Runner
                    from showcase.agent import showcase_workflow
                    from google.genai import types

                    session_service = InMemorySessionService()
                    session = session_service.create_session_sync(user_id="system", app_name="showcase")
                    runner = Runner(agent=showcase_workflow, session_service=session_service, app_name="showcase")

                    list(runner.run(
                        new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
                        user_id="system",
                        session_id=session.id
                    ))
                    logger.info("Background showcase workflow executed successfully.")
                except Exception as e:
                    logger.error("Failed to run background showcase workflow: %s", e)

            threading.Thread(target=run_showcase_async, daemon=True).start()

    return {
        "ok": True,
        "tree_id": tree_id,
        "vote_total": int(vote_total),
        "voted": True
    }


@app.get("/showcase")
def get_showcase():
    """GET /showcase -> MediaAsset[] items with fallback storyboard panels/scenes"""
    store = get_store()
    assets = store.list_media_assets()

    showcase_items = []
    for asset in assets:
        title = "Storyline Showcase"
        root_entry = store.get_canon_entry(asset.tree_id)
        if root_entry:
            title = root_entry.title

        # Map panels or scenes from ShowcaseJob storyboard JSON
        panels = []
        scenes = []
        job = store.get_showcase_job(asset.job_id)
        if job and job.storyboard_json:
            try:
                storyboard_data = json.loads(job.storyboard_json)
                scenes_list = storyboard_data.get("scenes", [])
                for scene in scenes_list:
                    desc = scene.get("visual_description", "")
                    if asset.kind == "comic":
                        panels.append(desc)
                    else:
                        scenes.append(desc)
            except Exception:
                pass

        showcase_items.append({
            "id": asset.id,
            "tree_id": asset.tree_id,
            "kind": asset.kind,
            "title": title,
            "caption": asset.caption,
            "hashtags": asset.hashtags,
            "contributor_ids": asset.contributor_ids,
            "gcs_url": asset.gcs_url,
            "panels": panels if asset.kind == "comic" else None,
            "scenes": scenes if asset.kind == "reel" else None
        })

    return showcase_items


class ContributePayload(BaseModel):
    title: str
    type: str
    body: str


@app.post("/contribute")
def post_contribute(payload: ContributePayload, authorization: Optional[str] = Header(None)):
    """POST /contribute -> Execute world_engine_workflow ingest synchronously"""
    user_id = get_user_id_from_token(authorization)

    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from app.agent import root_agent
    from google.genai import types

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id=user_id, app_name="app")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="app")

    # Serialize structured user payload
    input_data = {
        "user_text": f"Type: {payload.type}. Title: {payload.title}. Body: {payload.body}",
        "author_id": user_id,
        "id_token": authorization.replace("Bearer ", "") if authorization else None
    }

    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=json.dumps(input_data))]
    )

    try:
        events = list(runner.run(
            new_message=message,
            user_id=user_id,
            session_id=session.id
        ))

        # Retrieve the final outcome from session state
        session_obj = session_service.get_session_sync(user_id=user_id, session_id=session.id)
        state = session_obj.state if session_obj else {}

        verdict = "ALLOW"
        status = "accepted"
        score = 0
        reason = ""

        # Check for direct execution errors
        for event in events:
            if event.error:
                reason = str(event.error)
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

        return {
            "status": status,
            "verdict": verdict,
            "score": score,
            "message": reason
        }

    except Exception as e:
        logger.error("Workflow execution failed: %s", e)
        err_msg = str(e)
        if "Security Block" in err_msg:
            return {
                "status": "blocked",
                "verdict": "BLOCK",
                "score": 0,
                "message": err_msg
            }
        elif "contradiction" in err_msg.lower():
            return {
                "status": "rejected",
                "verdict": "ALLOW",
                "score": 0,
                "message": err_msg
            }
        else:
            return {
                "status": "rejected",
                "verdict": "ALLOW",
                "score": 0,
                "message": f"Execution failed: {err_msg}"
            }


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback."""
    if is_cloud_logging:
        logger.log_struct(feedback.model_dump(), severity="INFO")
    else:
        logger.info("Feedback: %s", feedback.model_dump())
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

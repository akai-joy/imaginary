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
# limitations under the License.
import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging
from pydantic import BaseModel

from app.agents.showcase_tally import assemble_trees
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.core.store import get_store
from app.core.types import (
    DEFAULT_WORLD_ID,
    SEED_WORLD,
    Vote,
)

load_dotenv()

setup_telemetry()
try:
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
    is_cloud_logging = True
except Exception:
    logger = logging.getLogger(__name__)
    is_cloud_logging = False

env_origins = os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else []
allow_origins = list(set([
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
    "http://localhost:5175", "http://127.0.0.1:5175",
    "http://localhost:5176", "http://127.0.0.1:5176",
    *env_origins
]))

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

# CORS middleware is automatically managed by get_fast_api_app using the allow_origins parameter


os.makedirs("gcs_mock", exist_ok=True)
app.mount("/gcs_mock", StaticFiles(directory="gcs_mock"), name="gcs_mock")
os.makedirs("cache", exist_ok=True)
app.mount("/cache", StaticFiles(directory="cache"), name="cache")


def get_user_id_from_token(authorization: str | None, strict: bool = False) -> str:
    """Helper to extract user identity from Firebase Auth ID token, fallback to local dev user."""
    is_strict_active = (
        os.environ.get("K_SERVICE") is not None
        or os.environ.get("REQUIRE_AUTH", "").upper() == "TRUE"
    )

    if not authorization or not authorization.startswith("Bearer "):
        if strict and is_strict_active:
            raise HTTPException(status_code=401, detail="Authentication required")
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
            uid = decoded_token.get("uid") or decoded_token.get("email")
            if not uid:
                if strict and is_strict_active:
                    raise HTTPException(status_code=401, detail="Invalid token payload")
                return "playground_user"
            return uid
        except Exception as e:
            logger.warning("Firebase token verification failed, using fallback: %s", e)
            if strict and is_strict_active:
                raise HTTPException(status_code=401, detail=f"Firebase token verification failed: {e}") from e

    if strict and is_strict_active:
        raise HTTPException(status_code=401, detail="Authentication required (Firebase App ID not configured)")
    return "playground_user"


# --- REST API Endpoints for the Front-End ---

def active_world_id() -> str:
    w = get_store().get_active_world()
    return w.id if w else DEFAULT_WORLD_ID


@app.get("/world/map")
def get_world_map(authorization: str | None = Header(None)):
    store = get_store()
    user_id = get_user_id_from_token(authorization)
    active_w_id = active_world_id()

    active_w = store.get_active_world()
    if not active_w:
        active_w = store.get_world(DEFAULT_WORLD_ID) or SEED_WORLD

    world_info = {
        "id": active_w.id,
        "theme": active_w.theme,
        "opening_line": active_w.opening_line,
        "art_style_directive": active_w.art_style_directive,
        "map_image_url": active_w.map_image_url,
    }

    canon_locations = store.list_canon_entries_by_type("location", active_w_id)
    discoveries = store.list_discoveries(user_id)

    # Query map tiles and build latest map_tile URL dict
    all_assets = store.list_media_assets()
    tile_urls = {}
    for asset in all_assets:
        if asset.kind == "map_tile" and asset.world_id == active_w_id:
            existing = tile_urls.get(asset.node_id)
            if not existing or asset.created_at > existing.created_at:
                tile_urls[asset.node_id] = asset

    locations = []
    for loc in canon_locations:
        x = loc.map_meta.x if loc.map_meta else 0.0
        y = loc.map_meta.y if loc.map_meta else 0.0
        region = loc.map_meta.region if loc.map_meta else ""
        near = loc.map_meta.near if loc.map_meta else []

        discovered = (loc.id in discoveries) or (loc.contributor_id == user_id)

        tile_asset = tile_urls.get(loc.id)
        tile_url = tile_asset.gcs_url if tile_asset else None

        locations.append({
            "id": loc.id,
            "title": loc.title,
            "body": loc.body,
            "region": region,
            "x": x,
            "y": y,
            "near": near,
            "discovered": discovered,
            "contributor_id": loc.contributor_id,
            "tile_url": tile_url,
        })

    regions = sorted({loc["region"] for loc in locations if loc["region"]})

    return {
        "world": world_info,
        "locations": locations,
        "regions": regions,
    }


@app.get("/codex/{kind}")
def get_codex(kind: str, authorization: str | None = Header(None)):
    kind_to_type = {
        "characters": "character",
        "beasts": "beast",
        "spells": "spell",
    }
    if kind not in kind_to_type:
        raise HTTPException(status_code=404, detail="Invalid codex kind")

    entry_type = kind_to_type[kind]
    store = get_store()
    user_id = get_user_id_from_token(authorization)
    active_w_id = active_world_id()

    entries = store.list_canon_entries_by_type(entry_type, active_w_id)
    discoveries = store.list_discoveries(user_id)

    codex_items = []
    for entry in entries:
        discovered = (entry.id in discoveries) or (entry.contributor_id == user_id)
        codex_items.append({
            "id": entry.id,
            "title": entry.title,
            "body": entry.body,
            "contributor_id": entry.contributor_id,
            "discovered": discovered,
        })

    return codex_items


class DiscoverPayload(BaseModel):
    canon_id: str


@app.post("/discover")
def post_discover(payload: DiscoverPayload, authorization: str | None = Header(None)):
    user_id = get_user_id_from_token(authorization)
    store = get_store()
    store.save_discovery(user_id, payload.canon_id)
    return {"discovered": True, "canon_id": payload.canon_id}

@app.get("/canon/storylines")
def list_storylines(authorization: str | None = Header(None)):
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
def get_storyline(treeId: str, authorization: str | None = Header(None)):
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

    loaded_entries.sort(key=lambda x: x.created_at.replace(tzinfo=None) if x.created_at and hasattr(x.created_at, 'replace') else x.created_at)

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


def is_local_dev() -> bool:
    local_dev_env = os.getenv("WORLD_ENGINE_LOCAL_DEV")
    if local_dev_env is not None:
        return local_dev_env.upper() == "TRUE"
    return not os.getenv("GOOGLE_CLOUD_PROJECT") or not os.getenv("K_SERVICE")


def enqueue_showcase_task(tree_id: str):
    import json

    from google.cloud import tasks_v2

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
    queue = os.getenv("CLOUD_TASKS_QUEUE", "showcase-queue")

    service_url = os.getenv("SERVICE_URL") or os.getenv("PUBLIC_URL")
    if not service_url:
        logger.warning("SERVICE_URL or PUBLIC_URL env var not set. Defaulting callback URL to localhost.")
        service_url = "http://localhost:8000"

    target_url = f"{service_url.rstrip('/')}/internal/run-showcase"

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"tree_id": tree_id}).encode("utf-8"),
        }
    }

    service_account_email = os.getenv("CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
    if service_account_email:
        task["http_request"]["oidc_token"] = {
            "service_account_email": service_account_email,
            "audience": target_url,
        }

    logger.info("Enqueuing Cloud Tasks target=%s for tree_id=%s", target_url, tree_id)
    client.create_task(request={"parent": parent, "task": task})


def enqueue_atlas_task(location_id: str):
    import json

    from google.cloud import tasks_v2

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
    queue = os.getenv("CLOUD_TASKS_QUEUE", "showcase-queue")

    service_url = os.getenv("SERVICE_URL") or os.getenv("PUBLIC_URL")
    if not service_url:
        logger.warning("SERVICE_URL or PUBLIC_URL env var not set. Defaulting callback URL to localhost.")
        service_url = "http://localhost:8000"

    target_url = f"{service_url.rstrip('/')}/internal/paint-atlas"

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"location_id": location_id}).encode("utf-8"),
        }
    }

    service_account_email = os.getenv("CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
    if service_account_email:
        task["http_request"]["oidc_token"] = {
            "service_account_email": service_account_email,
            "audience": target_url,
        }

    logger.info("Enqueuing Cloud Tasks target=%s for location_id=%s", target_url, location_id)
    client.create_task(request={"parent": parent, "task": task})


def trigger_atlas_task(location_id: str):
    if is_local_dev():
        def run_atlas_async():
            try:
                from app.agents.atlas_illustrator import atlas_node
                from app.core.controller import cartography_controller_node

                store = get_store()
                entry = store.get_canon_entry(location_id)
                if not entry:
                    logger.warning("run_atlas_async: location %s not found in store.", location_id)
                    return

                class SimpleContext:
                    def __init__(self):
                        self.state = {}

                ctx = SimpleContext()
                list(atlas_node(ctx, entry))
                list(cartography_controller_node(ctx, entry))
                logger.info("Background atlas task completed for location: %s", location_id)
            except Exception as e:
                logger.error("Failed to run background atlas task: %s", e)

        threading.Thread(target=run_atlas_async, daemon=True).start()
    else:
        try:
            enqueue_atlas_task(location_id)
        except Exception as e:
            logger.error("Failed to enqueue atlas task: %s", e)



# Defined AFTER /canon/storylines and /canon/storylines/{treeId} so the parameterized
# {id} route does not shadow those more specific paths (FastAPI matches in order).
@app.get("/canon/{id}")
def get_canon_detail(id: str, authorization: str | None = Header(None)):
    store = get_store()
    user_id = get_user_id_from_token(authorization)
    entry = store.get_canon_entry(id)
    if not entry:
        raise HTTPException(status_code=404, detail="Canon entry not found")

    store.save_discovery(user_id, id)

    resolved_references = []
    if entry.references:
        for ref_id in entry.references:
            ref_entry = store.get_canon_entry(ref_id)
            if ref_entry:
                resolved_references.append({
                    "id": ref_entry.id,
                    "title": ref_entry.title,
                    "type": ref_entry.type.value if hasattr(ref_entry.type, "value") else ref_entry.type,
                })

    active_w_id = active_world_id()
    all_entries = store.list_canon_entries(active_w_id)
    referenced_by = []
    for e in all_entries:
        if e.references and id in e.references:
            referenced_by.append({
                "id": e.id,
                "title": e.title,
                "type": e.type.value if hasattr(e.type, "value") else e.type,
              })

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


@app.post("/vote")
def post_vote(payload: VotePayload, authorization: str | None = Header(None)):
    """POST /vote -> Record user vote, check threshold to run showcase pipeline async"""
    store = get_store()
    user_id = get_user_id_from_token(authorization, strict=True)
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
        created_at=datetime.now(UTC)
    )
    store.save_vote(new_vote)

    all_votes = store.get_votes_for_tree(tree_id)
    vote_total = sum(v.weight for v in all_votes)

    # 1. Fetch policy settings
    import yaml

    from app.core.config import POLICY_PATH
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
            if is_local_dev():
                # Run showcase workflow asynchronously in background thread
                def run_showcase_async():
                    try:
                        from google.adk.sessions import InMemorySessionService
                        from google.genai import types

                        from app.core.runner_factory import create_runner
                        from showcase.agent import app as showcase_app

                        session_service = InMemorySessionService()
                        session = session_service.create_session_sync(user_id="system", app_name="showcase")
                        runner = create_runner(showcase_app, session_service)

                        list(runner.run(
                            new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
                            user_id="system",
                            session_id=session.id
                        ))
                        logger.info("Background showcase workflow executed successfully (local fallback).")
                    except Exception as e:
                        logger.error("Failed to run background showcase workflow (local fallback): %s", e)

                threading.Thread(target=run_showcase_async, daemon=True).start()
            else:
                try:
                    enqueue_showcase_task(tree_id)
                except Exception as e:
                    logger.error("Failed to enqueue showcase task: %s", e)

    return {
        "ok": True,
        "tree_id": tree_id,
        "vote_total": int(vote_total),
        "voted": True
    }


class RunShowcasePayload(BaseModel):
    tree_id: str


@app.post("/internal/run-showcase")
def post_internal_run_showcase(payload: RunShowcasePayload):
    """Internal endpoint called to execute the showcase workflow for a tree."""
    store = get_store()
    existing_jobs = store.list_showcase_jobs()
    if any(job.tree_id == payload.tree_id for job in existing_jobs):
        logger.info("Showcase job already exists for tree %s, skipping.", payload.tree_id)
        return {"ok": True, "message": "Already exists"}

    try:
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        from app.core.runner_factory import create_runner
        from showcase.agent import app as showcase_app

        session_service = InMemorySessionService()
        session = session_service.create_session_sync(user_id="system", app_name="showcase")
        runner = create_runner(showcase_app, session_service)

        list(runner.run(
            new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
            user_id="system",
            session_id=session.id
        ))
        logger.info("Showcase workflow executed successfully via internal endpoint.")
        return {"ok": True}
    except Exception as e:
        logger.error("Failed to run showcase workflow in internal handler: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


def get_media_urls_for_scene(scene, media_type: str) -> tuple[str | None, str | None]:
    import hashlib
    prompt = scene.optimized_prompt if scene.optimized_prompt else scene.visual_description
    if not prompt:
        prompt = scene.visual_description

    # Compile prompt style formatting matching media_node
    if not scene.optimized_prompt:
        if media_type == "comic":
            prompt = f"{scene.visual_description}, high quality fantasy comic book style illustration, vibrant colors"
        else:
            prompt = f"{scene.visual_description}, cinematography, 9:16 vertical video"

    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    image_path = os.path.join("cache", f"{h}.png")
    video_path = os.path.join("cache", f"{h}.mp4")

    image_url = f"http://localhost:8000/cache/{h}.png" if os.path.exists(image_path) else None
    video_url = f"http://localhost:8000/cache/{h}.mp4" if os.path.exists(video_path) else None

    return image_url, video_url


@app.get("/scenes/{scene_id}")
def get_scene(scene_id: str):
    """GET /scenes/{scene_id} -> Scene model for the explorable-graph player."""
    store = get_store()
    entry = store.get_canon_entry(scene_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Scene/Canon entry not found")

    if scene_id in ("canon_alistair", "canon_10254e4f-2552-4528-aa24-5fb891f200a8", "canon_10072aa0-ccd9-4bca-875b-9399a501efc2"):
        # Custom override for the Alistair / Elynar storyline matching the custom video assets
        choices = []
        canon_entries = store.list_canon_entries()
        children = [e for e in canon_entries if scene_id in e.derived_from]
        for child in children:
            choices.append({
                "label": child.title,
                "to": child.id
            })

        if scene_id == "canon_alistair":
            panels = [
                {
                    "id": "alistair_p1",
                    "prompt": "Wounded wizard Alistair hoists himself to the great oak and sits down with crows circling.",
                    "caption": "Alistair hoists himself to the great oak and sits down with crows circling.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/silence_falls_over_the_scorche.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "alistair_p2",
                    "prompt": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "caption": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/she_is_in_a_magic_school_how.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "alistair_p3",
                    "prompt": "Alistair tells the crows to deliver a message.",
                    "caption": "He tells the crows to deliver a message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/regenerate_this_one_the_wizar.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "alistair_p4",
                    "prompt": "Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "caption": "But Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/two_changes_Elynar_is_a_girl.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "alistair_p5",
                    "prompt": "The crows fly to Elynar and deliver the message.",
                    "caption": "They fly to Elynar and deliver the message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/the_crows_deliver_the_message.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                }
            ]
        elif scene_id == "canon_10254e4f-2552-4528-aa24-5fb891f200a8": # The Ash Oak
            panels = [
                {
                    "id": "ash_oak_p1",
                    "prompt": "Wounded wizard Alistair hoists himself to the great oak and sits down with crows circling.",
                    "caption": "Alistair hoists himself to the great oak and sits down with crows circling.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/silence_falls_over_the_scorche.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "ash_oak_p2",
                    "prompt": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "caption": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/she_is_in_a_magic_school_how.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "ash_oak_p3",
                    "prompt": "Alistair tells the crows to deliver a message.",
                    "caption": "He tells the crows to deliver a message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/regenerate_this_one_the_wizar.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                }
            ]
        else: # Alistair's Protege, Elynar
            panels = [
                {
                    "id": "protege_p1",
                    "prompt": "Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "caption": "But Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/two_changes_Elynar_is_a_girl.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                },
                {
                    "id": "protege_p2",
                    "prompt": "The crows fly to Elynar and deliver the message.",
                    "caption": "The crows fly to Elynar and deliver the message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/the_crows_deliver_the_message.mp4",
                    "audioUrl": None,
                    "durationMs": 5200
                }
            ]

        return {
            "id": entry.id,
            "title": entry.title,
            "logline": entry.body[:150] + "..." if len(entry.body) > 150 else entry.body,
            "panels": panels,
            "choices": choices
        }

    from app.core.types import Storyboard

    # Reconstruct the tree containing this scene to find the ShowcaseJob and storyboard
    canon_entries = store.list_canon_entries()
    assembled = assemble_trees(canon_entries)

    # Find the tree containing this entry
    tree_root_id = None
    for root_id, member_ids in assembled:
        if scene_id in member_ids:
            tree_root_id = root_id
            break

    job = None
    storyboard = None
    if tree_root_id:
        # Check if there is an existing showcase job for this tree
        jobs = store.list_showcase_jobs()
        for j in jobs:
            if j.tree_id == tree_root_id and j.storyboard_json:
                job = j
                try:
                    storyboard = Storyboard.model_validate_json(j.storyboard_json)
                except Exception:
                    pass
                break

    # Build choices from children nodes
    choices = []
    children = [e for e in canon_entries if scene_id in e.derived_from]
    for child in children:
        choices.append({
            "label": child.title,
            "to": child.id
        })

    # Map storyboard scenes to panels using the text overlap heuristic
    panels = []
    matched_scenes = []

    if storyboard and job:
        # Build tree entries list for matching
        tree_entries = []
        member_ids_for_tree = []
        for root_id, m_ids in assembled:
            if root_id == tree_root_id:
                member_ids_for_tree = m_ids
                break

        for m_id in member_ids_for_tree:
            e = store.get_canon_entry(m_id)
            if e:
                tree_entries.append(e)

        if tree_entries:
            # Group scenes by closest canon entry
            node_scenes = {e.id: [] for e in tree_entries}
            for s in storyboard.scenes:
                best_entry_id = tree_entries[0].id
                best_score = -1
                scene_text = f"{s.visual_description} {s.caption}".lower()
                scene_words = {w for w in scene_text.split() if len(w) > 3}

                for e in tree_entries:
                    entry_text = f"{e.title} {e.body}".lower()
                    entry_words = {w for w in entry_text.split() if len(w) > 3}
                    overlap = len(scene_words.intersection(entry_words))
                    if overlap > best_score:
                        best_score = overlap
                        best_entry_id = e.id

                node_scenes[best_entry_id].append(s)

            matched_scenes = node_scenes.get(scene_id, [])

    if matched_scenes:
        for idx, s in enumerate(matched_scenes):
            image_url, video_url = get_media_urls_for_scene(s, job.media_type)
            panels.append({
                "id": f"{scene_id}_p_{idx}",
                "prompt": s.visual_description,
                "caption": s.caption,
                "imageUrl": image_url,
                "videoUrl": video_url,
                "audioUrl": None,
                "durationMs": 5200
            })
    else:
        # Fallback panel from the entry itself if no storyboard match or job is not yet run
        panels.append({
            "id": f"{scene_id}_fallback",
            "prompt": f"Illustration of {entry.title}: {entry.body}",
            "caption": entry.body,
            "imageUrl": None,
            "videoUrl": None,
            "audioUrl": None,
            "durationMs": 5200
        })

    return {
        "id": entry.id,
        "title": entry.title,
        "logline": entry.body[:150] + "..." if len(entry.body) > 150 else entry.body,
        "panels": panels,
        "choices": choices
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
        optimized_prompts = []
        job = store.get_showcase_job(asset.job_id)
        if job and job.storyboard_json:
            try:
                storyboard_data = json.loads(job.storyboard_json)
                scenes_list = storyboard_data.get("scenes", [])
                for scene in scenes_list:
                    desc = scene.get("visual_description", "")
                    prompt_opt = scene.get("optimized_prompt", desc)
                    if asset.kind == "comic":
                        panels.append(desc)
                    else:
                        scenes.append(desc)
                    optimized_prompts.append(prompt_opt)
            except Exception:
                pass

        # Translate GCS URLs for local serving and set to None for text-only mock reels
        gcs_url = asset.gcs_url
        if gcs_url and gcs_url.startswith("https://storage.googleapis.com/"):
            is_mock_reel = False
            if asset.kind == "reel":
                path_part = gcs_url.replace("https://storage.googleapis.com/", "")
                local_path = os.path.join("gcs_mock", path_part)
                if os.path.exists(local_path):
                    try:
                        with open(local_path, "rb") as f:
                            header = f.read(100)
                            if b"Mock Veo" in header or b"Video Clip" in header:
                                is_mock_reel = True
                    except Exception:
                        pass
                else:
                    is_mock_reel = True

            if is_mock_reel:
                gcs_url = None
            else:
                path_part = gcs_url.replace("https://storage.googleapis.com/", "")
                gcs_url = f"http://localhost:8000/gcs_mock/{path_part}"

        showcase_items.append({
            "id": asset.id,
            "tree_id": asset.tree_id,
            "kind": asset.kind,
            "title": title,
            "caption": asset.caption,
            "hashtags": asset.hashtags,
            "contributor_ids": asset.contributor_ids,
            "gcs_url": gcs_url,
            "panels": panels if asset.kind == "comic" else None,
            "scenes": scenes if asset.kind == "reel" else None,
            "optimized_prompts": optimized_prompts,
            "prompt_sheet_url": f"http://localhost:8000/gcs_mock/world-engine-showcase/{job.id}_prompt_sheet.txt" if job else None
        })

    return showcase_items


class ContributePayload(BaseModel):
    title: str
    type: str
    body: str
    derived_from: list[str] = []
    references: list[str] = []
    world_id: str | None = None


@app.post("/contribute")
def post_contribute(payload: ContributePayload, authorization: str | None = Header(None)):
    """POST /contribute -> Execute world_engine_workflow ingest synchronously"""
    user_id = get_user_id_from_token(authorization, strict=True)

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
        "world_id": payload.world_id,
        "derived_from": payload.derived_from,
        "references": payload.references
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
        session_obj = session_service.get_session_sync(user_id=user_id, session_id=session.id, app_name="app")
        state = session_obj.state if session_obj else {}

        verdict = "ALLOW"
        status = "accepted"
        score = 0
        reason = ""

        # Check for direct execution errors
        for event in events:
            event_err = getattr(event, "error_message", None) or getattr(event, "error_code", None)
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
                if status == "accepted" and new_entry and new_entry.get("type") == "location":
                    try:
                        trigger_atlas_task(new_entry["id"])
                    except Exception as e:
                        logger.error("Failed to trigger atlas task: %s", e)

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



class PaintAtlasPayload(BaseModel):
    location_id: str


@app.post("/internal/paint-atlas")
def post_internal_paint_atlas(payload: PaintAtlasPayload):
    store = get_store()
    entry = store.get_canon_entry(payload.location_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Location canon entry not found")

    try:
        from app.agents.atlas_illustrator import atlas_node
        from app.core.controller import cartography_controller_node

        class SimpleContext:
            def __init__(self):
                self.state = {}

        ctx = SimpleContext()
        list(atlas_node(ctx, entry))
        list(cartography_controller_node(ctx, entry))
        return {"ok": True, "location_id": payload.location_id}
    except Exception as e:
        logger.error("Failed to run paint-atlas task in internal handler: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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

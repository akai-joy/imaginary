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
import uuid
from datetime import datetime, timezone

import yaml
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types
from pydantic import BaseModel, Field

from app.agents.showcase_tally import assemble_trees
from app.core.config import POLICY_PATH
from app.core.store import get_store
from app.core.types import MediaAsset, ShowcaseJob, ShowcaseJobStatus, Storyboard

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"
GCS_MOCK_DIR = "gcs_mock"


class CaptionResponse(BaseModel):
    """Structured response from the caption generation LLM."""

    caption: str = Field(description="A short, catchy caption summarizing the story.")
    hashtags: list[str] = Field(
        default_factory=list,
        description="A list of 3-5 relevant hashtags (without the hash symbol).",
    )


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


def publish_handoff_node(ctx: Context, node_input: list[ShowcaseJob]):
    """Publish / Handoff Node.

    Creates Instagram container payloads, resolves tree contributor IDs,
    records finished MediaAssets, copies files to a simulated GCS bucket,
    and moves job statuses to published_mock.
    """
    store = get_store()
    jobs = node_input or []
    if not jobs:
        all_jobs = store.list_showcase_jobs()
        jobs = [j for j in all_jobs if j.status == ShowcaseJobStatus.GENERATED]

    processed_jobs = []
    if "publish_proposal" not in ctx.state:
        ctx.state["publish_proposal"] = {}
    client = genai.Client()

    policy = load_policy_config()
    showcase_cfg = policy.get("showcase", {})
    publish_cfg = showcase_cfg.get("publish", {})
    bucket = publish_cfg.get("gcs_bucket", "world-engine-showcase")

    # Get all canon entries to reconstruct tree members
    canon_entries = store.list_canon_entries()
    assembled_trees = dict(assemble_trees(canon_entries))

    for job in jobs:
        if job.status != ShowcaseJobStatus.GENERATED:
            processed_jobs.append(job)
            continue

        if not job.storyboard_json:
            logger.warning("No storyboard_json found for job %s. Skipping.", job.id)
            processed_jobs.append(job)
            continue

        logger.info("Publishing handoff for job %s", job.id)
        storyboard = Storyboard.model_validate_json(job.storyboard_json)

        # 1. Resolve contributor IDs in the tree
        member_ids = assembled_trees.get(job.tree_id, [])
        contributor_ids = set()
        for m_id in member_ids:
            entry = store.get_canon_entry(m_id)
            if entry and entry.contributor_id:
                contributor_ids.add(entry.contributor_id)
        resolved_contributors = list(contributor_ids)

        # 2. Call LLM to generate caption + hashtags
        model_name = get_model_for_role("storyboard")
        prompt = f"""You are the Social Media Agent for a collaborative fantasy world-building system.
Create a short, engaging Instagram caption and 3-5 relevant hashtags for the following showcase story.

Title: {storyboard.title}
Logline: {storyboard.logline}

Generate a structured JSON response matching the CaptionResponse schema."""

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CaptionResponse,
                temperature=0.7,
            ),
        )

        caption_data = CaptionResponse.model_validate_json(response.text)

        # Append "AI-generated" disclaimer and hashtags
        final_caption = f"{caption_data.caption}\n\n🤖 AI-generated content."
        hashtag_line = " ".join([f"#{tag}" for tag in caption_data.hashtags])
        caption_with_hashtags = f"{final_caption}\n\n{hashtag_line}"

        # 3. Propose uploading to GCS bucket
        ext = "png" if job.media_type == "comic" else "mp4"
        src_filename = f"{job.id}_{job.media_type}.{ext}"
        src_path = os.path.join(CACHE_DIR, src_filename)

        dest_filename = f"{job.id}_final.{ext}"
        dest_bucket_dir = os.path.join(GCS_MOCK_DIR, bucket)
        dest_path = os.path.join(dest_bucket_dir, dest_filename)

        gcs_url = f"https://storage.googleapis.com/{bucket}/{dest_filename}"

        # 4. Construct MediaAsset proposal
        asset = MediaAsset(
            id=f"asset_{uuid.uuid4()}",
            job_id=job.id,
            tree_id=job.tree_id,
            kind=job.media_type,
            gcs_url=gcs_url,
            caption=caption_with_hashtags,
            hashtags=caption_data.hashtags,
            contributor_ids=resolved_contributors,
            created_at=datetime.now(timezone.utc),
        )

        # 5. Build Instagram container payload
        if job.media_type == "comic":
            instagram_payload = {"image_url": gcs_url, "caption": caption_with_hashtags}
        else:
            instagram_payload = {
                "media_type": "REELS",
                "video_url": gcs_url,
                "caption": caption_with_hashtags,
            }

        # 6. Stop at the Review Gate (log the payload)
        logger.info(
            "REVIEW GATE - Instagram Container Payload for job %s:\n%s",
            job.id,
            yaml.dump(instagram_payload, default_flow_style=False),
        )

        # Update job status in memory and queue proposal for deterministic controller
        job.status = ShowcaseJobStatus.PUBLISHED_MOCK
        ctx.state["publish_proposal"][job.id] = {
            "status": ShowcaseJobStatus.PUBLISHED_MOCK.value,
            "src_path": src_path,
            "dest_path": dest_path,
            "bucket": bucket,
            "media_asset": {
                "id": asset.id,
                "job_id": asset.job_id,
                "tree_id": asset.tree_id,
                "kind": asset.kind,
                "gcs_url": asset.gcs_url,
                "caption": asset.caption,
                "hashtags": asset.hashtags,
                "contributor_ids": asset.contributor_ids,
                "created_at": asset.created_at.isoformat(),
            }
        }
        processed_jobs.append(job)

        yield Event(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"### Review Gate — Mock Publishing Complete\n"
                        f"- **Job ID**: `{job.id}`\n"
                        f"- **Media Kind**: `{job.media_type.upper()}`\n"
                        f"- **GCS Public URL**: [{dest_filename}]({gcs_url})\n"
                        f"- **Resolved Contributors**: {', '.join(resolved_contributors)}\n"
                        f"\n**Generated Caption**:\n{caption_with_hashtags}\n"
                        f"\n**Instagram Publishing Payload (review gate)**:\n"
                        f"```json\n"
                        f"{yaml.dump(instagram_payload, default_flow_style=False)}"
                        f"```"
                    )
                ],
            )
        )

    yield Event(output=processed_jobs)

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

import yaml
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import POLICY_PATH
from app.core.store import get_store
from app.core.types import ShowcaseJob, ShowcaseJobStatus, Storyboard

logger = logging.getLogger(__name__)


class DirectorScenePrompt(BaseModel):
    scene_number: int = Field(description="The matching scene/panel number.")
    optimized_prompt: str = Field(
        description="Cinematic prompt optimized for image or video generation."
    )


class DirectorResponse(BaseModel):
    scenes: list[DirectorScenePrompt] = Field(
        description="List of optimized prompts for the storyboard scenes."
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


def director_node(ctx: Context, node_input: list[ShowcaseJob]):
    """Director Node.

    Takes storyboarded showcase jobs, calls the LLM to generate optimized cinematic prompts
    for each scene, and updates their status to DIRECTED.
    """
    store = get_store()
    jobs = node_input or []
    if not jobs:
        # Fallback to fetch all storyboarded jobs in the database
        all_jobs = store.list_showcase_jobs()
        jobs = [j for j in all_jobs if j.status == ShowcaseJobStatus.STORYBOARDED]

    processed_jobs = []
    if "director_proposal" not in ctx.state:
        ctx.state["director_proposal"] = {}

    client = genai.Client()
    model_name = get_model_for_role("storyboard")

    for job in jobs:
        if job.status != ShowcaseJobStatus.STORYBOARDED:
            processed_jobs.append(job)
            continue

        if not job.storyboard_json:
            logger.warning("No storyboard found for job %s. Skipping.", job.id)
            processed_jobs.append(job)
            continue

        logger.info("Directing job %s, generating cinematic prompts...", job.id)
        storyboard = Storyboard.model_validate_json(job.storyboard_json)

        # Build prompt for LLM
        prompt_lines = [
            "You are the Cinematic Director Agent for a collaborative storytelling system.",
            "Your task is to take the raw visual descriptions of scenes in the storyboard and rewrite each of them into an optimized cinematic prompt for image generation (Imagen) or video generation (Veo/Luma/Runway).",
            f"Media Type: {job.media_type.upper()} (For comic panels, optimize for static images; for reels, optimize for fluid video motions and camera pans).",
            f"Story Title: {storyboard.title}",
            f"Story Logline: {storyboard.logline}",
            "\nFor each scene below, write an optimized prompt focusing on camera moves, lighting, shot size, and visual composition. Keep descriptions clear and direct. Ensure visual elements (like characters and lighting style) are consistent across the scenes.",
            "\nScenes to optimize:",
        ]
        for scene in storyboard.scenes:
            prompt_lines.append(
                f"- Scene {scene.scene_number}: {scene.visual_description}"
            )

        prompt = "\n".join(prompt_lines)

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DirectorResponse,
                    temperature=0.2,
                ),
            )
            director_data = DirectorResponse.model_validate_json(response.text)
            prompt_map = {
                item.scene_number: item.optimized_prompt
                for item in director_data.scenes
            }

            # Merge optimized prompts back into storyboard
            for scene in storyboard.scenes:
                scene.optimized_prompt = prompt_map.get(
                    scene.scene_number, scene.visual_description
                )

            # Write prompt sheet file to cache for user convenience
            os.makedirs("cache", exist_ok=True)
            prompt_sheet_filename = f"{job.id}_prompt_sheet.txt"
            prompt_sheet_path = os.path.join("cache", prompt_sheet_filename)
            with open(prompt_sheet_path, "w") as f:
                f.write(
                    f"--- Prompt Sheet for Job {job.id} ({job.media_type.upper()}) ---\n"
                )
                f.write(f"Title: {storyboard.title}\n")
                f.write(f"Logline: {storyboard.logline}\n\n")
                for scene in storyboard.scenes:
                    f.write(
                        f"Scene {scene.scene_number} Prompt:\n{scene.optimized_prompt}\n\n"
                    )

            logger.info("Saved prompt sheet to cache: %s", prompt_sheet_path)

            job.storyboard_json = storyboard.model_dump_json()
            job.status = ShowcaseJobStatus.DIRECTED

            # Propose the directed status update
            ctx.state["director_proposal"][job.id] = {
                "status": ShowcaseJobStatus.DIRECTED.value,
                "storyboard_json": job.storyboard_json,
                "prompt_sheet_path": prompt_sheet_path,
                "prompt_sheet_filename": prompt_sheet_filename,
            }

            yield Event(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=f"### Directed Storyboard (Job `{job.id}`):\n"
                            f"Generated optimized prompts for {len(storyboard.scenes)} scenes. Prompt sheet saved locally."
                        )
                    ],
                )
            )

        except Exception as e:
            logger.error("Failed to direct storyboard for job %s: %s", job.id, e)
            # Fallback to copy visual description directly to optimized prompt
            for scene in storyboard.scenes:
                scene.optimized_prompt = scene.visual_description
            job.storyboard_json = storyboard.model_dump_json()
            job.status = ShowcaseJobStatus.DIRECTED
            ctx.state["director_proposal"][job.id] = {
                "status": ShowcaseJobStatus.DIRECTED.value,
                "storyboard_json": job.storyboard_json,
            }

        processed_jobs.append(job)

    yield Event(output=processed_jobs)

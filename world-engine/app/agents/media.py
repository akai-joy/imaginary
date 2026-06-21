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

import hashlib
import io
import logging
import os
from typing import Any

import yaml
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types
from PIL import Image, ImageDraw

from app.core.config import POLICY_PATH
from app.core.store import get_store
from app.core.types import ShowcaseJob, ShowcaseJobStatus, Storyboard

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"


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


def is_vertex_enabled() -> bool:
    """Checks if Vertex AI is enabled based on environment variables."""
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "True"


def get_cached_asset_path(prompt: str, ext: str) -> str | None:
    """Check if the asset with this prompt has been generated and cached."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    path = os.path.join(CACHE_DIR, f"{h}.{ext}")
    if os.path.exists(path):
        return path
    return None


def cache_asset_data(prompt: str, data: bytes, ext: str) -> str:
    """Cache the raw asset bytes."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    path = os.path.join(CACHE_DIR, f"{h}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def create_mock_panel_image(scene_num: int, description: str) -> bytes:
    """Draws a placeholder colored image representing a comic panel."""
    # Create soft color gradient based on scene number
    color = ((scene_num * 40) % 256, (scene_num * 80) % 256, (scene_num * 120) % 256)
    img = Image.new("RGB", (512, 512), color)
    draw = ImageDraw.Draw(img)

    draw.text((20, 20), f"Panel {scene_num}", fill=(255, 255, 255))

    # Wrap text to fit panel width
    words = description.split()
    lines = []
    current_line = []
    for word in words:
        if len(" ".join([*current_line, word])) * 7 > 470:
            lines.append(" ".join(current_line))
            current_line = [word]
        else:
            current_line.append(word)
    if current_line:
        lines.append(" ".join(current_line))

    y = 60
    for line in lines:
        draw.text((20, y), line, fill=(240, 240, 240))
        y += 20

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_imagen_panel(client: genai.Client, prompt: str, scene_num: int) -> bytes:
    """Generates an image via Vertex AI Imagen, Gemini Nano Banana, or falls back to mock generation."""
    try:
        # Check cache first
        cached = get_cached_asset_path(prompt, "png")
        if cached:
            logger.info("Imagen/Nano Banana cache hit for scene %d", scene_num)
            with open(cached, "rb") as f:
                return f.read()

        if is_vertex_enabled():
            logger.info("Calling Imagen (Vertex AI) for scene %d...", scene_num)
            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                ),
            )
            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                cache_asset_data(prompt, img_bytes, "png")
                return img_bytes
        else:
            logger.info("Calling Gemini Nano Banana (Developer API) for scene %d...", scene_num)
            response = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"]
                )
            )
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        img_bytes = part.inline_data.data
                        cache_asset_data(prompt, img_bytes, "png")
                        return img_bytes
    except Exception as e:
        logger.warning("Imagen/Nano Banana generation failed: %s. Generating local mock panel.", e)

    # Fallback to local cacheable mock image
    mock_bytes = create_mock_panel_image(scene_num, prompt)
    cache_asset_data(prompt, mock_bytes, "png")
    return mock_bytes


def generate_veo_clip(
    client: genai.Client, prompt: str, scene_num: int, model_tier: str
) -> bytes:
    """Generates a video clip via Vertex AI Veo or falls back to mock clip."""
    try:
        cached = get_cached_asset_path(prompt, "mp4")
        if cached:
            logger.info("Veo cache hit for scene %d", scene_num)
            with open(cached, "rb") as f:
                return f.read()

        if is_vertex_enabled():
            model_name = "veo-2.0-generate-001"
            logger.info("Calling Vertex Veo (%s) for scene %d...", model_tier, scene_num)
        else:
            model_name = "veo-3.1-generate-preview"
            logger.info("Calling AI Studio Veo (%s) for scene %d...", model_tier, scene_num)

        operation = client.models.generate_videos(
            model=model_name,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                duration_seconds=8,
            ),
        )

        # Poll the operation until completion
        import time
        max_attempts = 12  # Poll for up to 2 minutes
        for i in range(max_attempts):
            if operation.done:
                break
            logger.info("Waiting for Veo video clip %d generation (attempt %d/%d)...", scene_num, i+1, max_attempts)
            time.sleep(10)
            operation = client.operations.get(operation)

        if not operation.done:
            raise TimeoutError("Veo video generation timed out.")

        if operation.response and operation.response.generated_videos:
            gen_video = operation.response.generated_videos[0]
            clip_bytes = client.files.download(file=gen_video.video)
            cache_asset_data(prompt, clip_bytes, "mp4")
            return clip_bytes
    except Exception as e:
        logger.warning("Veo generation failed: %s. Generating mock clip.", e)

    # Local mock clip
    mock_data = f"Mock Veo Video Clip (9:16, 8s, Tier: {model_tier})\nScene {scene_num}\nVisual: {prompt}".encode()
    cache_asset_data(prompt, mock_data, "mp4")
    return mock_data


def compose_comic_page(panel_bytes_list: list[bytes]) -> bytes:
    """Composes individual panel image bytes into a single grid-aligned comic page PNG."""
    panels = [Image.open(io.BytesIO(b)) for b in panel_bytes_list]
    num_panels = len(panels)
    if num_panels == 0:
        return b""

    # Determine grid layout: 2 columns, N rows
    cols = 2
    rows = (num_panels + 1) // 2

    panel_w, panel_h = panels[0].size
    grid_w = cols * panel_w
    grid_h = rows * panel_h

    # Create composite image with white gutters
    composite = Image.new("RGB", (grid_w, grid_h), (255, 255, 255))
    for idx, panel in enumerate(panels):
        r = idx // cols
        c = idx % cols
        composite.paste(panel, (c * panel_w, r * panel_h))

    buf = io.BytesIO()
    composite.save(buf, format="PNG")
    return buf.getvalue()


def media_node(ctx: Context, node_input: list[ShowcaseJob]):
    """Media Node.

    Processes storyboarded showcase jobs, calling Imagen (for comic panels) or Veo (for reels)
    with configured settings and caching, then composing/saving the final asset file.
    """
    store = get_store()
    jobs = node_input or []
    if not jobs:
        all_jobs = store.list_showcase_jobs()
        jobs = [j for j in all_jobs if j.status == ShowcaseJobStatus.DIRECTED]

    processed_jobs = []
    if "media_proposal" not in ctx.state:
        ctx.state["media_proposal"] = {}
    client = genai.Client()

    policy = load_policy_config()
    media_cfg = policy.get("showcase", {}).get("media", {})
    reel_cfg = media_cfg.get("reel", {})
    model_tier = reel_cfg.get("model_tier", "lite")

    for job in jobs:
        if job.status != ShowcaseJobStatus.DIRECTED:
            processed_jobs.append(job)
            continue

        if not job.storyboard_json:
            logger.warning("No storyboard_json found for job %s. Skipping.", job.id)
            processed_jobs.append(job)
            continue

        logger.info(
            "Generating media assets for job %s (type=%s)", job.id, job.media_type
        )
        storyboard = Storyboard.model_validate_json(job.storyboard_json)

        os.makedirs(CACHE_DIR, exist_ok=True)
        final_path = ""

        if job.media_type == "comic":
            panel_images = []
            for scene in storyboard.scenes:
                # Use optimized prompt if available, otherwise compile fallback prompt
                if getattr(scene, "optimized_prompt", None):
                    prompt = scene.optimized_prompt
                else:
                    prompt = f"{scene.visual_description}, high quality fantasy comic book style illustration, vibrant colors"
                panel_bytes = generate_imagen_panel(client, prompt, scene.scene_number)
                panel_images.append(panel_bytes)

            # Compose composed page
            comic_page_bytes = compose_comic_page(panel_images)
            final_path = os.path.join(CACHE_DIR, f"{job.id}_comic.png")
            with open(final_path, "wb") as f:
                f.write(comic_page_bytes)

            logger.info("Composed comic page saved at %s", final_path)
            yield Event(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=f"Generated and composed comic page with {len(storyboard.scenes)} panels for job `{job.id}`."
                        )
                    ],
                )
            )

        elif job.media_type == "reel":
            clips = []
            for scene in storyboard.scenes:
                if getattr(scene, "optimized_prompt", None):
                    prompt = scene.optimized_prompt
                else:
                    prompt = (
                        f"{scene.visual_description}, cinematography, 9:16 vertical video"
                    )
                clip_bytes = generate_veo_clip(
                    client, prompt, scene.scene_number, model_tier
                )
                clips.append(clip_bytes)

            # Chained into one final video file
            final_path = os.path.join(CACHE_DIR, f"{job.id}_reel.mp4")
            with open(final_path, "wb") as f:
                for idx, clip in enumerate(clips):
                    f.write(f"--- Video Clip {idx + 1} ---\n".encode())
                    f.write(clip)
                    f.write(b"\n")

            logger.info("Chained reel video saved at %s", final_path)
            yield Event(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=f"Generated and chained {len(storyboard.scenes)} video clips into reel for job `{job.id}` (Tier: {model_tier})."
                        )
                    ],
                )
            )

        # Propose job status update
        job.status = ShowcaseJobStatus.GENERATED
        ctx.state["media_proposal"][job.id] = {
            "status": ShowcaseJobStatus.GENERATED.value,
        }
        processed_jobs.append(job)

    yield Event(output=processed_jobs)

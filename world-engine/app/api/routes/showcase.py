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
"""Showcase feed route: generated media assets with storyboard fallbacks."""

import json
import logging
import os

from fastapi import APIRouter

from app.api import deps

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/showcase")
def get_showcase():
    """GET /showcase -> MediaAsset[] items with fallback storyboard panels/scenes"""
    store = deps.get_store()
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

        showcase_items.append(
            {
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
                "prompt_sheet_url": f"http://localhost:8000/gcs_mock/world-engine-showcase/{job.id}_prompt_sheet.txt"
                if job
                else None,
            }
        )

    return showcase_items

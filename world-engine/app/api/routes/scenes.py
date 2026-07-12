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
"""Scene-player routes: panel resolution for the explorable graph, incl. demo overrides."""

import logging
import os

from fastapi import APIRouter, HTTPException

from app.agents.showcase_tally import assemble_trees
from app.api import deps

logger = logging.getLogger(__name__)

router = APIRouter()


def get_media_urls_for_scene(scene, media_type: str) -> tuple[str | None, str | None]:
    """Resolve cached comic/reel asset URLs for a storyboard scene by hashing its generation prompt (None until generated)."""
    import hashlib

    prompt = (
        scene.optimized_prompt if scene.optimized_prompt else scene.visual_description
    )
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

    image_url = (
        f"http://localhost:8000/cache/{h}.png" if os.path.exists(image_path) else None
    )
    video_url = (
        f"http://localhost:8000/cache/{h}.mp4" if os.path.exists(video_path) else None
    )

    return image_url, video_url


def attach_panel_audio(panels: list[dict]) -> list[dict]:
    """Resolves active world's persona voice, then adds cached audio URLs to panels."""
    if not panels:
        return panels
    try:
        from app.agents.chronicler import (
            _chronicle_config,
            get_cached_speech_url,
            select_persona,
        )

        active_w = deps.resolve_active_world()
        config = _chronicle_config()
        _, persona = select_persona(active_w.theme, config)
        voice_name = persona.get("voice_name") or config.get(
            "default_voice_name", "Sulafat"
        )

        for panel in panels:
            caption = panel.get("caption")
            if caption:
                panel["audioUrl"] = get_cached_speech_url(caption, voice_name)
    except Exception as e:
        logger.error("Failed to attach panel audio: %s", e)
    return panels


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: str):
    """GET /scenes/{scene_id} -> Scene model for the explorable-graph player."""
    store = deps.get_store()
    entry = store.get_canon_entry(scene_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Scene/Canon entry not found")

    if scene_id in (
        "canon_alistair",
        "canon_10254e4f-2552-4528-aa24-5fb891f200a8",
        "canon_10072aa0-ccd9-4bca-875b-9399a501efc2",
        "canon_86cfa3fe-c56d-4fda-a066-469d40eb7cf0",
        "canon_eldoria",
        "eldoria",
        "canon_drk",
        "canon_pia",
    ):
        # Custom override for the Alistair / Elynar storyline matching the custom video assets
        choices = []
        canon_entries = store.list_canon_entries()
        children = [e for e in canon_entries if scene_id in e.derived_from]
        for child in children:
            choices.append({"label": child.title, "to": child.id})

        if scene_id == "canon_alistair":
            panels = [
                {
                    "id": "alistair_p1",
                    "prompt": "Wounded wizard Alistair hoists himself to the great oak and sits down with crows circling.",
                    "caption": "Alistair hoists himself to the great oak and sits down with crows circling.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/silence_falls_over_the_scorche.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "alistair_p2",
                    "prompt": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "caption": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/she_is_in_a_magic_school_how.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "alistair_p3",
                    "prompt": "Alistair tells the crows to deliver a message.",
                    "caption": "He tells the crows to deliver a message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/regenerate_this_one_the_wizar.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "alistair_p4",
                    "prompt": "Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "caption": "But Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/two_changes_Elynar_is_a_girl.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "alistair_p5",
                    "prompt": "The crows fly to Elynar and deliver the message.",
                    "caption": "They fly to Elynar and deliver the message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/the_crows_deliver_the_message.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
            ]
        elif scene_id == "canon_10254e4f-2552-4528-aa24-5fb891f200a8":  # The Ash Oak
            panels = [
                {
                    "id": "ash_oak_p1",
                    "prompt": "Wounded wizard Alistair hoists himself to the great oak and sits down with crows circling.",
                    "caption": "Alistair hoists himself to the great oak and sits down with crows circling.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/silence_falls_over_the_scorche.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "ash_oak_p2",
                    "prompt": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "caption": "He tells the crows Elynar can't be in danger, she is in a magic school.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/she_is_in_a_magic_school_how.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "ash_oak_p3",
                    "prompt": "Alistair tells the crows to deliver a message.",
                    "caption": "He tells the crows to deliver a message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/regenerate_this_one_the_wizar.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
            ]
        elif scene_id in (
            "canon_eldoria",
            "eldoria",
        ):  # Sliced 6-panel Eldoria Storyline
            panels = [
                {
                    "id": "p1",
                    "imageUrl": "/eldoria_p1.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "At the edge of the white pass, the traveler saw it at last — Eldoria, glowing gold against the dark.",
                    "prompt": "Wide shot. A weary traveler on a snow-covered mountain path; the golden lights of Eldoria nestle among snowy peaks. Dusk, deep blues and purples.",
                    "durationMs": 5200,
                },
                {
                    "id": "p2",
                    "imageUrl": "/eldoria_p2.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "The village lay cupped in the valley, steam rising from the springs like breath on the cold air.",
                    "prompt": "High-angle establishing shot. Eldoria in a snowy valley, rustic cabins, warm windows, thick steam from mineral hot springs. Starry sky.",
                    "durationMs": 5200,
                },
                {
                    "id": "p3",
                    "imageUrl": "/eldoria_p3.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "She sank into the hot spring, and the journey's ache lifted into the steam and the stars.",
                    "prompt": "Medium shot. The traveler soaks in a stone hot spring, eyes closed; ethereal steam drifts upward, catching soft light. Brilliant starry sky.",
                    "durationMs": 5200,
                },
                {
                    "id": "p4",
                    "imageUrl": "/eldoria_p4.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "The tavern door gave way to warmth — light, voices, the smell of something good.",
                    "prompt": "Low-angle dynamic shot. The traveler pushes open a heavy wooden door into a bustling warm tavern; golden light pours out.",
                    "durationMs": 5200,
                },
                {
                    "id": "p5",
                    "imageUrl": "/eldoria_p5.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "By the hearth she cradled the mug, and for the first time in weeks, she smiled.",
                    "prompt": "Medium close-up. The traveler in a plush armchair by a roaring stone hearth, holding a steaming mug, gentle smile, warm firelight.",
                    "durationMs": 5200,
                },
                {
                    "id": "p6",
                    "imageUrl": "/eldoria_p6.png",
                    "videoUrl": None,
                    "audioUrl": None,
                    "caption": "Snow fell soft over the sleeping village, and Eldoria kept its quiet, glowing watch.",
                    "prompt": "POV from inside a cabin looking out a wooden window; soft snow over the sleeping village at night, glowing windows, cool blue tones.",
                    "durationMs": 5200,
                },
            ]
        elif (
            scene_id == "canon_86cfa3fe-c56d-4fda-a066-469d40eb7cf0"
        ):  # The School of Magic
            panels = [
                {
                    "id": "magic_school_p1",
                    "prompt": "In the eastern city of Pavlovia, the School of Magic rises in tiered halls of pale stone.",
                    "caption": "In the eastern city of Pavlovia, the School of Magic rises in tiered halls of pale stone, where apprentices are sent to study far from the wars.",
                    "imageUrl": "http://localhost:8000/cache/schoolofmagic.jpg",
                    "videoUrl": None,
                    "audioUrl": None,
                    "durationMs": 5200,
                }
            ]
        elif scene_id == "canon_drk":  # The Slagmaw Drake
            panels = [
                {
                    "id": "drk_p1",
                    "prompt": "Close-up of the Slagmaw Drake nesting in cooling iron, eyes glowing, breath crackling.",
                    "caption": "The Slagmaw Drake nests in cooling iron, its breath crackling as it swallows oaths whole.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/gcs_mock/world-engine-showcase/the_slagmaw_drake.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                }
            ]
        elif scene_id == "canon_pia":  # Pia, the Chronicler of Lantern Row
            panels = [
                {
                    "id": "pia_p1",
                    "prompt": "Pia the chronicler writing in her book under the warm streetlamps of Lantern Row.",
                    "caption": "Pia sits under the amber streetlamps of Lantern Row, capturing the histories of the world.",
                    "imageUrl": "http://localhost:8000/cache/pia_the_chronicler.jpg",
                    "videoUrl": None,
                    "audioUrl": None,
                    "durationMs": 5200,
                }
            ]
        else:  # Alistair's Protege, Elynar
            panels = [
                {
                    "id": "protege_p1",
                    "prompt": "Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "caption": "But Elynar decides to leave immediately, using her power to teleport through doors to run towards the stables.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/two_changes_Elynar_is_a_girl.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
                {
                    "id": "protege_p2",
                    "prompt": "The crows fly to Elynar and deliver the message.",
                    "caption": "The crows fly to Elynar and deliver the message.",
                    "imageUrl": None,
                    "videoUrl": "http://localhost:8000/cache/the_crows_deliver_the_message.mp4",
                    "audioUrl": None,
                    "durationMs": 5200,
                },
            ]

        return {
            "id": entry.id,
            "title": entry.title,
            "logline": entry.body[:150] + "..."
            if len(entry.body) > 150
            else entry.body,
            "panels": attach_panel_audio(panels),
            "choices": choices,
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
        choices.append({"label": child.title, "to": child.id})

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
            if tree_root_id == "canon_eldoria":
                image_url = f"/eldoria_p{s.scene_number}.png"
                video_url = None
            else:
                image_url, video_url = get_media_urls_for_scene(s, job.media_type)
            panels.append(
                {
                    "id": f"{scene_id}_p_{idx}",
                    "prompt": s.visual_description,
                    "caption": s.caption,
                    "imageUrl": image_url,
                    "videoUrl": video_url,
                    "audioUrl": None,
                    "durationMs": 5200,
                }
            )
    else:
        # Fallback panel from the entry itself if no storyboard match or job is not yet run
        image_url = None
        entry_type = entry.type.value if hasattr(entry.type, "value") else entry.type
        if entry_type == "location":
            assets = store.list_media_assets()
            tile_assets = [
                a for a in assets if a.kind == "map_tile" and a.node_id == entry.id
            ]
            if tile_assets:
                latest_tile = max(tile_assets, key=lambda a: a.created_at)
                image_url = latest_tile.gcs_url

        panels.append(
            {
                "id": f"{scene_id}_fallback",
                "prompt": f"Illustration of {entry.title}: {entry.body}",
                "caption": entry.body,
                "imageUrl": image_url,
                "videoUrl": None,
                "audioUrl": None,
                "durationMs": 5200,
            }
        )

    return {
        "id": entry.id,
        "title": entry.title,
        "logline": entry.body[:150] + "..." if len(entry.body) > 150 else entry.body,
        "panels": attach_panel_audio(panels),
        "choices": choices,
    }

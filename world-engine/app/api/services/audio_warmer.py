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
"""Background TTS pre-warmer for scene panel captions."""

import logging
from collections.abc import Callable

from app.api.services.background import submit_once
from app.core.store import get_store
from app.core.types import DEFAULT_WORLD_ID, SEED_WORLD

logger = logging.getLogger(__name__)

# The scene builder lives in the route layer (it shapes the REST response the
# player consumes); the warmer only needs its output, so the app registers the
# builder here instead of the service importing upward from the routes.
_scene_provider: Callable[[str], dict] | None = None


def set_scene_provider(fn: Callable[[str], dict]) -> None:
    global _scene_provider
    _scene_provider = fn


def warm_scene_audio() -> None:
    """Pre-generates TTS for all panel captions across all canon scenes."""
    try:
        from app.agents.chronicler import (
            _chronicle_config,
            get_cached_speech_url,
            select_persona,
            synthesize_speech,
        )

        if _scene_provider is None:
            logger.warning("Scene audio warming skipped: no scene provider registered.")
            return

        config = _chronicle_config()
        tts_cfg = config.get("tts", {}) or {}
        if not tts_cfg.get("enabled", True):
            logger.info("Scene audio warming skipped: tts.enabled is False.")
            return

        logger.info("Starting background scene audio warmer...")
        store = get_store()

        from app.core.lifecycle import tick

        active_w = tick(store)
        if not active_w:
            worlds = store.list_worlds()
            active_w = (
                worlds[0]
                if worlds
                else (store.get_world(DEFAULT_WORLD_ID) or SEED_WORLD)
            )
        _, persona = select_persona(active_w.theme, config)
        voice_name = persona.get("voice_name") or config.get(
            "default_voice_name", "Sulafat"
        )
        persona_style = persona.get("voice", "")

        entries = store.list_canon_entries()

        warmed_count = 0
        cached_count = 0
        failed_count = 0

        for entry in entries:
            try:
                scene_data = _scene_provider(entry.id)
                panels = scene_data.get("panels", [])
                for p in panels:
                    caption = p.get("caption")
                    if not caption:
                        continue
                    cached_url = get_cached_speech_url(caption, voice_name)
                    if cached_url:
                        cached_count += 1
                    else:
                        res = synthesize_speech(
                            caption, voice_name, style=persona_style
                        )
                        if res:
                            warmed_count += 1
                        else:
                            failed_count += 1
            except Exception as ex:
                logger.error("Warmer failed to process scene %s: %s", entry.id, ex)

        logger.info(
            "Scene audio warming complete: %d warmed, %d already cached, %d failed",
            warmed_count,
            cached_count,
            failed_count,
        )
    except Exception as e:
        logger.error("Scene audio warmer failed completely: %s", e)


def schedule_scene_audio_warmup() -> None:
    """Kick the warmer onto the shared background pool (deduped)."""
    submit_once("scene-audio-warmer", warm_scene_audio)

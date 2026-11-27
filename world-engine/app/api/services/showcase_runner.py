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
"""Showcase workflow execution: inline runner + Cloud Tasks enqueue + local trigger."""

import logging

from google.genai import types

from app.api import deps
from app.api.services.audio_warmer import warm_scene_audio
from app.api.services.background import enqueue_cloud_task, is_local_dev, submit_once
from app.core.runner_factory import create_runner
from showcase.agent import app as showcase_app

logger = logging.getLogger(__name__)


def run_showcase() -> None:
    """Execute the showcase workflow once via the plugin-carrying Runner (raises on failure)."""
    session_service = deps.get_session_service()
    session = session_service.create_session_sync(user_id="system", app_name="showcase")
    runner = create_runner(showcase_app, session_service)

    try:
        list(
            runner.run(
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text="run")]
                ),
                user_id="system",
                session_id=session.id,
            )
        )
    finally:
        try:
            session_service.delete_session_sync(
                app_name="showcase", user_id="system", session_id=session.id
            )
        except Exception:
            pass


def enqueue_showcase_task(tree_id: str) -> None:
    """Enqueue the showcase workflow for a tree on Cloud Tasks (the production async path)."""
    enqueue_cloud_task(
        "/internal/run-showcase",
        {"tree_id": tree_id},
        log_label=f"tree_id={tree_id}",
    )


def _run_showcase_local() -> None:
    run_showcase()
    logger.info("Background showcase workflow executed successfully (local fallback).")
    warm_scene_audio()


def trigger_showcase_task(tree_id: str) -> None:
    """Fire the showcase workflow for a tree: deduped background run in local dev, Cloud Tasks in the cloud."""
    if is_local_dev():
        submit_once(f"showcase:{tree_id}", _run_showcase_local)
    else:
        try:
            enqueue_showcase_task(tree_id)
        except Exception as e:
            logger.error("Failed to enqueue showcase task: %s", e)

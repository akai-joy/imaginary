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

import json
import logging
import os

from app.api.services.background import is_local_dev, submit_once

logger = logging.getLogger(__name__)


def run_showcase() -> None:
    """Execute the showcase workflow once via the plugin-carrying Runner (raises on failure)."""
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.core.runner_factory import create_runner
    from showcase.agent import app as showcase_app

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="system", app_name="showcase")
    runner = create_runner(showcase_app, session_service)

    list(
        runner.run(
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text="run")]
            ),
            user_id="system",
            session_id=session.id,
        )
    )


def enqueue_showcase_task(tree_id: str) -> None:
    """Enqueue the showcase workflow for a tree on Cloud Tasks (the production async path)."""
    from google.cloud import tasks_v2

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
    queue = os.getenv("CLOUD_TASKS_QUEUE", "showcase-queue")

    service_url = os.getenv("SERVICE_URL") or os.getenv("PUBLIC_URL")
    if not service_url:
        logger.warning(
            "SERVICE_URL or PUBLIC_URL env var not set. Defaulting callback URL to localhost."
        )
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


def _run_showcase_local() -> None:
    from app.api.services.audio_warmer import warm_scene_audio

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

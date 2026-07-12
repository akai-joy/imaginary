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
"""Atlas illustration execution: inline runner + Cloud Tasks enqueue + local trigger."""

import json
import logging
import os

from app.api.services.background import is_local_dev, submit_once
from app.core.store import get_store

logger = logging.getLogger(__name__)


class _SimpleContext:
    """Minimal ctx stand-in carrying only the state dict the atlas nodes use."""

    def __init__(self) -> None:
        self.state: dict = {}


def run_atlas(location_id: str) -> bool:
    """Run the atlas illustrator + cartography controller for a location.

    Returns False (with a warning) if the location no longer exists; raises on
    execution failure so callers can surface it.
    """
    from app.agents.atlas_illustrator import atlas_node
    from app.core.controller import cartography_controller_node

    store = get_store()
    entry = store.get_canon_entry(location_id)
    if not entry:
        logger.warning("run_atlas: location %s not found in store.", location_id)
        return False

    ctx = _SimpleContext()
    list(atlas_node(ctx, entry))
    list(cartography_controller_node(ctx, entry))
    logger.info("Background atlas task completed for location: %s", location_id)
    return True


def enqueue_atlas_task(location_id: str) -> None:
    """Enqueue the async Atlas-illustration workflow for a location on Cloud Tasks (the production async path)."""
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

    logger.info(
        "Enqueuing Cloud Tasks target=%s for location_id=%s", target_url, location_id
    )
    client.create_task(request={"parent": parent, "task": task})


def trigger_atlas_task(location_id: str) -> None:
    """Fire the Atlas illustration for a location: deduped background run in local dev, Cloud Tasks in the cloud."""
    if is_local_dev():
        submit_once(f"atlas:{location_id}", run_atlas, location_id)
    else:
        try:
            enqueue_atlas_task(location_id)
        except Exception as e:
            logger.error("Failed to enqueue atlas task: %s", e)

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

import logging

from app.agents.atlas_illustrator import atlas_node
from app.api.services.background import enqueue_cloud_task, is_local_dev, submit_once
from app.core.controller import cartography_controller_node
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
    enqueue_cloud_task(
        "/internal/paint-atlas",
        {"location_id": location_id},
        log_label=f"location_id={location_id}",
    )


def trigger_atlas_task(location_id: str) -> None:
    """Fire the Atlas illustration for a location: deduped background run in local dev, Cloud Tasks in the cloud."""
    if is_local_dev():
        submit_once(f"atlas:{location_id}", run_atlas, location_id)
    else:
        try:
            enqueue_atlas_task(location_id)
        except Exception as e:
            logger.error("Failed to enqueue atlas task: %s", e)

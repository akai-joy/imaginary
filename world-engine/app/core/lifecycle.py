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
"""Deterministic World / Season lifecycle (controller-owned, never an LLM).

A World is one limited-time themed drop. Its window is time-boxed
(``opens_at``/``closes_at``) — that scarcity is the event energy. On close a
deterministic controller (1) flips ``status`` to ``archived``, (2) fires the
Showcase subgraph as a season-finale anthology, and (3) opens the next themed drop.
Worlds are archived, never deleted: the finished world is the reward.

This module owns steps (1) and (3). Step (2) — firing the showcase anthology — is
left to the caller (the showcase trigger already lives in the REST layer); this
skeleton exposes the deterministic state transitions it builds on.
"""

import logging
from datetime import datetime, timezone

from app.core.store import CanonStore
from app.core.types import World, WorldStatus

logger = logging.getLogger(__name__)


def close_world(
    store: CanonStore, world_id: str, *, now: datetime | None = None
) -> World | None:
    """Archive a world (the drop's window has closed). Idempotent and deterministic.

    Returns the archived world, or None if it doesn't exist or was already archived.
    """
    world = store.get_world(world_id)
    if world is None:
        logger.warning("close_world: no such world %s", world_id)
        return None
    if world.status == WorldStatus.ARCHIVED:
        return None

    world.status = WorldStatus.ARCHIVED
    if world.closes_at is None:
        world.closes_at = now or datetime.now(timezone.utc)
    store.save_world(world)
    logger.info("Lifecycle archived world: %s", world.id)
    return world


def open_world(store: CanonStore, world: World) -> World:
    """Open a new themed drop as the active world. Deterministic."""
    world.status = WorldStatus.ACTIVE
    store.save_world(world)
    logger.info("Lifecycle opened world: %s", world.id)
    return world


def rollover_world(
    store: CanonStore, next_world: World, *, now: datetime | None = None
) -> tuple[World | None, World]:
    """Close the current active world and open the next one.

    Returns ``(archived_world_or_None, opened_world)``. The caller is responsible for
    step (2) of the lifecycle — firing the Showcase subgraph as a season-finale
    anthology over the archived world's top trees — since the showcase trigger lives
    in the REST layer.
    """
    current = store.get_active_world()
    archived = close_world(store, current.id, now=now) if current else None
    # TODO(showcase): fire the Showcase subgraph as a season-finale anthology over
    # `archived`'s top trees before opening the next drop.
    opened = open_world(store, next_world)
    return archived, opened

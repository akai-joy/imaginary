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
"""Season-finale artifacts: binding a world's anthology when its drop closes.

The compiler is deterministic and read-only (no LLM), so binding is cheap:
the close/rollover endpoints pre-warm it on the background pool, and
GET /world/{id}/book compiles inline when the cached file is missing (or
always, for a still-open world, so the Working Draft stays current).
"""

import logging
import os
from pathlib import Path

from app.api.services.background import submit_once
from app.book_compiler import write_book
from app.core.store import CanonStore

logger = logging.getLogger(__name__)


def books_dir() -> Path:
    return Path(os.getenv("WORLD_ENGINE_BOOKS_DIR", "books"))


def book_path(world_id: str, *, draft: bool = False) -> Path:
    # Drafts cache separately: a Working Draft bound while the window was open
    # must never be served as the sealed world's finale edition.
    suffix = "_draft" if draft else ""
    return books_dir() / f"{world_id}_anthology{suffix}.html"


def bind_book(
    world_id: str, store: CanonStore | None = None, *, draft: bool = False
) -> Path:
    """Compile and cache the anthology for a world; returns the written path."""
    path = write_book(
        out_path=book_path(world_id, draft=draft), world_id=world_id, store=store
    )
    logger.info("Bound season anthology for %s -> %s", world_id, path)
    return path


def schedule_book_binding(world_id: str) -> None:
    """Pre-warm the anthology on the shared background pool (deduped)."""
    submit_once(f"book:{world_id}", bind_book, world_id)

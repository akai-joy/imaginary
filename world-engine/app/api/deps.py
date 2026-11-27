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
"""Shared REST-layer dependencies.

Route modules access everything here as ``deps.<name>`` (module-attribute
lookup, not ``from``-imports), so tests can monkeypatch a single point —
``app.api.deps.get_store`` / ``app.api.deps.get_user_id_from_token`` — and
every router sees the patched version.
"""

import logging
import os
import threading

from fastapi import HTTPException
from google.adk.sessions import InMemorySessionService

from app.core.lifecycle import tick
from app.core.store import get_store
from app.core.types import DEFAULT_WORLD_ID, SEED_WORLD, World

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton session service — shared across all requests
# ---------------------------------------------------------------------------

_session_service: InMemorySessionService | None = None
_session_service_lock = threading.Lock()


def get_session_service() -> InMemorySessionService:
    """Return the singleton session service, creating it lazily if needed."""
    global _session_service
    if _session_service is None:
        with _session_service_lock:
            if _session_service is None:
                _session_service = InMemorySessionService()
    return _session_service


def initialise_session_service() -> InMemorySessionService:
    """Create and register the singleton session service at application startup."""
    global _session_service
    with _session_service_lock:
        _session_service = InMemorySessionService()
        return _session_service


def reset_session_service() -> None:
    """Clear the singleton session service (useful for tests)."""
    global _session_service
    with _session_service_lock:
        _session_service = None


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------


def get_user_id_from_token(authorization: str | None, strict: bool = False) -> str:
    """Helper to extract user identity from Firebase Auth ID token, fallback to local dev user."""
    is_strict_active = (
        os.environ.get("K_SERVICE") is not None
        or os.environ.get("REQUIRE_AUTH", "").upper() == "TRUE"
    )

    if not authorization or not authorization.startswith("Bearer "):
        if strict and is_strict_active:
            raise HTTPException(status_code=401, detail="Authentication required")
        return "playground_user"

    token_str = authorization.replace("Bearer ", "")
    firebase_app_id = os.environ.get("VITE_FIREBASE_APP_ID") or os.environ.get(
        "FIREBASE_APP_ID"
    )
    if firebase_app_id:
        try:
            import firebase_admin
            from firebase_admin import auth

            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app()

            decoded_token = auth.verify_id_token(token_str)
            uid = decoded_token.get("uid") or decoded_token.get("email")
            if not uid:
                if strict and is_strict_active:
                    raise HTTPException(status_code=401, detail="Invalid token payload")
                return "playground_user"
            return uid
        except Exception as e:
            logger.warning("Firebase token verification failed, using fallback: %s", e)
            if strict and is_strict_active:
                raise HTTPException(
                    status_code=401, detail=f"Firebase token verification failed: {e}"
                ) from e

    if strict and is_strict_active:
        raise HTTPException(
            status_code=401,
            detail="Authentication required (Firebase App ID not configured)",
        )
    return "playground_user"


def active_world_id() -> str:
    """Resolve which world to serve: advance the lifecycle, else fall back to the newest world (or the default seed)."""
    store = get_store()
    w = tick(store)
    if w:
        return w.id
    # Fallback to the most recently opened world (newest first)
    worlds = store.list_worlds()
    if worlds:
        return worlds[0].id
    return DEFAULT_WORLD_ID


def resolve_active_world() -> World:
    """The active world object with the standard fallback chain (default seed last)."""
    store = get_store()
    return (
        store.get_world(active_world_id())
        or store.get_world(DEFAULT_WORLD_ID)
        or SEED_WORLD
    )

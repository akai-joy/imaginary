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
"""Shared background execution for the REST layer.

All fire-and-forget work (showcase runs, atlas painting, audio warming) goes
through one small pool of daemon workers instead of unbounded ad-hoc threads,
and each task carries a dedupe key so a flurry of identical triggers (e.g.
votes on the same tree) launches at most one run.

Daemon workers (not ThreadPoolExecutor) on purpose: executor threads are
non-daemon and their atexit hook would block interpreter shutdown while a
long warm-up or showcase run is mid-flight.
"""

import json
import logging
import os
import queue
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2

_task_queue: queue.Queue = queue.Queue()
_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()
_workers_started = False
_workers_lock = threading.Lock()


def is_local_dev() -> bool:
    """True when running locally (no GCP project / Cloud Run), so async work runs in-process instead of via Cloud Tasks."""
    local_dev_env = os.getenv("WORLD_ENGINE_LOCAL_DEV")
    if local_dev_env is not None:
        return local_dev_env.upper() == "TRUE"
    return not os.getenv("GOOGLE_CLOUD_PROJECT") or not os.getenv("K_SERVICE")


def _worker() -> None:
    while True:
        key, fn, args = _task_queue.get()
        try:
            fn(*args)
        except Exception:
            logger.exception("Background task %r failed", key)
        finally:
            with _in_flight_lock:
                _in_flight.discard(key)
            _task_queue.task_done()


def _ensure_workers() -> None:
    global _workers_started
    with _workers_lock:
        if _workers_started:
            return
        for i in range(_MAX_WORKERS):
            threading.Thread(target=_worker, daemon=True, name=f"we-bg-{i}").start()
        _workers_started = True


def submit_once(key: str, fn: Callable[..., object], *args: object) -> bool:
    """Run fn(*args) on the shared pool unless a task with the same key is already queued or running.

    Returns True if the task was submitted, False if it was deduped away.
    """
    with _in_flight_lock:
        if key in _in_flight:
            logger.info("Background task %r already in flight; skipping duplicate.", key)
            return False
        _in_flight.add(key)

    _ensure_workers()
    _task_queue.put((key, fn, args))
    return True


def enqueue_cloud_task(
    path: str, payload: dict[str, Any], *, log_label: str = ""
) -> None:
    """Enqueue an internal HTTP callback on Google Cloud Tasks (production async path)."""
    from google.cloud import tasks_v2

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
    queue_name = os.getenv("CLOUD_TASKS_QUEUE", "showcase-queue")

    service_url = os.getenv("SERVICE_URL") or os.getenv("PUBLIC_URL")
    if not service_url:
        logger.warning(
            "SERVICE_URL or PUBLIC_URL env var not set. Defaulting callback URL to localhost."
        )
        service_url = "http://localhost:8000"

    target_url = f"{service_url.rstrip('/')}/{path.lstrip('/')}"

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue_name)

    task: dict[str, Any] = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
        }
    }

    service_account_email = os.getenv("CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
    if service_account_email:
        task["http_request"]["oidc_token"] = {
            "service_account_email": service_account_email,
            "audience": target_url,
        }

    logger.info(
        "Enqueuing Cloud Tasks target=%s%s",
        target_url,
        f" ({log_label})" if log_label else "",
    )
    client.create_task(request={"parent": parent, "task": task})

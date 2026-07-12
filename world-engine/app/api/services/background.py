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
# See the License for the specific language governing permissions and
# limitations under the License.
"""Shared background execution for the REST layer.

All fire-and-forget work (showcase runs, atlas painting, audio warming) goes
through one small thread pool instead of unbounded ad-hoc threads, and each
task carries a dedupe key so a flurry of identical triggers (e.g. votes on the
same tree) launches at most one run.
"""

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="we-bg")
_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


def is_local_dev() -> bool:
    """True when running locally (no GCP project / Cloud Run), so async work runs in-process instead of via Cloud Tasks."""
    local_dev_env = os.getenv("WORLD_ENGINE_LOCAL_DEV")
    if local_dev_env is not None:
        return local_dev_env.upper() == "TRUE"
    return not os.getenv("GOOGLE_CLOUD_PROJECT") or not os.getenv("K_SERVICE")


def submit_once(key: str, fn: Callable[..., object], *args: object) -> bool:
    """Run fn(*args) on the shared pool unless a task with the same key is already queued or running.

    Returns True if the task was submitted, False if it was deduped away.
    """
    with _in_flight_lock:
        if key in _in_flight:
            logger.info("Background task %r already in flight; skipping duplicate.", key)
            return False
        _in_flight.add(key)

    def _run() -> None:
        try:
            fn(*args)
        except Exception:
            logger.exception("Background task %r failed", key)
        finally:
            with _in_flight_lock:
                _in_flight.discard(key)

    _executor.submit(_run)
    return True

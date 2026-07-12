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
"""The shared background pool must dedupe identical in-flight tasks:
a flurry of votes on one tree may launch at most one showcase run."""

import threading
import time

from app.api.services import background, showcase_runner


def _wait_for_key_release(key: str, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with background._in_flight_lock:
            if key not in background._in_flight:
                return True
        time.sleep(0.01)
    return False


def test_submit_once_dedupes_while_in_flight():
    key = "test:dedupe"
    started = threading.Event()
    gate = threading.Event()
    runs = []

    def blocked():
        runs.append(1)
        started.set()
        gate.wait(timeout=5)

    try:
        assert background.submit_once(key, blocked) is True
        assert started.wait(timeout=5)
        # Duplicate triggers while the first run is still going are dropped
        assert background.submit_once(key, blocked) is False
        assert background.submit_once(key, blocked) is False
    finally:
        gate.set()

    assert _wait_for_key_release(key)
    assert runs == [1]

    # Once the run finishes, the same key is accepted again
    assert background.submit_once(key, lambda: None) is True
    assert _wait_for_key_release(key)


def test_submit_once_releases_key_when_task_raises():
    key = "test:raises"

    def boom():
        raise RuntimeError("kaput")

    assert background.submit_once(key, boom) is True
    assert _wait_for_key_release(key)
    assert background.submit_once(key, lambda: None) is True
    assert _wait_for_key_release(key)


def test_vote_flurry_launches_one_showcase_run(monkeypatch):
    monkeypatch.setattr(showcase_runner, "is_local_dev", lambda: True)

    started = threading.Event()
    gate = threading.Event()
    runs = []

    def fake_local_run():
        runs.append(1)
        started.set()
        gate.wait(timeout=5)

    monkeypatch.setattr(showcase_runner, "_run_showcase_local", fake_local_run)

    try:
        for _ in range(5):
            showcase_runner.trigger_showcase_task("tree_x")
        assert started.wait(timeout=5)
    finally:
        gate.set()

    assert _wait_for_key_release("showcase:tree_x")
    assert runs == [1]

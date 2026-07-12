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
"""Pinned invariant: ADK Runners are only ever built by app.core.runner_factory.

Every Runner must wrap an App that carries SecurityPlugin. If any production
module constructs Runner() directly (easy to reintroduce while moving routes
around), a contribution path could silently run without the security plugin.
This test fails the moment such a construction appears.
"""

import re
from pathlib import Path

WORLD_ENGINE_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIRS = ["app", "showcase"]
ALLOWED_FILE = WORLD_ENGINE_ROOT / "app" / "core" / "runner_factory.py"

# Matches Runner( and runners.Runner( but not create_runner( / MockRunner(
RUNNER_CONSTRUCTION = re.compile(r"(?<![\w])Runner\(")
RUNNER_IMPORT = re.compile(r"from\s+google\.adk\.runners\s+import\b")


def _production_files():
    for dirname in PRODUCTION_DIRS:
        yield from (WORLD_ENGINE_ROOT / dirname).rglob("*.py")


def test_runner_constructed_only_in_runner_factory():
    offenders = []
    for path in _production_files():
        if path == ALLOWED_FILE:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if RUNNER_CONSTRUCTION.search(line):
                offenders.append(f"{path.relative_to(WORLD_ENGINE_ROOT)}:{lineno} {line.strip()}")
    assert not offenders, (
        "Runner() must only be constructed via app.core.runner_factory.create_runner "
        "(SecurityPlugin coverage depends on it). Direct constructions found:\n"
        + "\n".join(offenders)
    )


def test_runner_class_imported_only_in_runner_factory():
    offenders = []
    for path in _production_files():
        if path == ALLOWED_FILE:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if RUNNER_IMPORT.search(line):
                offenders.append(f"{path.relative_to(WORLD_ENGINE_ROOT)}:{lineno} {line.strip()}")
    assert not offenders, (
        "google.adk.runners should only be imported by app.core.runner_factory:\n"
        + "\n".join(offenders)
    )


def test_runner_factory_wraps_app_with_security_plugin():
    """The factory itself must build Runner from the App (which carries plugins)."""
    src = (ALLOWED_FILE).read_text(encoding="utf-8")
    assert "def create_runner" in src
    assert RUNNER_CONSTRUCTION.search(src), "factory no longer constructs Runner?"
    assert re.search(r"Runner\(\s*app=app", src), (
        "create_runner must pass the App object (plugin carrier) to Runner"
    )

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
"""Architectural invariants for the modular REST layer (REFACTORING_PROPOSAL.md).

Pins:
1. Dependency direction: app/agents and app/core never import from app/api or fast_api_app.
2. Singleton SessionService: production REST modules use deps.get_session_service(),
   never constructing InMemorySessionService() directly outside app/api/deps.py.
3. Ephemeral session cleanup: contribution_runner and showcase_runner reuse the
   singleton and delete temporary sessions after each run so memory stays bounded.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.api import deps
from app.api.services import contribution_runner, showcase_runner

WORLD_ENGINE_ROOT = Path(__file__).resolve().parents[2]
SESSION_SERVICE_CONSTRUCTION = re.compile(r"(?<![\w])InMemorySessionService\(")


def test_core_and_agents_never_import_api_layer():
    offenders: list[str] = []
    for subdir in ("app/agents", "app/core"):
        for path in (WORLD_ENGINE_ROOT / subdir).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(("app.api", "app.fast_api_app")):
                            offenders.append(
                                f"{path.relative_to(WORLD_ENGINE_ROOT)}:{node.lineno} import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith(("app.api", "app.fast_api_app")):
                        offenders.append(
                            f"{path.relative_to(WORLD_ENGINE_ROOT)}:{node.lineno} from {node.module}"
                        )
    assert not offenders, (
        "app/agents and app/core must not depend on the REST layer:\n"
        + "\n".join(offenders)
    )


def test_in_memory_session_service_constructed_only_in_deps():
    allowed = WORLD_ENGINE_ROOT / "app" / "api" / "deps.py"
    offenders: list[str] = []
    for path in (WORLD_ENGINE_ROOT / "app" / "api").rglob("*.py"):
        if path == allowed:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if SESSION_SERVICE_CONSTRUCTION.search(line):
                offenders.append(
                    f"{path.relative_to(WORLD_ENGINE_ROOT)}:{lineno} {line.strip()}"
                )
    assert not offenders, (
        "REST modules must reuse deps.get_session_service() instead of constructing "
        "InMemorySessionService() directly:\n" + "\n".join(offenders)
    )


def test_singleton_session_service_lifecycle():
    deps.reset_session_service()
    first = deps.get_session_service()
    second = deps.get_session_service()
    assert first is second

    reinit = deps.initialise_session_service()
    assert reinit is not first
    assert deps.get_session_service() is reinit


def test_contribution_runner_reuses_singleton_and_cleans_up_session(monkeypatch):
    singleton = deps.initialise_session_service()
    seen_services = []

    class _FakeRunner:
        def run(self, *, new_message, user_id, session_id):
            return iter([])

    def _fake_create_runner(app_obj, session_service):
        seen_services.append(session_service)
        return _FakeRunner()

    monkeypatch.setattr(contribution_runner, "create_runner", _fake_create_runner)

    result = contribution_runner.execute_contribution_pipeline(
        user_id="author_1",
        id_token=None,
        world_id="world_genesis",
        title="Test Title",
        entry_type="lore",
        body="Some lore.",
        derived_from=[],
        references=[],
    )

    assert result["status"] == "accepted"
    assert seen_services == [singleton]
    remaining = singleton.list_sessions_sync(app_name="app", user_id="author_1")
    assert remaining.sessions == []


def test_showcase_runner_reuses_singleton_and_cleans_up_session(monkeypatch):
    singleton = deps.initialise_session_service()
    seen_services = []

    class _FakeRunner:
        def run(self, *, new_message, user_id, session_id):
            return iter([])

    def _fake_create_runner(app_obj, session_service):
        seen_services.append(session_service)
        return _FakeRunner()

    monkeypatch.setattr(showcase_runner, "create_runner", _fake_create_runner)

    showcase_runner.run_showcase()

    assert seen_services == [singleton]
    remaining = singleton.list_sessions_sync(app_name="showcase", user_id="system")
    assert remaining.sessions == []

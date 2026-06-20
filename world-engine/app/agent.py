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

import os

import google.auth
from google.adk.apps import App
from google.adk.workflow import Edge, Workflow
from google.adk.workflow._graph import START
from google.adk.workflow.utils._workflow_graph_utils import build_node

from app.agents.continuity import continuity_node
from app.agents.intake import intake_router
from app.agents.moderation import moderation_node
from app.agents.narrator import narrator_node
from app.agents.provenance import provenance_node
from app.agents.scoring import scoring_node

# Authenticate with Google Cloud
if "GOOGLE_GENAI_USE_VERTEXAI" in os.environ:
    use_vertex = os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "True"
else:
    use_vertex = False
    try:
        _, project_id = google.auth.default()
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            use_vertex = True
    except Exception:
        pass

if use_vertex:
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"


# Pre-build nodes to avoid duplicate node names in explicit edges
intake_router_node = build_node(intake_router)
moderation_node_node = build_node(moderation_node)
continuity_node_node = build_node(continuity_node)
provenance_node_node = build_node(provenance_node)
scoring_node_node = build_node(scoring_node)
narrator_node_node = build_node(narrator_node)

# Root workflow skeleton for the world engine ingest pipeline
root_workflow = Workflow(
    name="world_engine_workflow",
    edges=[
        Edge(from_node=START, to_node=intake_router_node),
        Edge(from_node=intake_router_node, to_node=moderation_node_node),
        Edge(
            from_node=moderation_node_node,
            to_node=continuity_node_node,
            route=["ALLOW", "FLAG"],
        ),
        Edge(
            from_node=continuity_node_node,
            to_node=provenance_node_node,
            route="consistent",
        ),
        Edge(
            from_node=provenance_node_node,
            to_node=scoring_node_node,
        ),
        Edge(
            from_node=scoring_node_node,
            to_node=narrator_node_node,
        ),
    ],
)

# App wrapping the root workflow
app = App(
    root_agent=root_workflow,
    name="app",
)

root_agent = root_workflow

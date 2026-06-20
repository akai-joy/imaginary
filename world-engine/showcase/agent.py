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

from app.agents.showcase_tally import showcase_tally_node
from app.agents.storyboard import storyboard_node

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


# Pre-build nodes
tally_node = build_node(showcase_tally_node)
storyboard_node_node = build_node(storyboard_node)

# Showcase workflow skeleton
showcase_workflow = Workflow(
    name="showcase_workflow",
    edges=[
        Edge(from_node=START, to_node=tally_node),
        Edge(from_node=tally_node, to_node=storyboard_node_node),
    ],
)

# App wrapping the showcase workflow
app = App(
    root_agent=showcase_workflow,
    name="showcase",
)

root_agent = showcase_workflow

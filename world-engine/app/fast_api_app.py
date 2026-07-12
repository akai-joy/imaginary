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
"""Thin FastAPI entrypoint: bootstrap, mounts, router registration.

Endpoint logic lives in app/api/routes/*; background work in app/api/services/*.
Modules under app/agents and app/core must never import from app/api or this file.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.api.routes import canon, contribute, internal, scenes, showcase, world
from app.api.services.audio_warmer import (
    schedule_scene_audio_warmup,
    set_scene_provider,
)
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

load_dotenv()

setup_telemetry()
try:
    logging_client = google_cloud_logging.Client()
    logging_client.setup_logging()
    gcp_logger = logging_client.logger(__name__)
    logger = logging.getLogger(__name__)
    is_cloud_logging = True
except Exception:
    logger = logging.getLogger(__name__)
    gcp_logger = None
    is_cloud_logging = False

env_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else []
)
allow_origins = list(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        *env_origins,
    }
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "world-engine"
app.description = "API for interacting with the Agent world-engine"

# CORS middleware is automatically managed by get_fast_api_app using the allow_origins parameter


os.makedirs("gcs_mock", exist_ok=True)
app.mount("/gcs_mock", StaticFiles(directory="gcs_mock"), name="gcs_mock")
os.makedirs("cache", exist_ok=True)
app.mount("/cache", StaticFiles(directory="cache"), name="cache")


# --- REST API Endpoints for the Front-End ---

app.include_router(world.router)
app.include_router(canon.router)
app.include_router(scenes.router)
app.include_router(showcase.router)
app.include_router(contribute.router)
app.include_router(internal.router)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback."""
    if is_cloud_logging and gcp_logger:
        gcp_logger.log_struct(feedback.model_dump(), severity="INFO")
    else:
        logger.info("Feedback: %s", feedback.model_dump())
    return {"status": "success"}


# The warmer needs the scene builder; register it, then start the warm-up on the
# shared background pool (was a raw daemon thread at import time).
set_scene_provider(scenes.get_scene)
schedule_scene_audio_warmup()


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

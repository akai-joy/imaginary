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

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import yaml
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event, EventActions
from google.auth.transport import requests
from google.genai import types
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from app.core.config import POLICY_PATH
from app.core.types import Contribution, ContributionStatus, ContributionType

logger = logging.getLogger(__name__)


class IngestInput(BaseModel):
    """Structured input for the world-engine Ingest workflow."""

    user_text: str = Field(description="The raw storytelling contribution text.")
    author_id: str = Field(
        description="The ID of the author submitting this contribution."
    )
    id_token: str | None = Field(
        default=None, description="Optional Google Auth ID token to verify."
    )


class RouterOutput(BaseModel):
    """Structured output expected from the router classification LLM call."""

    contribution_type: ContributionType = Field(
        description="The classified type of the storytelling contribution."
    )
    title: str = Field(description="A concise, engaging title for the contribution.")
    body: str = Field(description="The normalized body text of the contribution.")


def load_policy_config() -> dict:
    """Loads configuration policies from policy.yaml."""
    if os.path.exists(POLICY_PATH):
        try:
            with open(POLICY_PATH) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load policy.yaml: %s", e)
    return {}


def get_model_for_role(role: str) -> str:
    """Gets the configured model name for a specific role/node."""
    policy = load_policy_config()
    return policy.get("models", {}).get(role, "gemini-3.5-flash")


def verify_google_auth(author_id: str, id_token_str: str | None) -> str:
    """Verifies the author's Google Auth token if provided.

    If no token is provided, it falls back to the provided author_id (permitted for local dev).
    """
    if not id_token_str:
        logger.warning(
            "No Google Auth ID token provided. Proceeding with author_id: %s", author_id
        )
        return author_id

    try:
        # Verify the ID token (audience check is omitted for flexibility in dev/test environment)
        id_info = id_token.verify_oauth2_token(
            id_token_str, requests.Request(), audience=None
        )
        verified_author_id = id_info.get("email") or id_info.get("sub")
        if not verified_author_id:
            raise ValueError("Token does not contain email or sub claim.")
        return verified_author_id
    except Exception as e:
        logger.error("Google Auth token verification failed: %s", e)
        raise ValueError(f"Authentication failed: {e}") from e


def intake_router(ctx: Context, node_input: Any):
    """Intake and Router node.

    Verifies user authentication, classifies contribution type, normalize fields,
    and returns a structured Contribution object.
    """
    user_text = ""
    author_id = "playground_user"
    id_token_str = None

    # Resolve input variables from various structures
    if isinstance(node_input, str):
        user_text = node_input
    elif isinstance(node_input, IngestInput):
        user_text = node_input.user_text
        author_id = node_input.author_id
        id_token_str = node_input.id_token
    elif isinstance(node_input, dict):
        user_text = node_input.get("user_text", "")
        author_id = node_input.get("author_id", "playground_user")
        id_token_str = node_input.get("id_token")
    elif hasattr(node_input, "parts"):  # types.Content from client message
        parts = node_input.parts or []
        if parts:
            user_text = parts[0].text or ""
        author_id = "playground_user"

    # 1. Authenticate human author
    authenticated_author_id = verify_google_auth(author_id, id_token_str)

    # 2. Classify and normalize via LLM
    model_name = get_model_for_role("router")
    client = genai.Client()

    prompt = (
        "You are the Intake and Router agent for a collaborative storytelling system. "
        "Analyze the following user storytelling contribution. Classify its type, extract "
        "a clean title, and normalize its body text. "
        f"Input contribution text:\n{user_text}"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RouterOutput,
            temperature=0.1,
        ),
    )

    result = RouterOutput.model_validate_json(response.text)

    # 3. Construct normalized Contribution object
    contrib = Contribution(
        id=str(uuid.uuid4()),
        author_id=authenticated_author_id,
        type=result.contribution_type,
        title=result.title,
        body=result.body,
        created_at=datetime.now(timezone.utc),
        status=ContributionStatus.PENDING,
        references=[],
    )

    # Yield content event for display in CLI/playground
    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        f"**Routed & Normalized Ingest Contribution**\n\n"
                        f"- **ID**: {contrib.id}\n"
                        f"- **Type**: `{contrib.type.value}`\n"
                        f"- **Title**: *{contrib.title}*\n"
                        f"- **Body**: {contrib.body}\n"
                        f"- **Author**: {contrib.author_id}\n"
                        f"- **Status**: `{contrib.status.value}`"
                    )
                )
            ],
        )
    )

    # Yield actual output and save original raw_text in state for downstream screening
    yield Event(
        output=contrib, actions=EventActions(state_delta={"raw_text": user_text})
    )

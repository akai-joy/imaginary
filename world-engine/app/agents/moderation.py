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

import base64
import logging
import os
import re
from enum import StrEnum

import yaml
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event, EventActions
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import POLICY_PATH
from app.core.types import Contribution, ContributionStatus

logger = logging.getLogger(__name__)


class ModerationVerdict(StrEnum):
    ALLOW = "ALLOW"
    FLAG = "FLAG"
    BLOCK = "BLOCK"


class ModerationResponse(BaseModel):
    """Structured output from the safety classification model or scanning rules."""

    verdict: ModerationVerdict = Field(
        description="The moderation verdict: ALLOW, FLAG, or BLOCK."
    )
    category: str = Field(
        description="The policy category matched (e.g., 'none', 'explicit_sexual', 'hidden_content', 'prompt_injection')."
    )
    reason: str = Field(
        description="Detailed explanation of the safety classification."
    )


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


def scan_hidden_content(text: str) -> ModerationResponse | None:
    """Deterministic check for hidden/encoded payloads or structures."""
    # 1. Zero-width and invisible characters
    zw_regex = re.compile(r"[\u200b-\u200d\ufeff\u200e\u200f\u202a-\u202e]")
    if zw_regex.search(text):
        stripped = zw_regex.sub("", text)
        return ModerationResponse(
            verdict=ModerationVerdict.BLOCK,
            category="hidden_content",
            reason=f"Detected and stripped zero-width/invisible unicode characters. Stripped text: '{stripped}'",
        )

    # 2. Base64 encoding scan (minimum 8 characters, optional padding)
    b64_regex = re.compile(r"\b[A-Za-z0-9+/]{8,}={0,2}\b")
    for match in b64_regex.finditer(text):
        potential_b64 = match.group(0)
        try:
            decoded = base64.b64decode(potential_b64, validate=True)
            decoded_str = decoded.decode("utf-8", errors="strict")
            # Check if it decodes to readable ASCII string
            if all(32 <= ord(c) < 127 for c in decoded_str) and len(decoded_str) > 4:
                from app.core.security import detect_deterministic_injection
                # Block if it has a space, injection keywords, or security keywords to prevent false positives on random strings
                if (
                    " " in decoded_str
                    or detect_deterministic_injection(decoded_str)
                    or any(kw in decoded_str.lower() for kw in ["secret", "code", "admin", "flag", "bypass", "ignore", "system", "override", "instruction", "block", "allow"])
                ):
                    return ModerationResponse(
                        verdict=ModerationVerdict.BLOCK,
                        category="hidden_content",
                        reason=f"Detected and blocked base64 encoded message containing injection: '{decoded_str}'",
                    )
        except Exception:
            pass

    # 3. Hex encoding scan
    hex_regex = re.compile(r"\b[0-9a-fA-F]{8,}\b")
    for match in hex_regex.finditer(text):
        potential_hex = match.group(0)
        try:
            decoded = bytes.fromhex(potential_hex)
            decoded_str = decoded.decode("utf-8", errors="strict")
            if all(32 <= ord(c) < 127 for c in decoded_str) and len(decoded_str) > 4:
                from app.core.security import detect_deterministic_injection
                if (
                    " " in decoded_str
                    or detect_deterministic_injection(decoded_str)
                    or any(kw in decoded_str.lower() for kw in ["secret", "code", "admin", "flag", "bypass", "ignore", "system", "override", "instruction", "block", "allow"])
                ):
                    return ModerationResponse(
                        verdict=ModerationVerdict.BLOCK,
                        category="hidden_content",
                        reason=f"Detected and blocked hex encoded message containing injection: '{decoded_str}'",
                    )
        except Exception:
            pass

    # 4. Mixed-script / Homoglyph lookalike check (e.g. Cyrillic characters mixed with Latin)
    has_latin = any(
        0x0020 <= ord(c) <= 0x007E or 0x00A0 <= ord(c) <= 0x024F for c in text
    )
    has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in text)
    if has_latin and has_cyrillic:
        return ModerationResponse(
            verdict=ModerationVerdict.BLOCK,
            category="hidden_content",
            reason="Detected unusual mixed-script (homoglyph) unicode characters.",
        )

    # 5. Acrostic checks (spelling down lines)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 3:
        acrostic = "".join(line[0].upper() for line in lines)
        for bad_word in ["BLOCK", "FLAG", "BYPASS", "IGNORE"]:
            if bad_word in acrostic:
                return ModerationResponse(
                    verdict=ModerationVerdict.BLOCK,
                    category="hidden_content",
                    reason=f"Detected hidden acrostic spelling word: '{acrostic}'",
                )

    return None


def scan_prompt_injection(text: str) -> ModerationResponse | None:
    """Regex scan for direct or indirect prompt injection patterns."""
    from app.core.security import INJECTION_PATTERNS
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            stripped = re.sub(pattern, "[STRIPPED INJECTION]", text)
            return ModerationResponse(
                verdict=ModerationVerdict.BLOCK,
                category="prompt_injection",
                reason=f"Detected and blocked prompt injection: '{pattern}'. Stripped text: '{stripped}'",
            )
    return None


def load_moderation_rules() -> tuple[list[str], list[str], list[str]]:
    """Loads profile-specific block/flag rules from policy.yaml."""
    policy = load_policy_config()
    active_profile = policy.get("active_profile", "default")
    moderation_cfg = policy.get("moderation", {})

    hard_block = moderation_cfg.get("hard_block", [])
    profile_cfg = moderation_cfg.get("profiles", {}).get(active_profile, {})
    block_categories = profile_cfg.get("block", [])
    flag_categories = profile_cfg.get("flag", [])

    return hard_block, block_categories, flag_categories


def moderation_node(ctx: Context, node_input: Contribution):
    """Moderation / Safety Node.

    Loads configuration policies, performs deterministic checks, and calls the
    Gemini 3.5 model for safety profile enforcement.
    """
    contrib = node_input
    raw_text = ctx.state.get("raw_text") or contrib.body

    # 1. Deterministic Content Scanning
    hidden_check = scan_hidden_content(raw_text)
    if hidden_check:
        logger.warning(
            "Halted on BLOCK (deterministic hidden content): %s", hidden_check.reason
        )
        contrib.status = ContributionStatus.BLOCKED
        yield Event(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=f"Blocked: {hidden_check.reason}")],
            ),
            actions=EventActions(route=ModerationVerdict.BLOCK),
        )
        yield Event(output=contrib, actions=EventActions(route=ModerationVerdict.BLOCK))
        return

    injection_check = scan_prompt_injection(raw_text)
    if injection_check:
        logger.warning(
            "Halted on BLOCK (deterministic prompt injection): %s",
            injection_check.reason,
        )
        contrib.status = ContributionStatus.BLOCKED
        yield Event(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=f"Blocked: {injection_check.reason}")],
            ),
            actions=EventActions(route=ModerationVerdict.BLOCK),
        )
        yield Event(output=contrib, actions=EventActions(route=ModerationVerdict.BLOCK))
        return

    # 2. LLM Policy Assessment
    _hard_block, block_categories, flag_categories = load_moderation_rules()
    model_name = get_model_for_role("moderation")
    client = genai.Client()

    prompt = f"""Evaluate the following collaborative storytelling contribution. Determine if it violates safety policies and return a structured JSON response matching the ModerationResponse schema.

Hard-Block Categories (Always BLOCK):
- minor_sexualization (sexual content involving/depicting minors)
- illegal_synthesis_instructions (how to make, synthesize, or manufacture drugs/weapons/explosives/bombs, including reference to fabrication or gathering household chemicals for explosives, even in fictional/storytelling/creative contexts)
- threats_doxxing_real_people (doxxing, targeting real people, or threats)

Active Profile Blocks (Block if matching):
{", ".join(block_categories) if block_categories else "None"}

Active Profile Flags (Flag if matching, e.g., mature theme handled non-explicitly):
{", ".join(flag_categories) if flag_categories else "None"}

Content to evaluate:
<untrusted_content>
Title: {contrib.title}
Body: {contrib.body}
Original Raw Input: {raw_text}
</untrusted_content>"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ModerationResponse,
            temperature=0.1,
        ),
    )

    verdict_data = ModerationResponse.model_validate_json(response.text)

    # 3. Handle Verdict and Route Workflow
    if verdict_data.verdict == ModerationVerdict.BLOCK:
        logger.warning(
            "Halted on BLOCK: Category=%s, Reason=%s",
            verdict_data.category,
            verdict_data.reason,
        )
        contrib.status = ContributionStatus.BLOCKED
    elif verdict_data.verdict == ModerationVerdict.FLAG:
        logger.info(
            "Marked for review (FLAG): Category=%s, Reason=%s",
            verdict_data.category,
            verdict_data.reason,
        )
        contrib.status = ContributionStatus.FLAGGED
    else:
        logger.info("Allowed: %s", verdict_data.reason)
        # Keeps status=pending until synthetic merging

    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"**Safety Verdict**: `{verdict_data.verdict.value}`\n"
                    f"- **Category**: `{verdict_data.category}`\n"
                    f"- **Reason**: {verdict_data.reason}"
                )
            ],
        ),
        actions=EventActions(route=verdict_data.verdict),
    )
    yield Event(output=contrib, actions=EventActions(route=verdict_data.verdict))

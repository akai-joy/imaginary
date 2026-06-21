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

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ContributionType(StrEnum):
    CHARACTER = "character"
    LOCATION = "location"
    FACTION = "faction"
    PLOT = "plot"
    LORE = "lore"
    OTHER = "other"


class ContributionStatus(StrEnum):
    PENDING = "pending"
    BLOCKED = "blocked"
    FLAGGED = "flagged"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Contribution(BaseModel):
    id: str
    author_id: str
    type: ContributionType
    title: str
    body: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: ContributionStatus = ContributionStatus.PENDING
    references: list[str] = Field(default_factory=list)


class CanonEntry(BaseModel):
    id: str
    type: ContributionType
    title: str
    body: str
    contributor_id: str
    derived_from: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LedgerEntry(BaseModel):
    contribution_id: str
    author_id: str
    points_delta: int
    reason: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ShowcaseJobStatus(StrEnum):
    QUEUED = "queued"
    STORYBOARDED = "storyboarded"
    DIRECTED = "directed"
    BLOCKED = "blocked"
    GENERATED = "generated"
    PUBLISHED_MOCK = "published_mock"


class Vote(BaseModel):
    id: str
    voter_id: str
    tree_id: str
    weight: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StorylineTree(BaseModel):
    tree_id: str
    root_id: str
    member_ids: list[str] = Field(default_factory=list)
    vote_total: float = 0.0
    composite_score: float = 0.0


class StoryboardScene(BaseModel):
    scene_number: int = Field(description="The ordered panel/scene number (1-based).")
    visual_description: str = Field(
        description="Detailed visual description for image/video generation model."
    )
    caption: str = Field(
        description="The text caption or dialogue line accompanying this scene."
    )
    optimized_prompt: str | None = Field(
        default=None,
        description="Detailed cinematic prompt optimized for image/video generation tools."
    )


class Storyboard(BaseModel):
    title: str = Field(description="A descriptive title for this showcase story.")
    logline: str = Field(description="A concise logline summarizing the narrative arc.")
    scenes: list[StoryboardScene] = Field(
        description="Ordered list of panels (for comic) or scenes (for reel)."
    )


class ShowcaseJob(BaseModel):
    id: str
    tree_id: str
    media_type: str  # "comic" or "reel"
    status: ShowcaseJobStatus = ShowcaseJobStatus.QUEUED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    storyboard_json: str | None = None


class MediaAsset(BaseModel):
    id: str
    job_id: str
    tree_id: str
    kind: str  # "comic" or "reel"
    gcs_url: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    contributor_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

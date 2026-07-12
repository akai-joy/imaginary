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

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Naive UTC timestamp — the store compares/persists naive UTC throughout."""
    return datetime.now(UTC).replace(tzinfo=None)


# Every world-scoped entity (Contribution, CanonEntry, Vote, ShowcaseJob) carries a
# `world_id`. Until multi-world wiring lands everything defaults to the seed world, so
# the existing single-world pipeline keeps working unchanged.
DEFAULT_WORLD_ID = "world_genesis"


class WorldStatus(StrEnum):
    ACTIVE = "active"  # contribution window open
    ARCHIVED = "archived"  # window closed; read-only collectible


class World(BaseModel):
    """One limited-time themed drop — the unit of participation.

    A world opens on an `opening_line` (a Dark-Tower-grade seed sentence with
    pursuit-pressure), not a bland theme noun. `art_style_directive` keeps generated
    media visually coherent; `moderation_profile` selects the `policy.yaml` profile.
    """

    id: str
    theme: str
    opening_line: str
    art_style_directive: str = ""
    moderation_profile: str = "default"
    status: WorldStatus = WorldStatus.ACTIVE
    opens_at: datetime = Field(default_factory=_utcnow)
    # None = open-ended (the seed/demo world has no hard deadline). A real drop is
    # time-boxed — that scarcity is the event energy.
    closes_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    map_image_url: str | None = None
    map_image_version: int = 1


# The single active world the store seeds itself with on first init, so the local
# playground and tests always have a world to scope against.
SEED_WORLD = World(
    id=DEFAULT_WORLD_ID,
    theme="Medieval Wizards",
    opening_line=(
        "The last spell in the world guttered out at dusk, and every wizard who felt "
        "it die began to run."
    ),
    art_style_directive=(
        "Painterly high-fantasy storybook illustration; candlelit medieval palette; "
        "ink-and-watercolor linework; cohesive, hand-crafted feel."
    ),
    moderation_profile="default",
)


class ContributionType(StrEnum):
    CHARACTER = "character"
    LOCATION = "location"
    BEAST = "beast"
    SPELL = "spell"
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
    world_id: str = DEFAULT_WORLD_ID
    type: ContributionType
    title: str
    body: str
    created_at: datetime = Field(default_factory=_utcnow)
    status: ContributionStatus = ContributionStatus.PENDING
    # `references` = cast/setting the contributor selected; `derived_from` = explicit
    # fork/continue lineage chosen in the UI. Both are trusted structure applied by the
    # controller (content is still moderated). Empty `derived_from` => a brand-new root.
    references: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)


class MapMeta(BaseModel):
    """World-map placement for a location, written only by the Cartographer via the controller."""

    x: float = 0.0
    y: float = 0.0
    region: str = ""
    near: list[str] = Field(default_factory=list)


class CanonEntry(BaseModel):
    id: str
    world_id: str = DEFAULT_WORLD_ID
    type: ContributionType
    title: str
    body: str
    contributor_id: str
    derived_from: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: datetime = Field(default_factory=_utcnow)
    # Set only for locations, by the Cartographer node (never by a user).
    map_meta: MapMeta | None = None


class Discovery(BaseModel):
    """Per-user exploration state for the fog-of-war overlay. One shared canon, personal fog."""

    user_id: str
    canon_id: str
    created_at: datetime = Field(default_factory=_utcnow)


class LedgerEntry(BaseModel):
    contribution_id: str
    author_id: str
    points_delta: int
    reason: str
    created_at: datetime = Field(default_factory=_utcnow)


class ShowcaseJobStatus(StrEnum):
    QUEUED = "queued"
    STORYBOARDED = "storyboarded"
    DIRECTED = "directed"
    BLOCKED = "blocked"
    GENERATED = "generated"
    PUBLISHED_MOCK = "published_mock"


class ContributionJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


class ContributionJob(BaseModel):
    """Tracks one async /contribute run. The submission payload itself travels
    with the dispatch (in-process closure locally, Cloud Tasks body in the
    cloud) so the caller's id_token never rests in the database; only the
    status and final verdict are persisted here."""

    id: str
    world_id: str = DEFAULT_WORLD_ID
    user_id: str
    status: ContributionJobStatus = ContributionJobStatus.QUEUED
    result_json: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Vote(BaseModel):
    id: str
    voter_id: str
    world_id: str = DEFAULT_WORLD_ID
    tree_id: str
    weight: float = 1.0
    created_at: datetime = Field(default_factory=_utcnow)


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
        description="Detailed cinematic prompt optimized for image/video generation tools.",
    )


class Storyboard(BaseModel):
    title: str = Field(description="A descriptive title for this showcase story.")
    logline: str = Field(description="A concise logline summarizing the narrative arc.")
    scenes: list[StoryboardScene] = Field(
        description="Ordered list of panels (for comic) or scenes (for reel)."
    )


class ShowcaseJob(BaseModel):
    id: str
    world_id: str = DEFAULT_WORLD_ID
    tree_id: str
    media_type: str  # "comic" or "reel"
    status: ShowcaseJobStatus = ShowcaseJobStatus.QUEUED
    created_at: datetime = Field(default_factory=_utcnow)
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
    created_at: datetime = Field(default_factory=_utcnow)
    node_id: str = ""
    world_id: str = ""

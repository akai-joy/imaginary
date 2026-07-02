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

import json
import re
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from datetime import UTC, datetime
from functools import lru_cache

from app.core.types import (
    DEFAULT_WORLD_ID,
    SEED_WORLD,
    CanonEntry,
    Contribution,
    LedgerEntry,
    MapMeta,
    MediaAsset,
    ShowcaseJob,
    Vote,
    World,
    WorldStatus,
)


class CanonStore(ABC):
    """Interface for world-engine persistence layer."""

    @abstractmethod
    def save_world(self, world: World) -> None:
        """Save or update a world (themed seasonal drop)."""
        pass

    @abstractmethod
    def get_world(self, world_id: str) -> World | None:
        """Retrieve a world by ID."""
        pass

    @abstractmethod
    def list_worlds(self) -> list[World]:
        """List all worlds (active and archived), newest first."""
        pass

    @abstractmethod
    def get_active_world(self) -> World | None:
        """Return the current active world (most recently opened), or None."""
        pass

    @abstractmethod
    def save_world_map_image(self, world_id: str, url: str, version: int) -> None:
        """Update a world's master map image URL and version."""
        pass

    @abstractmethod
    def save_contribution(self, contribution: Contribution) -> None:
        """Save or update a contribution."""
        pass

    @abstractmethod
    def get_contribution(self, contribution_id: str) -> Contribution | None:
        """Retrieve a contribution by ID."""
        pass

    @abstractmethod
    def save_canon_entry(self, entry: CanonEntry) -> None:
        """Save or update a canon entry."""
        pass

    @abstractmethod
    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        """Retrieve a canon entry by ID."""
        pass

    @abstractmethod
    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        """Save a new points ledger entry."""
        pass

    @abstractmethod
    def get_ledger_entries(self, author_id: str) -> list[LedgerEntry]:
        """Retrieve all ledger entries for a specific author."""
        pass

    @abstractmethod
    def list_canon_entries(self, world_id: str | None = None) -> list[CanonEntry]:
        """List all canon entries, optionally scoped to one world."""
        pass

    @abstractmethod
    def list_canon_entries_by_type(
        self, entry_type: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        """List canon entries filtered by type (powers the Map / codex views)."""
        pass

    @abstractmethod
    def search_canon_entries(
        self, query: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        """Search canon entries using text match keywords."""
        pass

    @abstractmethod
    def save_discovery(self, user_id: str, canon_id: str) -> None:
        """Record that a user has discovered a node (clears its fog). Idempotent."""
        pass

    @abstractmethod
    def list_discoveries(self, user_id: str) -> set[str]:
        """Return the set of canon_ids this user has discovered."""
        pass

    @abstractmethod
    def save_vote(self, vote: Vote) -> None:
        """Save a new human vote."""
        pass

    @abstractmethod
    def get_votes_for_tree(self, tree_id: str) -> list[Vote]:
        """Retrieve all votes for a specific story tree."""
        pass

    @abstractmethod
    def save_showcase_job(self, job: ShowcaseJob) -> None:
        """Save a showcase generation job."""
        pass

    @abstractmethod
    def get_showcase_job(self, job_id: str) -> ShowcaseJob | None:
        """Retrieve a showcase job by ID."""
        pass

    @abstractmethod
    def list_showcase_jobs(self, world_id: str | None = None) -> list[ShowcaseJob]:
        """List all showcase jobs, optionally scoped to one world."""
        pass

    @abstractmethod
    def save_media_asset(self, asset: MediaAsset) -> None:
        """Save a generated media asset."""
        pass

    @abstractmethod
    def list_media_assets(self) -> list[MediaAsset]:
        """List all generated media assets."""
        pass

    @abstractmethod
    def get_points_for_contribution(self, contribution_id: str) -> int:
        """Retrieve the points delta (score) for a contribution ID from LedgerEntry."""
        pass


class SQLiteCanonStore(CanonStore):
    """SQLite implementation of the CanonStore interface."""

    def __init__(self, db_path: str = "world.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        # sqlite3's context manager only commits/rolls back — it never closes, so
        # every call site pairs this with closing() to avoid leaking connections.
        return sqlite3.connect(self.db_path, timeout=15)

    def _init_db(self):
        with closing(self._connect()) as conn, conn:
            # WAL is persistent in the db file; readers no longer block on writers.
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            # Worlds table (themed seasonal drops). Every other entity is scoped to a world.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS worlds (
                    id TEXT PRIMARY KEY,
                    theme TEXT NOT NULL,
                    opening_line TEXT NOT NULL,
                    art_style_directive TEXT NOT NULL,
                    moderation_profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    opens_at TEXT NOT NULL,
                    closes_at TEXT,
                    created_at TEXT NOT NULL,
                    map_image_url TEXT,
                    map_image_version INTEGER DEFAULT 1
                )
            """)
            # Contributions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contributions (
                    id TEXT PRIMARY KEY,
                    author_id TEXT NOT NULL,
                    world_id TEXT NOT NULL DEFAULT 'world_genesis',
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    references_json TEXT NOT NULL
                )
            """)
            # Canon entries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canon_entries (
                    id TEXT PRIMARY KEY,
                    world_id TEXT NOT NULL DEFAULT 'world_genesis',
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    contributor_id TEXT NOT NULL,
                    derived_from_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    references_json TEXT,
                    map_meta_json TEXT
                )
            """)

            # Self-healing migration: add Living-World columns to pre-existing tables.
            # (ALTER ... ADD COLUMN appends to the end; SELECTs use named columns so order
            # never matters.)
            def _add_missing_columns(table: str, columns: dict[str, str]):
                cursor.execute(f"PRAGMA table_info({table})")
                existing = {col[1] for col in cursor.fetchall()}
                for name, ddl in columns.items():
                    if name not in existing:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

            _add_missing_columns(
                "canon_entries",
                {
                    "references_json": "references_json TEXT",
                    "map_meta_json": "map_meta_json TEXT",
                    "world_id": "world_id TEXT NOT NULL DEFAULT 'world_genesis'",
                },
            )
            _add_missing_columns(
                "contributions",
                {"world_id": "world_id TEXT NOT NULL DEFAULT 'world_genesis'"},
            )
            _add_missing_columns(
                "worlds",
                {
                    "map_image_url": "map_image_url TEXT",
                    "map_image_version": "map_image_version INTEGER DEFAULT 1",
                },
            )
            # Per-user discovery (fog-of-war) table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discoveries (
                    user_id TEXT NOT NULL,
                    canon_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, canon_id)
                )
            """)
            # Ledger entries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    contribution_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    points_delta INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Votes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id TEXT PRIMARY KEY,
                    voter_id TEXT NOT NULL,
                    world_id TEXT NOT NULL DEFAULT 'world_genesis',
                    tree_id TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            _add_missing_columns(
                "votes",
                {"world_id": "world_id TEXT NOT NULL DEFAULT 'world_genesis'"},
            )
            # Showcase jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS showcase_jobs (
                    id TEXT PRIMARY KEY,
                    world_id TEXT NOT NULL DEFAULT 'world_genesis',
                    tree_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    storyboard_json TEXT
                )
            """)
            _add_missing_columns(
                "showcase_jobs",
                {
                    "storyboard_json": "storyboard_json TEXT",
                    "world_id": "world_id TEXT NOT NULL DEFAULT 'world_genesis'",
                },
            )

            # Media assets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS media_assets (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    tree_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    gcs_url TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    hashtags_json TEXT NOT NULL,
                    contributor_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    node_id TEXT NOT NULL DEFAULT '',
                    world_id TEXT NOT NULL DEFAULT ''
                )
            """)

            _add_missing_columns(
                "media_assets",
                {
                    "node_id": "node_id TEXT NOT NULL DEFAULT ''",
                    "world_id": "world_id TEXT NOT NULL DEFAULT ''",
                },
            )

            # Seed the first active world if none exists yet, so the playground and tests
            # always have a world to scope against. We never re-seed once any world exists
            # (so archiving the seed doesn't resurrect it).
            cursor.execute("SELECT COUNT(*) FROM worlds")
            if cursor.fetchone()[0] == 0:
                w = SEED_WORLD
                cursor.execute(
                    """
                    INSERT INTO worlds (
                        id, theme, opening_line, art_style_directive, moderation_profile,
                        status, opens_at, closes_at, created_at, map_image_url, map_image_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        w.id,
                        w.theme,
                        w.opening_line,
                        w.art_style_directive,
                        w.moderation_profile,
                        w.status.value,
                        w.opens_at.isoformat(),
                        w.closes_at.isoformat() if w.closes_at else None,
                        w.created_at.isoformat(),
                        w.map_image_url,
                        w.map_image_version,
                    ),
                )

            conn.commit()

    _WORLD_COLS = (
        "id, theme, opening_line, art_style_directive, moderation_profile, "
        "status, opens_at, closes_at, created_at, map_image_url, map_image_version"
    )

    @staticmethod
    def _row_to_world(row) -> World:
        return World(
            id=row[0],
            theme=row[1],
            opening_line=row[2],
            art_style_directive=row[3],
            moderation_profile=row[4],
            status=row[5],
            opens_at=datetime.fromisoformat(row[6]),
            closes_at=datetime.fromisoformat(row[7]) if row[7] else None,
            created_at=datetime.fromisoformat(row[8]),
            map_image_url=row[9] if len(row) > 9 else None,
            map_image_version=row[10] if len(row) > 10 else 1,
        )

    # --- Worlds (themed seasonal drops) ---
    def save_world(self, world: World) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO worlds (
                    id, theme, opening_line, art_style_directive, moderation_profile,
                    status, opens_at, closes_at, created_at, map_image_url, map_image_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    world.id,
                    world.theme,
                    world.opening_line,
                    world.art_style_directive,
                    world.moderation_profile,
                    world.status.value,
                    world.opens_at.isoformat(),
                    world.closes_at.isoformat() if world.closes_at else None,
                    world.created_at.isoformat(),
                    world.map_image_url,
                    world.map_image_version,
                ),
            )
            conn.commit()

    def save_world_map_image(self, world_id: str, url: str, version: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE worlds SET map_image_url = ?, map_image_version = ? WHERE id = ?",
                (url, version, world_id),
            )
            conn.commit()

    def get_world(self, world_id: str) -> World | None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._WORLD_COLS} FROM worlds WHERE id = ?", (world_id,)
            )
            row = cursor.fetchone()
            return self._row_to_world(row) if row else None

    def list_worlds(self) -> list[World]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._WORLD_COLS} FROM worlds ORDER BY opens_at DESC"
            )
            return [self._row_to_world(row) for row in cursor.fetchall()]

    def get_active_world(self) -> World | None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._WORLD_COLS} FROM worlds WHERE status = ? "
                "ORDER BY opens_at DESC LIMIT 1",
                (WorldStatus.ACTIVE.value,),
            )
            row = cursor.fetchone()
            return self._row_to_world(row) if row else None

    # --- Contributions (raw user submissions) ---
    def save_contribution(self, contribution: Contribution) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO contributions (
                    id, author_id, world_id, type, title, body, created_at, status, references_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    contribution.id,
                    contribution.author_id,
                    contribution.world_id,
                    contribution.type.value,
                    contribution.title,
                    contribution.body,
                    contribution.created_at.isoformat(),
                    contribution.status.value,
                    json.dumps(contribution.references),
                ),
            )
            conn.commit()

    def get_contribution(self, contribution_id: str) -> Contribution | None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, author_id, world_id, type, title, body, created_at, status, references_json
                FROM contributions WHERE id = ?
            """,
                (contribution_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Contribution(
                id=row[0],
                author_id=row[1],
                world_id=row[2],
                type=row[3],
                title=row[4],
                body=row[5],
                created_at=datetime.fromisoformat(row[6]),
                status=row[7],
                references=json.loads(row[8]),
            )

    # Column order shared by every canon SELECT, paired with _row_to_canon below.
    _CANON_COLS = (
        "id, type, title, body, contributor_id, derived_from_json, version, "
        "created_at, references_json, map_meta_json, world_id"
    )

    @staticmethod
    def _row_to_canon(row) -> CanonEntry:
        return CanonEntry(
            id=row[0],
            type=row[1],
            title=row[2],
            body=row[3],
            contributor_id=row[4],
            derived_from=json.loads(row[5]),
            version=row[6],
            created_at=datetime.fromisoformat(row[7]),
            references=json.loads(row[8]) if row[8] else [],
            map_meta=MapMeta(**json.loads(row[9])) if row[9] else None,
            world_id=row[10] or DEFAULT_WORLD_ID,
        )

    # --- Canon entries (accepted, versioned lore) ---
    def save_canon_entry(self, entry: CanonEntry) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO canon_entries (
                    id, type, title, body, contributor_id, derived_from_json, version,
                    created_at, references_json, map_meta_json, world_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.id,
                    entry.type.value,
                    entry.title,
                    entry.body,
                    entry.contributor_id,
                    json.dumps(entry.derived_from),
                    entry.version,
                    entry.created_at.isoformat(),
                    json.dumps(entry.references),
                    json.dumps(entry.map_meta.model_dump()) if entry.map_meta else None,
                    entry.world_id,
                ),
            )
            conn.commit()

    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._CANON_COLS} FROM canon_entries WHERE id = ?",
                (entry_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_canon(row)

    # --- Ledger (simulated points economy) ---
    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ledger_entries (
                    contribution_id, author_id, points_delta, reason, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (
                    entry.contribution_id,
                    entry.author_id,
                    entry.points_delta,
                    entry.reason,
                    entry.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_ledger_entries(self, author_id: str) -> list[LedgerEntry]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contribution_id, author_id, points_delta, reason, created_at
                FROM ledger_entries WHERE author_id = ?
            """,
                (author_id,),
            )
            rows = cursor.fetchall()
            return [
                LedgerEntry(
                    contribution_id=row[0],
                    author_id=row[1],
                    points_delta=row[2],
                    reason=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                )
                for row in rows
            ]

    def list_canon_entries(self, world_id: str | None = None) -> list[CanonEntry]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            if world_id is None:
                cursor.execute(f"SELECT {self._CANON_COLS} FROM canon_entries")
            else:
                cursor.execute(
                    f"SELECT {self._CANON_COLS} FROM canon_entries WHERE world_id = ?",
                    (world_id,),
                )
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    def list_canon_entries_by_type(
        self, entry_type: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            if world_id is None:
                cursor.execute(
                    f"SELECT {self._CANON_COLS} FROM canon_entries WHERE type = ?",
                    (entry_type,),
                )
            else:
                cursor.execute(
                    f"SELECT {self._CANON_COLS} FROM canon_entries "
                    "WHERE type = ? AND world_id = ?",
                    (entry_type, world_id),
                )
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    def search_canon_entries(
        self, query: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        # Simple keyword search using SQL LIKE
        words = [w for w in re.split(r"\W+", query) if len(w) > 3]
        if not words:
            return self.list_canon_entries(world_id)

        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            sql = f"SELECT {self._CANON_COLS} FROM canon_entries WHERE "
            conditions = []
            params = []
            for word in words:
                conditions.append("(title LIKE ? OR body LIKE ?)")
                params.extend([f"%{word}%", f"%{word}%"])
            sql += "(" + " OR ".join(conditions) + ")"
            if world_id is not None:
                sql += " AND world_id = ?"
                params.append(world_id)

            cursor.execute(sql, params)
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    # --- Discoveries (per-user fog-of-war) ---
    def save_discovery(self, user_id: str, canon_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discoveries (user_id, canon_id, created_at)
                VALUES (?, ?, ?)
            """,
                (user_id, canon_id, datetime.now(UTC).isoformat()),
            )
            conn.commit()

    def list_discoveries(self, user_id: str) -> set[str]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canon_id FROM discoveries WHERE user_id = ?", (user_id,)
            )
            return {row[0] for row in cursor.fetchall()}

    # --- Votes (one per user per storyline tree) ---
    def save_vote(self, vote: Vote) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO votes (
                    id, voter_id, world_id, tree_id, weight, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    vote.id,
                    vote.voter_id,
                    vote.world_id,
                    vote.tree_id,
                    vote.weight,
                    vote.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_votes_for_tree(self, tree_id: str) -> list[Vote]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, voter_id, world_id, tree_id, weight, created_at
                FROM votes WHERE tree_id = ?
            """,
                (tree_id,),
            )
            rows = cursor.fetchall()
            return [
                Vote(
                    id=row[0],
                    voter_id=row[1],
                    world_id=row[2],
                    tree_id=row[3],
                    weight=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                )
                for row in rows
            ]

    # --- Showcase jobs (async media generation) ---
    def save_showcase_job(self, job: ShowcaseJob) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO showcase_jobs (
                    id, world_id, tree_id, media_type, status, created_at, storyboard_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    job.id,
                    job.world_id,
                    job.tree_id,
                    job.media_type,
                    job.status.value,
                    job.created_at.isoformat(),
                    job.storyboard_json,
                ),
            )
            conn.commit()

    def get_showcase_job(self, job_id: str) -> ShowcaseJob | None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, world_id, tree_id, media_type, status, created_at, storyboard_json
                FROM showcase_jobs WHERE id = ?
            """,
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ShowcaseJob(
                id=row[0],
                world_id=row[1],
                tree_id=row[2],
                media_type=row[3],
                status=row[4],
                created_at=datetime.fromisoformat(row[5]),
                storyboard_json=row[6],
            )

    def list_showcase_jobs(self, world_id: str | None = None) -> list[ShowcaseJob]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            base = (
                "SELECT id, world_id, tree_id, media_type, status, created_at, "
                "storyboard_json FROM showcase_jobs"
            )
            if world_id is None:
                cursor.execute(base)
            else:
                cursor.execute(base + " WHERE world_id = ?", (world_id,))
            rows = cursor.fetchall()
            return [
                ShowcaseJob(
                    id=row[0],
                    world_id=row[1],
                    tree_id=row[2],
                    media_type=row[3],
                    status=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                    storyboard_json=row[6],
                )
                for row in rows
            ]

    def get_points_for_contribution(self, contribution_id: str) -> int:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT SUM(points_delta) FROM ledger_entries WHERE contribution_id = ?
            """,
                (contribution_id,),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    # --- Media assets (generated comics/reels/tiles) ---
    def save_media_asset(self, asset: MediaAsset) -> None:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO media_assets (
                    id, job_id, tree_id, kind, gcs_url, caption, hashtags_json, contributor_ids_json, created_at, node_id, world_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    asset.id,
                    asset.job_id,
                    asset.tree_id,
                    asset.kind,
                    asset.gcs_url,
                    asset.caption,
                    json.dumps(asset.hashtags),
                    json.dumps(asset.contributor_ids),
                    asset.created_at.isoformat(),
                    asset.node_id,
                    asset.world_id,
                ),
            )
            conn.commit()

    def list_media_assets(self) -> list[MediaAsset]:
        with closing(self._connect()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, job_id, tree_id, kind, gcs_url, caption, hashtags_json, contributor_ids_json, created_at, node_id, world_id
                FROM media_assets
            """
            )
            rows = cursor.fetchall()
            return [
                MediaAsset(
                    id=row[0],
                    job_id=row[1],
                    tree_id=row[2],
                    kind=row[3],
                    gcs_url=row[4],
                    caption=row[5],
                    hashtags=json.loads(row[6]),
                    contributor_ids=json.loads(row[7]),
                    created_at=datetime.fromisoformat(row[8]),
                    node_id=row[9] if len(row) > 9 else "",
                    world_id=row[10] if len(row) > 10 else "",
                )
                for row in rows
            ]


class FirestoreCanonStore(CanonStore):
    """Firestore implementation of the CanonStore interface."""

    def __init__(self, project: str | None = None, database: str | None = None):
        from google.cloud import firestore

        self.client = firestore.Client(project=project, database=database)
        # Seed the first active world if the collection is empty (parity with SQLite).
        self._ensure_seed_world()

    def _ensure_seed_world(self) -> None:
        existing = list(self.client.collection("worlds").limit(1).stream())
        if not existing:
            self.save_world(SEED_WORLD)

    @staticmethod
    def _doc_to_world(d: dict) -> World:
        return World(
            id=d["id"],
            theme=d["theme"],
            opening_line=d["opening_line"],
            art_style_directive=d.get("art_style_directive", ""),
            moderation_profile=d.get("moderation_profile", "default"),
            status=d["status"],
            opens_at=datetime.fromisoformat(d["opens_at"]),
            closes_at=datetime.fromisoformat(d["closes_at"])
            if d.get("closes_at")
            else None,
            created_at=datetime.fromisoformat(d["created_at"]),
            map_image_url=d.get("map_image_url"),
            map_image_version=d.get("map_image_version", 1),
        )

    # --- Worlds (themed seasonal drops) ---
    def save_world(self, world: World) -> None:
        data = {
            "id": world.id,
            "theme": world.theme,
            "opening_line": world.opening_line,
            "art_style_directive": world.art_style_directive,
            "moderation_profile": world.moderation_profile,
            "status": world.status.value,
            "opens_at": world.opens_at.isoformat(),
            "closes_at": world.closes_at.isoformat() if world.closes_at else None,
            "created_at": world.created_at.isoformat(),
            "map_image_url": world.map_image_url,
            "map_image_version": world.map_image_version,
        }
        self.client.collection("worlds").document(world.id).set(data)

    def save_world_map_image(self, world_id: str, url: str, version: int) -> None:
        self.client.collection("worlds").document(world_id).update(
            {
                "map_image_url": url,
                "map_image_version": version,
            }
        )

    def get_world(self, world_id: str) -> World | None:
        doc = self.client.collection("worlds").document(world_id).get()
        return self._doc_to_world(doc.to_dict()) if doc.exists else None

    def list_worlds(self) -> list[World]:
        docs = self.client.collection("worlds").stream()
        worlds = [self._doc_to_world(doc.to_dict()) for doc in docs]
        return sorted(worlds, key=lambda w: w.opens_at, reverse=True)

    def get_active_world(self) -> World | None:
        active = [w for w in self.list_worlds() if w.status == WorldStatus.ACTIVE]
        return active[0] if active else None

    # --- Contributions (raw user submissions) ---
    def save_contribution(self, contribution: Contribution) -> None:
        data = {
            "id": contribution.id,
            "author_id": contribution.author_id,
            "world_id": contribution.world_id,
            "type": contribution.type.value,
            "title": contribution.title,
            "body": contribution.body,
            "created_at": contribution.created_at.isoformat(),
            "status": contribution.status.value,
            "references": contribution.references,
        }
        self.client.collection("contributions").document(contribution.id).set(data)

    def get_contribution(self, contribution_id: str) -> Contribution | None:
        doc = self.client.collection("contributions").document(contribution_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return Contribution(
            id=d["id"],
            author_id=d["author_id"],
            world_id=d.get("world_id", DEFAULT_WORLD_ID),
            type=d["type"],
            title=d["title"],
            body=d["body"],
            created_at=datetime.fromisoformat(d["created_at"]),
            status=d["status"],
            references=d["references"],
        )

    @staticmethod
    def _doc_to_canon(d: dict) -> CanonEntry:
        map_meta = d.get("map_meta")
        return CanonEntry(
            id=d["id"],
            world_id=d.get("world_id", DEFAULT_WORLD_ID),
            type=d["type"],
            title=d["title"],
            body=d["body"],
            contributor_id=d["contributor_id"],
            derived_from=d["derived_from"],
            references=d.get("references", []),
            version=d["version"],
            created_at=datetime.fromisoformat(d["created_at"]),
            map_meta=MapMeta(**map_meta) if map_meta else None,
        )

    # --- Canon entries (accepted, versioned lore) ---
    def save_canon_entry(self, entry: CanonEntry) -> None:
        data = {
            "id": entry.id,
            "world_id": entry.world_id,
            "type": entry.type.value,
            "title": entry.title,
            "body": entry.body,
            "contributor_id": entry.contributor_id,
            "derived_from": entry.derived_from,
            "references": entry.references,
            "version": entry.version,
            "created_at": entry.created_at.isoformat(),
            "map_meta": entry.map_meta.model_dump() if entry.map_meta else None,
        }
        self.client.collection("canon_entries").document(entry.id).set(data)

    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        doc = self.client.collection("canon_entries").document(entry_id).get()
        if not doc.exists:
            return None
        return self._doc_to_canon(doc.to_dict())

    # --- Ledger (simulated points economy) ---
    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        data = {
            "contribution_id": entry.contribution_id,
            "author_id": entry.author_id,
            "points_delta": entry.points_delta,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat(),
        }
        self.client.collection("ledger_entries").add(data)

    def get_ledger_entries(self, author_id: str) -> list[LedgerEntry]:
        docs = (
            self.client.collection("ledger_entries")
            .where("author_id", "==", author_id)
            .stream()
        )
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(
                LedgerEntry(
                    contribution_id=d["contribution_id"],
                    author_id=d["author_id"],
                    points_delta=d["points_delta"],
                    reason=d["reason"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                )
            )
        return results

    def list_canon_entries(self, world_id: str | None = None) -> list[CanonEntry]:
        col = self.client.collection("canon_entries")
        query = col.where("world_id", "==", world_id) if world_id is not None else col
        return [self._doc_to_canon(doc.to_dict()) for doc in query.stream()]

    def list_canon_entries_by_type(
        self, entry_type: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        query = self.client.collection("canon_entries").where("type", "==", entry_type)
        if world_id is not None:
            query = query.where("world_id", "==", world_id)
        return [self._doc_to_canon(doc.to_dict()) for doc in query.stream()]

    # --- Discoveries (per-user fog-of-war) ---
    def save_discovery(self, user_id: str, canon_id: str) -> None:
        data = {
            "user_id": user_id,
            "canon_id": canon_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.client.collection("discoveries").document(f"{user_id}__{canon_id}").set(
            data
        )

    def list_discoveries(self, user_id: str) -> set[str]:
        docs = (
            self.client.collection("discoveries")
            .where("user_id", "==", user_id)
            .stream()
        )
        return {doc.to_dict()["canon_id"] for doc in docs}

    def search_canon_entries(
        self, query: str, world_id: str | None = None
    ) -> list[CanonEntry]:
        words = [w.lower() for w in re.split(r"\W+", query) if len(w) > 3]
        all_entries = self.list_canon_entries(world_id)
        if not words:
            return all_entries

        results = []
        for entry in all_entries:
            match = False
            for word in words:
                if word in entry.title.lower() or word in entry.body.lower():
                    match = True
                    break
            if match:
                results.append(entry)
        return results

    # --- Votes (one per user per storyline tree) ---
    def save_vote(self, vote: Vote) -> None:
        data = {
            "id": vote.id,
            "voter_id": vote.voter_id,
            "world_id": vote.world_id,
            "tree_id": vote.tree_id,
            "weight": vote.weight,
            "created_at": vote.created_at.isoformat(),
        }
        self.client.collection("votes").document(vote.id).set(data)

    def get_votes_for_tree(self, tree_id: str) -> list[Vote]:
        docs = self.client.collection("votes").where("tree_id", "==", tree_id).stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(
                Vote(
                    id=d["id"],
                    voter_id=d["voter_id"],
                    world_id=d.get("world_id", DEFAULT_WORLD_ID),
                    tree_id=d["tree_id"],
                    weight=d["weight"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                )
            )
        return results

    # --- Showcase jobs (async media generation) ---
    def save_showcase_job(self, job: ShowcaseJob) -> None:
        data = {
            "id": job.id,
            "world_id": job.world_id,
            "tree_id": job.tree_id,
            "media_type": job.media_type,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "storyboard_json": job.storyboard_json,
        }
        self.client.collection("showcase_jobs").document(job.id).set(data)

    def get_showcase_job(self, job_id: str) -> ShowcaseJob | None:
        doc = self.client.collection("showcase_jobs").document(job_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return ShowcaseJob(
            id=d["id"],
            world_id=d.get("world_id", DEFAULT_WORLD_ID),
            tree_id=d["tree_id"],
            media_type=d["media_type"],
            status=d["status"],
            created_at=datetime.fromisoformat(d["created_at"]),
            storyboard_json=d.get("storyboard_json"),
        )

    def list_showcase_jobs(self, world_id: str | None = None) -> list[ShowcaseJob]:
        col = self.client.collection("showcase_jobs")
        query = col.where("world_id", "==", world_id) if world_id is not None else col
        results = []
        for doc in query.stream():
            d = doc.to_dict()
            results.append(
                ShowcaseJob(
                    id=d["id"],
                    world_id=d.get("world_id", DEFAULT_WORLD_ID),
                    tree_id=d["tree_id"],
                    media_type=d["media_type"],
                    status=d["status"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                    storyboard_json=d.get("storyboard_json"),
                )
            )
        return results

    def get_points_for_contribution(self, contribution_id: str) -> int:
        docs = (
            self.client.collection("ledger_entries")
            .where("contribution_id", "==", contribution_id)
            .stream()
        )
        total = 0
        for doc in docs:
            d = doc.to_dict()
            total += int(d.get("points_delta", 0))
        return total

    # --- Media assets (generated comics/reels/tiles) ---
    def save_media_asset(self, asset: MediaAsset) -> None:
        data = {
            "id": asset.id,
            "job_id": asset.job_id,
            "tree_id": asset.tree_id,
            "kind": asset.kind,
            "gcs_url": asset.gcs_url,
            "caption": asset.caption,
            "hashtags": asset.hashtags,
            "contributor_ids": asset.contributor_ids,
            "created_at": asset.created_at.isoformat(),
            "node_id": asset.node_id,
            "world_id": asset.world_id,
        }
        self.client.collection("media_assets").document(asset.id).set(data)

    def list_media_assets(self) -> list[MediaAsset]:
        docs = self.client.collection("media_assets").stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(
                MediaAsset(
                    id=d["id"],
                    job_id=d["job_id"],
                    tree_id=d["tree_id"],
                    kind=d["kind"],
                    gcs_url=d["gcs_url"],
                    caption=d["caption"],
                    hashtags=d.get("hashtags", []),
                    contributor_ids=d.get("contributor_ids", []),
                    created_at=datetime.fromisoformat(d["created_at"]),
                    node_id=d.get("node_id", ""),
                    world_id=d.get("world_id", ""),
                )
            )
        return results


@lru_cache(maxsize=1)
def get_store() -> CanonStore:
    """Returns either a Firestore or SQLite CanonStore depending on the environment.

    Firestore is used in the cloud (``K_SERVICE`` set on Cloud Run) or when explicitly
    requested (``USE_FIRESTORE=True``). Using Vertex AI for the LLM
    (``GOOGLE_GENAI_USE_VERTEXAI=True``) does NOT force Firestore, so local dev can run
    Vertex models against the local SQLite ``world.db``.

    Cached: on Firestore this avoids rebuilding the client (and re-running the
    seed-world check) on every call. Env-based selection is read once per process.
    """
    import os

    if (
        os.environ.get("USE_FIRESTORE") == "True"
        or os.environ.get("K_SERVICE") is not None
    ):
        return FirestoreCanonStore()
    else:
        return SQLiteCanonStore()

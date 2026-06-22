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

import json
import re
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.core.types import (
    CanonEntry,
    Contribution,
    LedgerEntry,
    MapMeta,
    MediaAsset,
    ShowcaseJob,
    Vote,
)


class CanonStore(ABC):
    """Interface for world-engine persistence layer."""

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
    def list_canon_entries(self) -> list[CanonEntry]:
        """List all canon entries in the store."""
        pass

    @abstractmethod
    def list_canon_entries_by_type(self, entry_type: str) -> list[CanonEntry]:
        """List canon entries filtered by type (powers the Map / codex views)."""
        pass

    @abstractmethod
    def search_canon_entries(self, query: str) -> list[CanonEntry]:
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
    def list_showcase_jobs(self) -> list[ShowcaseJob]:
        """List all showcase jobs."""
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

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Contributions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contributions (
                    id TEXT PRIMARY KEY,
                    author_id TEXT NOT NULL,
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
            # Self-healing migration: add Living-World columns to pre-existing canon tables.
            cursor.execute("PRAGMA table_info(canon_entries)")
            canon_columns = [col[1] for col in cursor.fetchall()]
            if "references_json" not in canon_columns:
                cursor.execute("ALTER TABLE canon_entries ADD COLUMN references_json TEXT")
            if "map_meta_json" not in canon_columns:
                cursor.execute("ALTER TABLE canon_entries ADD COLUMN map_meta_json TEXT")
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
                    tree_id TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Showcase jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS showcase_jobs (
                    id TEXT PRIMARY KEY,
                    tree_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    storyboard_json TEXT
                )
            """)
            # Check and add storyboard_json to showcase_jobs if missing (self-healing migration)
            cursor.execute("PRAGMA table_info(showcase_jobs)")
            columns = [col[1] for col in cursor.fetchall()]
            if "storyboard_json" not in columns:
                cursor.execute(
                    "ALTER TABLE showcase_jobs ADD COLUMN storyboard_json TEXT"
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
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_contribution(self, contribution: Contribution) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO contributions (
                    id, author_id, type, title, body, created_at, status, references_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    contribution.id,
                    contribution.author_id,
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, author_id, type, title, body, created_at, status, references_json
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
                type=row[2],
                title=row[3],
                body=row[4],
                created_at=datetime.fromisoformat(row[5]),
                status=row[6],
                references=json.loads(row[7]),
            )

    # Column order shared by every canon SELECT, paired with _row_to_canon below.
    _CANON_COLS = (
        "id, type, title, body, contributor_id, derived_from_json, version, "
        "created_at, references_json, map_meta_json"
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
        )

    def save_canon_entry(self, entry: CanonEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO canon_entries (
                    id, type, title, body, contributor_id, derived_from_json, version,
                    created_at, references_json, map_meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._CANON_COLS} FROM canon_entries WHERE id = ?",
                (entry_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_canon(row)

    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
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

    def list_canon_entries(self) -> list[CanonEntry]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {self._CANON_COLS} FROM canon_entries")
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    def list_canon_entries_by_type(self, entry_type: str) -> list[CanonEntry]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {self._CANON_COLS} FROM canon_entries WHERE type = ?",
                (entry_type,),
            )
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    def search_canon_entries(self, query: str) -> list[CanonEntry]:
        # Simple keyword search using SQL LIKE
        words = [w for w in re.split(r"\W+", query) if len(w) > 3]
        if not words:
            return self.list_canon_entries()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            sql = f"SELECT {self._CANON_COLS} FROM canon_entries WHERE "
            conditions = []
            params = []
            for word in words:
                conditions.append("(title LIKE ? OR body LIKE ?)")
                params.extend([f"%{word}%", f"%{word}%"])
            sql += " OR ".join(conditions)

            cursor.execute(sql, params)
            return [self._row_to_canon(row) for row in cursor.fetchall()]

    def save_discovery(self, user_id: str, canon_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discoveries (user_id, canon_id, created_at)
                VALUES (?, ?, ?)
            """,
                (user_id, canon_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def list_discoveries(self, user_id: str) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canon_id FROM discoveries WHERE user_id = ?", (user_id,)
            )
            return {row[0] for row in cursor.fetchall()}

    def save_vote(self, vote: Vote) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO votes (
                    id, voter_id, tree_id, weight, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (
                    vote.id,
                    vote.voter_id,
                    vote.tree_id,
                    vote.weight,
                    vote.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_votes_for_tree(self, tree_id: str) -> list[Vote]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, voter_id, tree_id, weight, created_at
                FROM votes WHERE tree_id = ?
            """,
                (tree_id,),
            )
            rows = cursor.fetchall()
            return [
                Vote(
                    id=row[0],
                    voter_id=row[1],
                    tree_id=row[2],
                    weight=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                )
                for row in rows
            ]

    def save_showcase_job(self, job: ShowcaseJob) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO showcase_jobs (
                    id, tree_id, media_type, status, created_at, storyboard_json
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    job.id,
                    job.tree_id,
                    job.media_type,
                    job.status.value,
                    job.created_at.isoformat(),
                    job.storyboard_json,
                ),
            )
            conn.commit()

    def get_showcase_job(self, job_id: str) -> ShowcaseJob | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tree_id, media_type, status, created_at, storyboard_json
                FROM showcase_jobs WHERE id = ?
            """,
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ShowcaseJob(
                id=row[0],
                tree_id=row[1],
                media_type=row[2],
                status=row[3],
                created_at=datetime.fromisoformat(row[4]),
                storyboard_json=row[5],
            )

    def list_showcase_jobs(self) -> list[ShowcaseJob]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tree_id, media_type, status, created_at, storyboard_json
                FROM showcase_jobs
            """
            )
            rows = cursor.fetchall()
            return [
                ShowcaseJob(
                    id=row[0],
                    tree_id=row[1],
                    media_type=row[2],
                    status=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    storyboard_json=row[5],
                )
                for row in rows
            ]

    def get_points_for_contribution(self, contribution_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT SUM(points_delta) FROM ledger_entries WHERE contribution_id = ?
            """,
                (contribution_id,),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    def save_media_asset(self, asset: MediaAsset) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO media_assets (
                    id, job_id, tree_id, kind, gcs_url, caption, hashtags_json, contributor_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

    def list_media_assets(self) -> list[MediaAsset]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, job_id, tree_id, kind, gcs_url, caption, hashtags_json, contributor_ids_json, created_at
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
                )
                for row in rows
            ]


class FirestoreCanonStore(CanonStore):
    """Firestore implementation of the CanonStore interface."""

    def __init__(self, project: str | None = None, database: str | None = None):
        from google.cloud import firestore

        self.client = firestore.Client(project=project, database=database)

    def save_contribution(self, contribution: Contribution) -> None:
        data = {
            "id": contribution.id,
            "author_id": contribution.author_id,
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

    def save_canon_entry(self, entry: CanonEntry) -> None:
        data = {
            "id": entry.id,
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

    def list_canon_entries(self) -> list[CanonEntry]:
        docs = self.client.collection("canon_entries").stream()
        return [self._doc_to_canon(doc.to_dict()) for doc in docs]

    def list_canon_entries_by_type(self, entry_type: str) -> list[CanonEntry]:
        docs = (
            self.client.collection("canon_entries")
            .where("type", "==", entry_type)
            .stream()
        )
        return [self._doc_to_canon(doc.to_dict()) for doc in docs]

    def save_discovery(self, user_id: str, canon_id: str) -> None:
        data = {
            "user_id": user_id,
            "canon_id": canon_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.collection("discoveries").document(f"{user_id}__{canon_id}").set(data)

    def list_discoveries(self, user_id: str) -> set[str]:
        docs = (
            self.client.collection("discoveries")
            .where("user_id", "==", user_id)
            .stream()
        )
        return {doc.to_dict()["canon_id"] for doc in docs}

    def search_canon_entries(self, query: str) -> list[CanonEntry]:
        words = [w.lower() for w in re.split(r"\W+", query) if len(w) > 3]
        all_entries = self.list_canon_entries()
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

    def save_vote(self, vote: Vote) -> None:
        data = {
            "id": vote.id,
            "voter_id": vote.voter_id,
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
                    tree_id=d["tree_id"],
                    weight=d["weight"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                )
            )
        return results

    def save_showcase_job(self, job: ShowcaseJob) -> None:
        data = {
            "id": job.id,
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
            tree_id=d["tree_id"],
            media_type=d["media_type"],
            status=d["status"],
            created_at=datetime.fromisoformat(d["created_at"]),
            storyboard_json=d.get("storyboard_json"),
        )

    def list_showcase_jobs(self) -> list[ShowcaseJob]:
        docs = self.client.collection("showcase_jobs").stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(
                ShowcaseJob(
                    id=d["id"],
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
                )
            )
        return results


def get_store() -> CanonStore:
    """Returns either a Firestore or SQLite CanonStore depending on the environment."""
    import os

    if (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "True"
        or os.environ.get("USE_FIRESTORE") == "True"
        or os.environ.get("K_SERVICE") is not None
    ):
        return FirestoreCanonStore()
    else:
        return SQLiteCanonStore()

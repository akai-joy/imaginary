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
from datetime import datetime

from app.core.types import CanonEntry, Contribution, LedgerEntry, ShowcaseJob, Vote


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
    def search_canon_entries(self, query: str) -> list[CanonEntry]:
        """Search canon entries using text match keywords."""
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
                    created_at TEXT NOT NULL
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

    def save_canon_entry(self, entry: CanonEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO canon_entries (
                    id, type, title, body, contributor_id, derived_from_json, version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, type, title, body, contributor_id, derived_from_json, version, created_at
                FROM canon_entries WHERE id = ?
            """,
                (entry_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return CanonEntry(
                id=row[0],
                type=row[1],
                title=row[2],
                body=row[3],
                contributor_id=row[4],
                derived_from=json.loads(row[5]),
                version=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )

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
            cursor.execute(
                """
                SELECT id, type, title, body, contributor_id, derived_from_json, version, created_at
                FROM canon_entries
            """
            )
            rows = cursor.fetchall()
            return [
                CanonEntry(
                    id=row[0],
                    type=row[1],
                    title=row[2],
                    body=row[3],
                    contributor_id=row[4],
                    derived_from=json.loads(row[5]),
                    version=row[6],
                    created_at=datetime.fromisoformat(row[7]),
                )
                for row in rows
            ]

    def search_canon_entries(self, query: str) -> list[CanonEntry]:
        # Simple keyword search using SQL LIKE
        words = [w for w in re.split(r"\W+", query) if len(w) > 3]
        if not words:
            return self.list_canon_entries()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            sql = (
                "SELECT id, type, title, body, contributor_id, derived_from_json, version, created_at "
                "FROM canon_entries WHERE "
            )
            conditions = []
            params = []
            for word in words:
                conditions.append("(title LIKE ? OR body LIKE ?)")
                params.extend([f"%{word}%", f"%{word}%"])
            sql += " OR ".join(conditions)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [
                CanonEntry(
                    id=row[0],
                    type=row[1],
                    title=row[2],
                    body=row[3],
                    contributor_id=row[4],
                    derived_from=json.loads(row[5]),
                    version=row[6],
                    created_at=datetime.fromisoformat(row[7]),
                )
                for row in rows
            ]

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
                    id, tree_id, media_type, status, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (
                    job.id,
                    job.tree_id,
                    job.media_type,
                    job.status.value,
                    job.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_showcase_job(self, job_id: str) -> ShowcaseJob | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tree_id, media_type, status, created_at
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
            )

    def list_showcase_jobs(self) -> list[ShowcaseJob]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tree_id, media_type, status, created_at
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
                )
                for row in rows
            ]

    def get_points_for_contribution(self, contribution_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT points_delta FROM ledger_entries WHERE contribution_id = ?
            """,
                (contribution_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0


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

    def save_canon_entry(self, entry: CanonEntry) -> None:
        data = {
            "id": entry.id,
            "type": entry.type.value,
            "title": entry.title,
            "body": entry.body,
            "contributor_id": entry.contributor_id,
            "derived_from": entry.derived_from,
            "version": entry.version,
            "created_at": entry.created_at.isoformat(),
        }
        self.client.collection("canon_entries").document(entry.id).set(data)

    def get_canon_entry(self, entry_id: str) -> CanonEntry | None:
        doc = self.client.collection("canon_entries").document(entry_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        return CanonEntry(
            id=d["id"],
            type=d["type"],
            title=d["title"],
            body=d["body"],
            contributor_id=d["contributor_id"],
            derived_from=d["derived_from"],
            version=d["version"],
            created_at=datetime.fromisoformat(d["created_at"]),
        )

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
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(
                CanonEntry(
                    id=d["id"],
                    type=d["type"],
                    title=d["title"],
                    body=d["body"],
                    contributor_id=d["contributor_id"],
                    derived_from=d["derived_from"],
                    version=d["version"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                )
            )
        return results

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
        docs = (
            self.client.collection("votes")
            .where("tree_id", "==", tree_id)
            .stream()
        )
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
                )
            )
        return results

    def get_points_for_contribution(self, contribution_id: str) -> int:
        docs = (
            self.client.collection("ledger_entries")
            .where("contribution_id", "==", contribution_id)
            .limit(1)
            .stream()
        )
        for doc in docs:
            d = doc.to_dict()
            return int(d.get("points_delta", 0))
        return 0


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

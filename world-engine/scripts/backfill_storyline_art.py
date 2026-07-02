"""Seed QUEUED comic ShowcaseJobs for named storyline trees (idempotent)."""

import sys
import uuid
from datetime import UTC, datetime

from app.core.store import get_store
from app.core.types import ShowcaseJob, ShowcaseJobStatus

TARGET_TREE_IDS = ["canon_tre_lantern", "canon_lamp"]  # override via CLI args


def main(tree_ids):
    store = get_store()
    existing = {j.tree_id for j in store.list_showcase_jobs()}
    for tid in tree_ids:
        if tid in existing:
            print(f"skip {tid} (job already exists)")
            continue
        if not store.get_canon_entry(tid):
            print(f"WARN {tid} not found in store; skipping")
            continue
        job = ShowcaseJob(
            id=f"job_{uuid.uuid4()}",
            tree_id=tid,
            media_type="comic",  # NEVER "reel" — keep cost/latency down
            status=ShowcaseJobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        store.save_showcase_job(job)
        print(f"queued comic job {job.id} for {tid}")


if __name__ == "__main__":
    main(sys.argv[1:] or TARGET_TREE_IDS)

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job


def db_connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            fingerprint TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            title TEXT,
            organisation TEXT,
            location TEXT,
            url TEXT,
            source TEXT,
            score INTEGER,
            payload_json TEXT
        )
        """
    )
    return conn


def already_seen(conn: sqlite3.Connection, fingerprint: str) -> bool:
    row = conn.execute("SELECT 1 FROM seen_jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
    return row is not None


from datetime import datetime, timezone


def persist_job(conn: sqlite3.Connection, job: Job) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = job.to_json()
    conn.execute(
        """
        INSERT INTO seen_jobs
        (fingerprint, first_seen, last_seen, title, organisation, location, url, source, score, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            last_seen=excluded.last_seen,
            score=excluded.score,
            payload_json=excluded.payload_json
        """,
        (
            job.fingerprint,
            now,
            now,
            job.title,
            job.organisation,
            job.location,
            job.url,
            job.source,
            job.score,
            payload,
        ),
    )

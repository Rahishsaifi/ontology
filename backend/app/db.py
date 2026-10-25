"""SQLite job and sync-state store."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.jobs import JobError, JobRecord, SyncState


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    mode TEXT,
                    entity_sets TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    progress_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    batch_no INTEGER,
                    entity_set TEXT,
                    source_key TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_state (
                    entity_set TEXT PRIMARY KEY,
                    last_success_at TEXT,
                    watermark TEXT,
                    catalog_hash TEXT,
                    status TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def create_job(self, job: JobRecord) -> JobRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, status, dry_run, mode, entity_sets, created_at,
                    started_at, finished_at, progress_json, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.job_type,
                    job.status,
                    int(job.dry_run),
                    job.mode,
                    json.dumps(job.entity_sets),
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    json.dumps(job.progress),
                    json.dumps(job.summary),
                ),
            )
            self._conn.commit()
        return job

    def update_job(self, job_id: str, **fields) -> None:
        mapping = {
            "status": "status",
            "started_at": "started_at",
            "finished_at": "finished_at",
            "progress": "progress_json",
            "summary": "summary_json",
        }
        sets = []
        values = []
        for key, value in fields.items():
            column = mapping[key]
            if key in {"progress", "summary"}:
                value = json.dumps(value)
            sets.append(f"{column} = ?")
            values.append(value)
        values.append(job_id)
        with self._lock:
            self._conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", values)
            self._conn.commit()

    def add_error(self, job_id: str, *, batch_no: int | None, entity_set: str | None, source_key: str | None, message: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO job_errors (job_id, batch_no, entity_set, source_key, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, batch_no, entity_set, source_key, message[:500], _now()),
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            errors = self._conn.execute(
                "SELECT * FROM job_errors WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return _job_from_row(row, errors)

    def list_jobs(self, limit: int = 20, job_type: str | None = None) -> list[JobRecord]:
        with self._lock:
            if job_type:
                rows = self._conn.execute(
                    "SELECT * FROM jobs WHERE job_type = ? ORDER BY created_at DESC LIMIT ?",
                    (job_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            result = []
            for row in rows:
                errors = self._conn.execute(
                    "SELECT * FROM job_errors WHERE job_id = ? ORDER BY id LIMIT 20",
                    (row["id"],),
                ).fetchall()
                result.append(_job_from_row(row, errors))
        return result

    def get_sync_state(self, entity_set: str) -> SyncState | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sync_state WHERE entity_set = ?", (entity_set,)).fetchone()
        if row is None:
            return None
        return SyncState(
            entity_set=row["entity_set"],
            last_success_at=row["last_success_at"],
            watermark=row["watermark"],
            catalog_hash=row["catalog_hash"],
            status=row["status"],
        )

    def upsert_sync_state(self, state: SyncState) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sync_state (entity_set, last_success_at, watermark, catalog_hash, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_set) DO UPDATE SET
                    last_success_at = excluded.last_success_at,
                    watermark = excluded.watermark,
                    catalog_hash = excluded.catalog_hash,
                    status = excluded.status
                """,
                (state.entity_set, state.last_success_at, state.watermark, state.catalog_hash, state.status),
            )
            self._conn.commit()

    def list_sync_states(self) -> list[SyncState]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM sync_state ORDER BY entity_set").fetchall()
        return [
            SyncState(
                entity_set=row["entity_set"],
                last_success_at=row["last_success_at"],
                watermark=row["watermark"],
                catalog_hash=row["catalog_hash"],
                status=row["status"],
            )
            for row in rows
        ]


def _job_from_row(row, errors) -> JobRecord:
    return JobRecord(
        id=row["id"],
        job_type=row["job_type"],
        status=row["status"],
        dry_run=bool(row["dry_run"]),
        mode=row["mode"],
        entity_sets=json.loads(row["entity_sets"]),
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        progress=json.loads(row["progress_json"]),
        summary=json.loads(row["summary_json"]),
        errors=[
            JobError(
                batch_no=error["batch_no"],
                entity_set=error["entity_set"],
                source_key=error["source_key"],
                message=error["message"],
                created_at=error["created_at"],
            )
            for error in errors
        ],
    )

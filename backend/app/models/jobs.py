"""Job and synchronization records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobError(BaseModel):
    batch_no: int | None = None
    entity_set: str | None = None
    source_key: str | None = None
    message: str
    created_at: str


class JobRecord(BaseModel):
    id: str
    job_type: str
    status: str
    dry_run: bool = False
    mode: str | None = None
    entity_sets: list[str] = Field(default_factory=list)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    progress: dict = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    errors: list[JobError] = Field(default_factory=list)


class SyncState(BaseModel):
    entity_set: str
    last_success_at: str | None = None
    watermark: str | None = None
    catalog_hash: str | None = None
    status: str

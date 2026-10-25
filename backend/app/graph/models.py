"""Graph row shapes shared by the memory and Neo4j stores."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
RESERVED = {
    "identity",
    "sourceSystem",
    "entityType",
    "sourceKey",
    "lastSyncedAt",
    "canonicalClass",
    "displayLabel",
    "effectiveStart",
    "effectiveEnd",
    "sourceModifiedAt",
    "provenance",
}


class EntityUpsert(BaseModel):
    identity: str
    source_system: str
    entity_type: str
    source_key: str
    last_synced_at: str
    canonical_class: str | None = None
    display_label: str
    effective_start: str | None = None
    effective_end: str | None = None
    source_modified_at: str | None = None
    provenance: str = "successfactors"
    properties: dict = Field(default_factory=dict)


class RelationshipUpsert(BaseModel):
    relationship_type: str
    source_identity: str
    target_identity: str
    mapping_id: str
    navigation_property: str
    synced_at: str


def sanitize_properties(properties: dict) -> dict:
    cleaned: dict = {}
    for key, value in properties.items():
        if value is None or key in RESERVED or not SAFE_NAME.match(str(key)):
            continue
        if isinstance(value, bool) or isinstance(value, (int, float, str)):
            if isinstance(value, str) and len(value) > 8000:
                value = value[:8000]
            cleaned[str(key)] = value
        else:
            cleaned[str(key)] = json.dumps(value, default=str)[:8000]
    return cleaned

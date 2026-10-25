"""Ontology draft and reviewed mapping documents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OntologyProperty(BaseModel):
    property_id: str
    natural_key: str
    source_property: str
    canonical_property: str | None = None
    data_type: str
    nullable: bool
    sensitive: bool = False
    mapping_status: str
    inference_note: str | None = None
    signature: str


class OntologyClass(BaseModel):
    class_id: str
    natural_key: str
    source_entity_type: str
    source_entity_set: str | None = None
    canonical_name: str | None = None
    namespace: str
    identity_fields: list[str] = Field(default_factory=list)
    key_defined: bool
    exposed: bool
    status: str
    mapping_confidence: float | None = None
    inference_note: str | None = None
    effective_dated: bool = False
    effective_start_field: str | None = None
    effective_end_field: str | None = None
    effective_date_in_key: bool = False
    effective_dating_rule: str | None = None
    effective_identity_field: str | None = None
    signature: str
    properties: list[OntologyProperty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OntologyRelationship(BaseModel):
    relationship_id: str
    natural_key: str
    source_entity: str
    source_entity_set: str | None = None
    navigation_property: str
    target_entity: str | None = None
    target_entity_set: str | None = None
    source_role: str
    target_role: str
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None
    relationship_semantics: str | None = None
    relationship_type: str | None = None
    mapping_status: str
    mapping_confidence: float | None = None
    key_resolution: str = "unresolved"
    source_key_fields: list[str] = Field(default_factory=list)
    target_key_fields: list[str] = Field(default_factory=list)
    inference_note: str | None = None
    unresolved_reason: str | None = None
    ambiguous: bool = False
    signature: str


class OntologyDocument(BaseModel):
    ontology_id: str
    name: str
    version: str
    mapping_version: int = 0
    source_system: str
    generated_at: str
    catalog_hash: str
    origin: str
    classes: list[OntologyClass]
    relationships: list[OntologyRelationship]
    concept_coverage: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ReviewRecord(BaseModel):
    kind: str
    natural_key: str
    source_entity_type: str
    source_property: str | None = None
    navigation_property: str | None = None
    status: str
    canonical_name: str | None = None
    relationship_type: str | None = None
    source_key_fields: list[str] = Field(default_factory=list)
    target_key_fields: list[str] = Field(default_factory=list)
    effective_dating_rule: str | None = None
    effective_identity_field: str | None = None
    signature: str = ""
    note: str | None = None
    updated_at: str = ""


class ReviewFile(BaseModel):
    version: int = 1
    mapping_version: int = 0
    source_system: str
    mappings: list[ReviewRecord] = Field(default_factory=list)

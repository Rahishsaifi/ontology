"""Generate a reviewable ontology. Semantic guesses are never approved."""

from __future__ import annotations

import hashlib
import json

from app.models.catalog import SchemaCatalog
from app.models.ontology import (
    OntologyClass,
    OntologyDocument,
    OntologyProperty,
    OntologyRelationship,
    ReviewRecord,
)
from app.ontology.canonical import (
    EFFECTIVE_END_FIELDS,
    EFFECTIVE_START_FIELDS,
    NAV_SEMANTICS,
    PRIMARY_ENTITY_CANDIDATES,
    REQUIRED_CONCEPTS,
    USER_ACCOUNT_NOTE,
    normalize_nav_name,
)


def _sig(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sensitive(name: str, patterns: list[str]) -> bool:
    lowered = name.lower()
    return any(pattern and pattern in lowered for pattern in patterns)


def generate_ontology(
    catalog: SchemaCatalog,
    reviews: list[ReviewRecord] | None = None,
    *,
    sensitive_patterns: list[str] | None = None,
) -> OntologyDocument:
    patterns = [item.lower() for item in (sensitive_patterns or [])]
    review_index = {item.natural_key: item for item in (reviews or []) if item.natural_key}
    classes = [_class_for(entity, patterns, review_index) for entity in catalog.entity_types]
    relationships: list[OntologyRelationship] = []
    for entity in catalog.entity_types:
        entity_set = entity.entity_set_names[0] if entity.entity_set_names else None
        for nav in entity.navigation_properties:
            relationships.append(_relationship_for(entity, entity_set, nav, review_index))
    classes.sort(key=lambda item: item.source_entity_type)
    relationships.sort(key=lambda item: item.natural_key)
    coverage = {concept: "unmatched" for concept in REQUIRED_CONCEPTS}
    coverage["Manager"] = "relationship_only"
    for item in classes:
        if item.canonical_name and item.canonical_name in coverage and item.canonical_name != "Manager":
            coverage[item.canonical_name] = item.source_entity_type
    return OntologyDocument(
        ontology_id=catalog.metadata_hash[:16] or "draft",
        name="Core HR ontology",
        version="0.1.0",
        mapping_version=0,
        source_system=catalog.source_system,
        generated_at=catalog.generated_at,
        catalog_hash=catalog.metadata_hash,
        origin=catalog.origin,
        classes=classes,
        relationships=relationships,
        concept_coverage=coverage,
        warnings=list(catalog.warnings),
    )


def apply_mapping_version(document: OntologyDocument, version: int) -> OntologyDocument:
    document.mapping_version = int(version or 0)
    return document


def _class_for(entity, patterns: list[str], reviews: dict[str, ReviewRecord]) -> OntologyClass:
    natural_key = f"class|{entity.qualified_name}"
    start = next((name for name in EFFECTIVE_START_FIELDS if name in entity.property_map()), None)
    end = next((name for name in EFFECTIVE_END_FIELDS if name in entity.property_map()), None)
    in_key = bool(start and start in entity.key.property_names)
    if entity.name == "User":
        canonical = None
        status = "discovered"
        confidence = None
        note = USER_ACCOUNT_NOTE
    elif entity.name in PRIMARY_ENTITY_CANDIDATES:
        canonical, confidence, note = PRIMARY_ENTITY_CANDIDATES[entity.name]
        status = "review_required"
    else:
        canonical = None
        status = "discovered"
        confidence = None
        note = "No canonical concept was inferred. Review this entity before using it."
    signature = _sig(
        {
            "entity": entity.qualified_name,
            "key": list(entity.key.property_names),
            "properties": [(prop.name, prop.edm_type, prop.nullable) for prop in entity.properties],
        }
    )
    properties = [_property_for(entity.qualified_name, prop, patterns, reviews) for prop in entity.properties]
    item = OntologyClass(
        class_id=natural_key,
        natural_key=natural_key,
        source_entity_type=entity.qualified_name,
        source_entity_set=entity.entity_set_names[0] if entity.entity_set_names else None,
        canonical_name=canonical,
        namespace=entity.namespace,
        identity_fields=list(entity.key.property_names),
        key_defined=entity.key_defined,
        exposed=entity.exposed,
        status=status,
        mapping_confidence=confidence,
        inference_note=note,
        effective_dated=start is not None,
        effective_start_field=start,
        effective_end_field=end,
        effective_date_in_key=in_key,
        effective_dating_rule="key_includes_effective_date" if in_key else None,
        signature=signature,
        properties=properties,
        warnings=[] if entity.key_defined else ["This entity type has no key and cannot be ingested."],
    )
    return _apply_class(item, reviews.get(natural_key))


def _property_for(qualified: str, prop, patterns: list[str], reviews: dict[str, ReviewRecord]) -> OntologyProperty:
    natural_key = f"property|{qualified}|{prop.name}"
    sensitive = _sensitive(prop.name, patterns)
    signature = _sig({"entity": qualified, "property": prop.name, "type": prop.edm_type, "nullable": prop.nullable})
    item = OntologyProperty(
        property_id=natural_key,
        natural_key=natural_key,
        source_property=prop.name,
        data_type=prop.edm_type,
        nullable=prop.nullable,
        sensitive=sensitive,
        mapping_status="review_required" if sensitive else "discovered",
        inference_note="Sensitive property. Keep it out of the graph unless a reviewer explicitly includes it."
        if sensitive
        else "Property discovered from EDMX.",
        signature=signature,
    )
    return _apply_property(item, reviews.get(natural_key))


def _relationship_for(entity, entity_set: str | None, nav, reviews: dict[str, ReviewRecord]) -> OntologyRelationship:
    natural_key = f"relationship|{entity.qualified_name}|{nav.name}"
    semantic = NAV_SEMANTICS.get(normalize_nav_name(nav.name)) if nav.resolved else None
    if not nav.resolved:
        status = "unresolved"
        semantics = None
        confidence = None
        note = f"Navigation could not be resolved ({nav.unresolved_reason})."
    elif semantic:
        semantics, confidence, note = semantic
        status = "review_required"
        if nav.key_resolution != "discovered":
            note = f"{note} Foreign-key fields are not established."
    else:
        semantics = None
        confidence = None
        status = "review_required"
        note = "Navigation was discovered, but its business meaning is not established."
    signature = _sig(
        {
            "entity": entity.qualified_name,
            "navigation": nav.name,
            "target": nav.target_entity_type,
            "key_resolution": nav.key_resolution,
            "source_fields": list(nav.source_key_fields),
            "target_fields": list(nav.target_key_fields),
        }
    )
    item = OntologyRelationship(
        relationship_id=natural_key,
        natural_key=natural_key,
        source_entity=entity.qualified_name,
        source_entity_set=entity_set,
        navigation_property=nav.name,
        target_entity=nav.target_entity_type,
        target_entity_set=nav.target_entity_set,
        source_role=nav.from_role,
        target_role=nav.to_role,
        source_multiplicity=nav.source_multiplicity,
        target_multiplicity=nav.target_multiplicity,
        relationship_semantics=semantics,
        relationship_type=None,
        mapping_status=status,
        mapping_confidence=confidence,
        key_resolution=nav.key_resolution,
        source_key_fields=list(nav.source_key_fields),
        target_key_fields=list(nav.target_key_fields),
        inference_note=note,
        unresolved_reason=nav.unresolved_reason,
        ambiguous=nav.unresolved_reason == "ambiguous_association",
        signature=signature,
    )
    return _apply_relationship(item, reviews.get(natural_key))


def _signature_ok(review: ReviewRecord | None, signature: str) -> bool:
    return bool(review) and (not review.signature or review.signature == signature)


def _apply_class(item: OntologyClass, review: ReviewRecord | None) -> OntologyClass:
    if not _signature_ok(review, item.signature):
        return item
    update = {"status": review.status, "inference_note": review.note or item.inference_note}
    if review.canonical_name:
        update["canonical_name"] = review.canonical_name
    if review.effective_dating_rule:
        update["effective_dating_rule"] = review.effective_dating_rule
    if review.effective_identity_field:
        update["effective_identity_field"] = review.effective_identity_field
    return item.model_copy(update=update)


def _apply_property(item: OntologyProperty, review: ReviewRecord | None) -> OntologyProperty:
    if not _signature_ok(review, item.signature):
        return item
    update = {"mapping_status": review.status, "inference_note": review.note or item.inference_note}
    if review.canonical_name:
        update["canonical_property"] = review.canonical_name
    return item.model_copy(update=update)


def _apply_relationship(item: OntologyRelationship, review: ReviewRecord | None) -> OntologyRelationship:
    if not _signature_ok(review, item.signature):
        return item
    update = {"mapping_status": review.status, "inference_note": review.note or item.inference_note}
    if review.relationship_type:
        update["relationship_type"] = review.relationship_type
    if review.source_key_fields:
        update["source_key_fields"] = list(review.source_key_fields)
    if review.target_key_fields:
        update["target_key_fields"] = list(review.target_key_fields)
    return item.model_copy(update=update)

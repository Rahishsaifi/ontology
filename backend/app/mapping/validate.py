"""Validate explicit ontology approvals. Semantic guesses cannot pass through here."""

from __future__ import annotations

from app.errors import ValidationFailed
from app.models.catalog import EntityTypeModel
from app.ontology.canonical import BUSINESS_REL_TYPES, CANONICAL_NAMES


def validate_class_approval(entity: EntityTypeModel, payload: dict) -> dict:
    if not entity.key_defined:
        raise ValidationFailed("This entity type has no key and cannot be approved for ingestion.")
    canonical_name = payload.get("canonical_name")
    if canonical_name not in CANONICAL_NAMES:
        allowed = ", ".join(sorted(CANONICAL_NAMES))
        raise ValidationFailed(f"Canonical name must be one of: {allowed}.")
    names = {prop.name for prop in entity.properties}
    start = payload.get("effective_start_field")
    rule = payload.get("effective_dating_rule")
    identity_field = payload.get("effective_identity_field")
    effective = bool(start)
    in_key = bool(start and start in entity.key.property_names)
    if effective and not in_key:
        if rule not in {"preserve_history", "current_snapshot"}:
            raise ValidationFailed(
                "This entity is effective-dated and the date is not part of the key. "
                "Choose preserve_history or current_snapshot explicitly."
            )
        if rule == "preserve_history":
            if identity_field not in names:
                raise ValidationFailed("The effective-history field does not exist on the entity.")
            if identity_field in entity.key.property_names:
                raise ValidationFailed("That field is already part of the key.")
    elif rule not in {None, "", "key_includes_effective_date"}:
        raise ValidationFailed("An effective-dating rule does not apply to this entity.")
    else:
        rule = "key_includes_effective_date" if in_key else None
        identity_field = None
    warning = None
    if entity.name == "User" and canonical_name in {"Person", "Employee", "Employment"}:
        warning = (
            "Explicit mapping from User to "
            f"{canonical_name} was recorded. The generator will not infer this equivalence."
        )
    return {
        "canonical_name": canonical_name,
        "effective_dating_rule": rule,
        "effective_identity_field": identity_field if rule == "preserve_history" else None,
        "warning": warning,
    }


def validate_relationship_approval(
    source: EntityTypeModel,
    target: EntityTypeModel | None,
    payload: dict,
) -> dict:
    relationship_type = payload.get("relationship_type")
    if relationship_type not in BUSINESS_REL_TYPES:
        allowed = ", ".join(sorted(BUSINESS_REL_TYPES))
        raise ValidationFailed(f"Relationship type must be one of: {allowed}.")
    if target is None or not target.key_defined:
        raise ValidationFailed("The target entity type is missing or has no key, so the relationship cannot be approved.")
    source_fields = list(payload.get("source_key_fields") or [])
    target_fields = list(payload.get("target_key_fields") or [])
    if not source_fields or not target_fields:
        raise ValidationFailed("Source and target key fields are required before a relationship can be approved.")
    if len(source_fields) != len(target_fields):
        raise ValidationFailed("Source and target key field lists must be the same length.")
    source_names = set(source.property_map())
    for field in source_fields:
        if field not in source_names:
            raise ValidationFailed(f"Source field '{field}' does not exist on {source.qualified_name}.")
    if set(target_fields) != set(target.key.property_names):
        raise ValidationFailed(
            "Target fields must be exactly the target key so the graph identity is unambiguous."
        )
    order = {name: index for index, name in enumerate(target_fields)}
    reordered_target = list(target.key.property_names)
    reordered_source = [source_fields[order[name]] for name in reordered_target]
    return {
        "relationship_type": relationship_type,
        "source_key_fields": reordered_source,
        "target_key_fields": reordered_target,
    }


def validate_property_approval(entity: EntityTypeModel, source_property: str, payload: dict) -> dict:
    prop = entity.property_map().get(source_property)
    if prop is None:
        raise ValidationFailed(f"Property '{source_property}' does not exist on {entity.qualified_name}.")
    canonical = payload.get("canonical_name") or source_property
    if not isinstance(canonical, str) or not canonical.strip():
        raise ValidationFailed("A canonical property name is required.")
    return {"canonical_property": canonical.strip()}

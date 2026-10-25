"""Namespace-aware EDMX parser for SuccessFactors OData v2 metadata.

External edmx:Reference URLs are recorded and never fetched.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from lxml import etree

from app.errors import ValidationFailed
from app.models.catalog import (
    AssociationEndModel,
    AssociationModel,
    EntitySetModel,
    EntityTypeModel,
    KeyModel,
    NavigationModel,
    PropertyModel,
    ReferentialModel,
    SchemaCatalog,
)

EDM_NAMESPACES = {
    "http://schemas.microsoft.com/ado/2006/04/edm",
    "http://schemas.microsoft.com/ado/2007/05/edm",
    "http://schemas.microsoft.com/ado/2008/09/edm",
    "http://schemas.microsoft.com/ado/2009/11/edm",
}
EDMX_NAMESPACES = {
    "http://schemas.microsoft.com/ado/2007/06/edmx",
    "http://docs.oasis-open.org/odata/ns/edmx",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clark(tag: str) -> tuple[str, str]:
    if isinstance(tag, str) and tag.startswith("{"):
        namespace, local = tag[1:].split("}", 1)
        return namespace, local
    return "", str(tag)


def is_edm(namespace: str) -> bool:
    return namespace in EDM_NAMESPACES or namespace.endswith("/edm")


def is_edmx(namespace: str) -> bool:
    return namespace in EDMX_NAMESPACES or namespace.endswith("/edmx")


def _bool_attr(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def _int_attr(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _local_children(element, name: str):
    for child in list(element):
        namespace, local = clark(child.tag)
        if local == name and (is_edm(namespace) or namespace == ""):
            yield child


def _extension_attrs(element) -> dict[str, str]:
    found: dict[str, str] = {}
    for attr, value in element.attrib.items():
        if not str(attr).startswith("{"):
            continue
        namespace, local = attr[1:].split("}", 1)
        if is_edm(namespace) or is_edmx(namespace):
            continue
        found[local] = value
    return found


def _summary(element) -> str | None:
    for child in _local_children(element, "Documentation"):
        for summary in _local_children(child, "Summary"):
            if summary.text and summary.text.strip():
                return summary.text.strip()
    return None


def _resolve_qualified(type_name: str, namespace: str, types_by_qualified: dict, types_by_local: dict) -> str | None:
    if not type_name:
        return None
    if type_name in types_by_qualified:
        return type_name
    if "." not in type_name:
        candidate = f"{namespace}.{type_name}"
        if candidate in types_by_qualified:
            return candidate
        matches = types_by_local.get(type_name, [])
        if len(matches) == 1:
            return matches[0]
    return None


def catalog_hash(catalog: SchemaCatalog) -> str:
    payload = catalog.model_dump(mode="json")
    for key in ("generated_at", "metadata_hash", "origin"):
        payload.pop(key, None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_edmx(
    xml_bytes: bytes,
    *,
    source_system: str = "successfactors",
    generated_at: str | None = None,
    origin: str = "successfactors",
    max_bytes: int = 20 * 1024 * 1024,
) -> SchemaCatalog:
    if not xml_bytes:
        raise ValidationFailed("Metadata was empty.")
    if len(xml_bytes) > max_bytes:
        raise ValidationFailed("Metadata exceeds the configured size limit.")
    lowered = xml_bytes.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValidationFailed("Metadata XML could not be parsed.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, recover=False)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationFailed("Metadata XML could not be parsed.") from exc

    warnings: list[str] = []
    for element in root.iter():
        namespace, local = clark(element.tag)
        if local == "Reference" and (is_edmx(namespace) or namespace == ""):
            warnings.append(f"external_edmx_reference_ignored:{element.get('Uri') or 'unspecified'}")

    entity_types: list[EntityTypeModel] = []
    associations: list[AssociationModel] = []
    entity_sets: list[EntitySetModel] = []
    schemas: list[str] = []
    containers: list[str] = []

    for element in root.iter():
        namespace, local = clark(element.tag)
        if local != "Schema" or not is_edm(namespace):
            continue
        schema_namespace = element.get("Namespace") or ""
        if not schema_namespace:
            warnings.append("ignored_schema_without_namespace")
            continue
        schemas.append(schema_namespace)
        for child in list(element):
            child_ns, child_local = clark(child.tag)
            if not is_edm(child_ns):
                continue
            if child_local == "EntityType":
                parsed = _parse_entity_type(child, schema_namespace, warnings)
                if parsed:
                    entity_types.append(parsed)
            elif child_local == "Association":
                parsed_association = _parse_association(child, schema_namespace, warnings)
                if parsed_association:
                    associations.append(parsed_association)
            elif child_local == "EntityContainer":
                container_name = child.get("Name") or "EntityContainer"
                containers.append(f"{schema_namespace}.{container_name}")
                for set_el in _local_children(child, "EntitySet"):
                    set_name = set_el.get("Name")
                    set_type = set_el.get("EntityType")
                    if not set_name or not set_type:
                        warnings.append("ignored_incomplete_entity_set")
                        continue
                    entity_sets.append(
                        EntitySetModel(
                            name=set_name,
                            entity_type=set_type,
                            container=container_name,
                            namespace=schema_namespace,
                        )
                    )

    types_by_qualified = {item.qualified_name: item for item in entity_types}
    types_by_local: dict[str, list[str]] = {}
    for item in entity_types:
        types_by_local.setdefault(item.name, []).append(item.qualified_name)

    resolved_sets: list[EntitySetModel] = []
    sets_by_type: dict[str, list[str]] = {}
    for entity_set in entity_sets:
        qualified = _resolve_qualified(entity_set.entity_type, entity_set.namespace, types_by_qualified, types_by_local)
        if not qualified:
            warnings.append(f"unresolved_entity_set_type:{entity_set.name}")
            continue
        resolved_sets.append(entity_set.model_copy(update={"entity_type": qualified}))
        sets_by_type.setdefault(qualified, []).append(entity_set.name)

    associations_by_qualified = {item.qualified_name: item for item in associations}
    for entity in entity_types:
        entity.entity_set_names = sorted(sets_by_type.get(entity.qualified_name, []))
        entity.exposed = bool(entity.entity_set_names)
        entity.navigation_properties = _resolve_navigations(
            entity, associations_by_qualified, types_by_qualified, types_by_local, sets_by_type
        )

    entity_types.sort(key=lambda item: item.qualified_name)
    resolved_sets.sort(key=lambda item: item.name)
    associations.sort(key=lambda item: item.qualified_name)
    catalog = SchemaCatalog(
        source_system=source_system,
        generated_at=generated_at or _utcnow(),
        origin=origin,
        schemas=sorted(set(schemas)),
        containers=sorted(set(containers)),
        entity_types=entity_types,
        entity_sets=resolved_sets,
        associations=associations,
        warnings=sorted(set(warnings)),
    )
    catalog.metadata_hash = catalog_hash(catalog)
    return catalog


def _parse_entity_type(element, namespace: str, warnings: list[str]) -> EntityTypeModel | None:
    name = element.get("Name")
    if not name:
        warnings.append("ignored_entity_type_without_name")
        return None
    key_names = []
    for key_el in _local_children(element, "Key"):
        for ref in _local_children(key_el, "PropertyRef"):
            if ref.get("Name"):
                key_names.append(ref.get("Name"))
    properties: list[PropertyModel] = []
    navigations: list[NavigationModel] = []
    for child in list(element):
        child_ns, child_local = clark(child.tag)
        if child_ns and not is_edm(child_ns):
            warnings.append(f"ignored_non_edm_element:{namespace}.{name}.{child_local}")
            continue
        if child_local == "Property" and (is_edm(child_ns) or child_ns == ""):
            prop_name = child.get("Name")
            prop_type = child.get("Type")
            if not prop_name or not prop_type:
                warnings.append(f"ignored_incomplete_property:{namespace}.{name}")
                continue
            properties.append(
                PropertyModel(
                    name=prop_name,
                    edm_type=prop_type,
                    nullable=_bool_attr(child.get("Nullable"), True),
                    max_length=_int_attr(child.get("MaxLength")),
                    precision=_int_attr(child.get("Precision")),
                    scale=_int_attr(child.get("Scale")),
                    extensions=_extension_attrs(child),
                )
            )
        elif child_local == "NavigationProperty" and (is_edm(child_ns) or child_ns == ""):
            nav_name = child.get("Name")
            relationship = child.get("Relationship")
            from_role = child.get("FromRole")
            to_role = child.get("ToRole")
            if not nav_name or not relationship or not from_role or not to_role:
                warnings.append(f"ignored_incomplete_navigation:{namespace}.{name}")
                continue
            navigations.append(
                NavigationModel(
                    name=nav_name,
                    relationship=relationship,
                    from_role=from_role,
                    to_role=to_role,
                    resolved=False,
                    unresolved_reason="pending",
                    key_resolution="unresolved",
                )
            )
    return EntityTypeModel(
        name=name,
        namespace=namespace,
        qualified_name=f"{namespace}.{name}",
        description=_summary(element),
        key=KeyModel(property_names=key_names),
        key_defined=bool(key_names),
        properties=properties,
        navigation_properties=navigations,
    )


def _parse_association(element, namespace: str, warnings: list[str]) -> AssociationModel | None:
    name = element.get("Name")
    if not name:
        warnings.append("ignored_association_without_name")
        return None
    ends = []
    for end in _local_children(element, "End"):
        if end.get("Role") and end.get("Type"):
            ends.append(AssociationEndModel(role=end.get("Role"), type_name=end.get("Type"), multiplicity=end.get("Multiplicity")))
    referential = None
    for constraint in _local_children(element, "ReferentialConstraint"):
        principal = next(_local_children(constraint, "Principal"), None)
        dependent = next(_local_children(constraint, "Dependent"), None)
        if principal is None or dependent is None:
            warnings.append(f"ignored_incomplete_referential_constraint:{namespace}.{name}")
            continue
        principal_fields = [ref.get("Name") for ref in _local_children(principal, "PropertyRef") if ref.get("Name")]
        dependent_fields = [ref.get("Name") for ref in _local_children(dependent, "PropertyRef") if ref.get("Name")]
        if principal.get("Role") and dependent.get("Role") and principal_fields and dependent_fields:
            referential = ReferentialModel(
                principal_role=principal.get("Role"),
                dependent_role=dependent.get("Role"),
                principal_fields=principal_fields,
                dependent_fields=dependent_fields,
            )
    return AssociationModel(
        name=name,
        namespace=namespace,
        qualified_name=f"{namespace}.{name}",
        ends=ends,
        referential=referential,
    )


def _resolve_navigations(entity, associations, types_by_qualified, types_by_local, sets_by_type) -> list[NavigationModel]:
    resolved: list[NavigationModel] = []
    for nav in entity.navigation_properties:
        association = associations.get(nav.relationship)
        if association is None and "." not in nav.relationship:
            matches = [item for item in associations.values() if item.name == nav.relationship]
            association = matches[0] if len(matches) == 1 else None
            if len(matches) > 1:
                resolved.append(nav.model_copy(update={"resolved": False, "unresolved_reason": "ambiguous_association"}))
                continue
        if association is None:
            resolved.append(nav.model_copy(update={"resolved": False, "unresolved_reason": "association_not_found"}))
            continue
        ends = {end.role: end for end in association.ends}
        if nav.from_role not in ends or nav.to_role not in ends:
            resolved.append(nav.model_copy(update={"resolved": False, "unresolved_reason": "association_role_not_found"}))
            continue
        target_name = _resolve_qualified(ends[nav.to_role].type_name, association.namespace, types_by_qualified, types_by_local)
        if not target_name or target_name not in types_by_qualified:
            resolved.append(
                nav.model_copy(update={"resolved": False, "unresolved_reason": "target_type_not_found", "target_entity_type": target_name})
            )
            continue
        target_sets = sets_by_type.get(target_name, [])
        key_resolution = "unresolved"
        source_fields: list[str] = []
        target_fields: list[str] = []
        note = "no_referential_constraint"
        referential = association.referential
        if referential:
            if referential.dependent_role == nav.from_role and referential.principal_role == nav.to_role:
                source_props = set(entity.property_map())
                target_props = set(types_by_qualified[target_name].property_map())
                if all(field in source_props for field in referential.dependent_fields) and all(
                    field in target_props for field in referential.principal_fields
                ):
                    key_resolution = "discovered"
                    source_fields = list(referential.dependent_fields)
                    target_fields = list(referential.principal_fields)
                    note = "referential_constraint"
                else:
                    note = "referential_constraint_fields_missing"
            else:
                note = "foreign_key_not_on_source_entity"
        resolved.append(
            nav.model_copy(
                update={
                    "resolved": True,
                    "unresolved_reason": None,
                    "target_entity_type": target_name,
                    "target_entity_set": target_sets[0] if len(target_sets) == 1 else None,
                    "source_multiplicity": ends[nav.from_role].multiplicity,
                    "target_multiplicity": ends[nav.to_role].multiplicity,
                    "key_resolution": key_resolution,
                    "source_key_fields": source_fields,
                    "target_key_fields": target_fields,
                    "key_resolution_note": note,
                }
            )
        )
    return resolved

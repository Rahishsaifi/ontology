"""Full and incremental import into the graph.

A failed or empty read never deletes nodes. Relationship reconciliation runs
only after a non-empty full sync of that entity completes without record errors.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from app.connector.odata import build_incremental_filter, build_key_filter
from app.errors import MissingKeyError
from app.graph.models import EntityUpsert, RelationshipUpsert, sanitize_properties
from app.mapping.keys import build_source_key, composite_identity, join_pairs, normalize_value, split_pairs
from app.models.jobs import SyncState
from app.redaction import redact_text

logger = logging.getLogger(__name__)

LABEL_FIELDS = ("displayName", "name", "externalName", "jobTitle", "firstName", "comment")

# Present in SF $metadata but often blocked by RBP / field security on $select.
NON_SELECTABLE_PROPERTIES = frozenset(
    {
        "operation",
        "md5Checksum",
        "createdBy",
        "createdDateTime",
        "lastModifiedBy",
        "lastModifiedWith",
    }
)

_NOT_VIEWABLE_RE = re.compile(
    r"(?:bad property expression\s+)?(?:[\w.]*/)?(?P<prop>[A-Za-z_][\w]*)\s+is not viewable",
    re.IGNORECASE,
)
_BAD_PROPERTY_RE = re.compile(
    r"bad property expression\s+(?:[\w.]*/)?(?P<prop>[A-Za-z_][\w]*)",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_unviewable_property(message: str) -> str | None:
    """Extract a property name from SuccessFactors 'not viewable' / bad $select errors."""
    text = (message or "").strip()
    if not text:
        return None
    for pattern in (_NOT_VIEWABLE_RE, _BAD_PROPERTY_RE):
        match = pattern.search(text)
        if match:
            return match.group("prop")
    return None


def build_select(
    entity,
    ontology_class,
    relationships,
    *,
    include_sensitive: bool,
    exclude: set[str] | None = None,
) -> list[str]:
    rejected = {
        prop.source_property
        for prop in ontology_class.properties
        if prop.mapping_status == "rejected" and prop.source_property not in entity.key.property_names
    }
    blocked = set(NON_SELECTABLE_PROPERTIES) | set(exclude or ())
    sensitive = {prop.source_property for prop in ontology_class.properties if prop.sensitive}
    fields: list[str] = []
    for prop in entity.properties:
        if not prop.edm_type.startswith("Edm."):
            continue
        if prop.name in rejected:
            continue
        if prop.name in blocked and prop.name not in entity.key.property_names:
            continue
        if prop.name in sensitive and prop.name not in entity.key.property_names and not include_sensitive:
            continue
        fields.append(prop.name)
    for relationship in relationships:
        for field in relationship.source_key_fields:
            if field not in fields and field not in rejected and field not in blocked and field in entity.property_map():
                fields.append(field)
    if "lastModifiedDateTime" in entity.property_map() and "lastModifiedDateTime" not in fields:
        if "lastModifiedDateTime" not in rejected and "lastModifiedDateTime" not in blocked:
            fields.append("lastModifiedDateTime")
    for field in entity.key.property_names:
        if field not in fields:
            fields.append(field)
    return fields


def run_ingestion(
    *,
    catalog,
    ontology,
    connector,
    graph,
    database,
    job_id: str,
    entity_sets: list[str],
    mode: str,
    dry_run: bool,
    batch_size: int,
    include_sensitive: bool = False,
    only_source_keys: dict[str, set[str]] | None = None,
    provenance: str = "successfactors",
) -> None:
    database.update_job(job_id, status="running", started_at=_now(), progress={"entities_completed": 0, "entities_total": len(entity_sets)})
    summary: dict = {"entities": {}, "metadata_changed": False, "dry_run": dry_run, "mode": mode}
    wrote_any = False
    error_count = 0
    try:
        graph.init_schema()
        graph.sync_ontology(ontology)
    except Exception as exc:
        if not dry_run:
            _fail(database, job_id, summary, f"Graph schema initialization failed: {redact_text(str(exc))}")
            return

    for index, entity_set in enumerate(entity_sets):
        entity_summary, entity_errors, wrote = _import_entity(
            catalog=catalog,
            ontology=ontology,
            connector=connector,
            graph=graph,
            database=database,
            job_id=job_id,
            entity_set=entity_set,
            mode=mode,
            dry_run=dry_run,
            batch_size=batch_size,
            include_sensitive=include_sensitive,
            only_source_keys=None if only_source_keys is None else only_source_keys.get(entity_set),
            provenance=provenance,
            summary=summary,
        )
        summary["entities"][entity_set] = entity_summary
        error_count += entity_errors
        wrote_any = wrote_any or wrote
        database.update_job(
            job_id,
            progress={"entities_completed": index + 1, "entities_total": len(entity_sets)},
            summary=summary,
        )
        logger.info(
            "ingestion entity_set=%s fetched=%s failed=%s dry_run=%s",
            entity_set,
            entity_summary.get("fetched", 0),
            entity_summary.get("failed", 0),
            dry_run,
        )

    status = "succeeded"
    if error_count and wrote_any:
        status = "partial"
    elif error_count:
        status = "failed"
    database.update_job(job_id, status=status, finished_at=_now(), summary=summary)


def _fail(database, job_id, summary, message: str) -> None:
    database.add_error(job_id, batch_no=None, entity_set=None, source_key=None, message=message)
    summary["fatal"] = message
    database.update_job(job_id, status="failed", finished_at=_now(), summary=summary)


def _import_entity(
    *,
    catalog,
    ontology,
    connector,
    graph,
    database,
    job_id,
    entity_set,
    mode,
    dry_run,
    batch_size,
    include_sensitive,
    only_source_keys,
    provenance,
    summary,
) -> tuple[dict, int, bool]:
    result = {
        "fetched": 0,
        "upserted": 0,
        "failed": 0,
        "skipped": 0,
        "relationships_written": 0,
        "relationships_skipped": 0,
        "missing_references": 0,
        "reconciled": 0,
        "status": "skipped",
    }
    entity = catalog.entity_for_set(entity_set)
    ontology_class = _class_for(ontology, entity.qualified_name) if entity else None
    if entity is None or ontology_class is None:
        result["reason"] = "unknown_entity_set"
        database.add_error(job_id, batch_no=None, entity_set=entity_set, source_key=None, message="Entity set is not in the catalog.")
        result["failed"] = 1
        result["status"] = "failed"
        return result, 1, False
    if ontology_class.status != "approved":
        result["reason"] = "mapping_not_approved"
        result["status"] = "skipped"
        return result, 0, False
    if not ontology_class.key_defined:
        message = "The entity type has no key and was not imported."
        database.add_error(job_id, batch_no=None, entity_set=entity_set, source_key=None, message=message)
        result["failed"] = 1
        result["status"] = "failed"
        result["reason"] = "missing_key"
        return result, 1, False
    if ontology_class.effective_dated and not ontology_class.effective_date_in_key:
        if ontology_class.effective_dating_rule not in {"preserve_history", "current_snapshot"}:
            message = "Effective-dated records were not collapsed or imported because no preservation rule is approved."
            database.add_error(job_id, batch_no=None, entity_set=entity_set, source_key=None, message=message)
            result["failed"] = 1
            result["status"] = "failed"
            result["reason"] = "effective_dating_rule_required"
            return result, 1, False

    approved_rels = [
        item
        for item in ontology.relationships
        if item.source_entity == entity.qualified_name and item.mapping_status == "approved" and item.relationship_type
    ]
    retired_rels = [
        item
        for item in ontology.relationships
        if item.source_entity == entity.qualified_name
        and item.mapping_status != "approved"
        and item.relationship_type
    ]
    dropped_fields: set[str] = set()
    selected = build_select(
        entity,
        ontology_class,
        approved_rels,
        include_sensitive=include_sensitive,
        exclude=dropped_fields,
    )
    state = database.get_sync_state(entity_set)
    if state and state.catalog_hash and state.catalog_hash != catalog.metadata_hash:
        summary["metadata_changed"] = True
    filter_expr = None
    if mode == "incremental":
        if not any(prop.name == "lastModifiedDateTime" for prop in entity.properties):
            message = "Incremental sync is not available because lastModifiedDateTime is not in the metadata."
            database.add_error(job_id, batch_no=None, entity_set=entity_set, source_key=None, message=message)
            result["failed"] = 1
            result["status"] = "failed"
            result["reason"] = "incremental_not_supported"
            return result, 1, False
        if state is None or not state.watermark:
            message = "Incremental sync requires a previous successful full sync."
            database.add_error(job_id, batch_no=None, entity_set=entity_set, source_key=None, message=message)
            result["failed"] = 1
            result["status"] = "failed"
            result["reason"] = "incremental_requires_prior_success"
            return result, 1, False
        filter_expr = build_incremental_filter(state.watermark)

    types = {prop.name: prop.edm_type for prop in entity.properties}
    target_types = catalog.type_index()
    incomplete = False
    fetched = 0
    max_watermark = state.watermark if state else None
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    next_url = None
    seen_links: set[str] = set()
    batch_no = 0
    snapshot_nodes: list[EntityUpsert] = []
    snapshot_rels: list[RelationshipUpsert] = []
    wrote = False
    while True:
        batch_no += 1
        single_filters = _key_filters(only_source_keys, entity, types) if only_source_keys and batch_no == 1 else [filter_expr]
        # Key retries issue one request per record and do not follow unrelated pages.
        pages = single_filters if only_source_keys else [filter_expr]
        if only_source_keys and batch_no > 1:
            break
        for page_filter in pages:
            try:
                page = _fetch_page_dropping_unviewable(
                    connector=connector,
                    entity_set=entity_set,
                    selected=selected,
                    catalog=catalog,
                    batch_size=batch_size,
                    page_filter=page_filter,
                    next_url=next_url if not only_source_keys else None,
                    entity=entity,
                    ontology_class=ontology_class,
                    approved_rels=approved_rels,
                    include_sensitive=include_sensitive,
                    dropped_fields=dropped_fields,
                )
                selected = build_select(
                    entity,
                    ontology_class,
                    approved_rels,
                    include_sensitive=include_sensitive,
                    exclude=dropped_fields,
                )
            except Exception as exc:
                incomplete = True
                result["failed"] += 1
                database.add_error(
                    job_id,
                    batch_no=batch_no,
                    entity_set=entity_set,
                    source_key=None,
                    message=redact_text(str(exc)),
                )
                next_url = None
                break
            nodes: list[EntityUpsert] = []
            rel_rows: list[RelationshipUpsert] = []
            for record in page.records:
                fetched += 1
                try:
                    prepared = _prepare_node(
                        record,
                        entity,
                        ontology_class,
                        types,
                        provenance,
                        include_sensitive,
                        only_source_keys,
                        catalog.source_system,
                    )
                except MissingKeyError as exc:
                    incomplete = True
                    result["failed"] += 1
                    database.add_error(
                        job_id,
                        batch_no=batch_no,
                        entity_set=entity_set,
                        source_key=None,
                        message=str(exc),
                    )
                    continue
                if prepared is None:
                    result["skipped"] += 1
                    continue
                node, modified = prepared
                if modified and (max_watermark is None or modified > max_watermark):
                    max_watermark = modified
                nodes.append(node)
                for relationship in approved_rels:
                    target = target_types.get(relationship.target_entity or "")
                    if target is None:
                        result["missing_references"] += 1
                        continue
                    try:
                        target_key = _target_key(record, relationship, entity, target)
                    except MissingKeyError as exc:
                        incomplete = True
                        result["failed"] += 1
                        database.add_error(
                            job_id,
                            batch_no=batch_no,
                            entity_set=entity_set,
                            source_key=node.source_key,
                            message=str(exc),
                        )
                        continue
                    if target_key is None:
                        result["relationships_skipped"] += 1
                        continue
                    pairs[relationship.relationship_id].add((node.source_key, target_key))
                    rel_rows.append(
                        RelationshipUpsert(
                            relationship_type=relationship.relationship_type,
                            source_identity=node.identity,
                            target_identity=composite_identity(catalog.source_system, target.qualified_name, target_key),
                            mapping_id=relationship.relationship_id,
                            navigation_property=relationship.navigation_property,
                            synced_at=_now(),
                        )
                    )
            if ontology_class.effective_dating_rule == "current_snapshot":
                snapshot_nodes.extend(nodes)
                snapshot_rels.extend(rel_rows)
            else:
                written, missing, failed_rows = _write_batch(graph, nodes, rel_rows, dry_run)
                result["upserted"] += written
                result["missing_references"] += missing
                result["relationships_written"] += max(len(rel_rows) - missing, 0)
                wrote = wrote or (written > 0 and not dry_run)
                for source_key, message in failed_rows:
                    incomplete = True
                    result["failed"] += 1
                    database.add_error(
                        job_id,
                        batch_no=batch_no,
                        entity_set=entity_set,
                        source_key=source_key,
                        message=message,
                    )
            if not only_source_keys:
                if page.next_url and page.next_url in seen_links:
                    incomplete = True
                    result["failed"] += 1
                    database.add_error(
                        job_id,
                        batch_no=batch_no,
                        entity_set=entity_set,
                        source_key=None,
                        message="Pagination stopped because the next link repeated.",
                    )
                    next_url = None
                else:
                    if page.next_url:
                        seen_links.add(page.next_url)
                    next_url = page.next_url
        if only_source_keys or not next_url or incomplete and next_url is None:
            if incomplete and next_url is None:
                break
            if not next_url or only_source_keys:
                break
    result["fetched"] = fetched
    if dropped_fields:
        result["dropped_select_fields"] = sorted(dropped_fields)
    if ontology_class.effective_dating_rule == "current_snapshot":
        if incomplete:
            database.add_error(
                job_id,
                batch_no=None,
                entity_set=entity_set,
                source_key=None,
                message="The current-snapshot rule was not applied because the feed was incomplete.",
            )
            result["failed"] += 1
        else:
            chosen = _latest_snapshot(snapshot_nodes)
            chosen_ids = {item.identity for item in chosen}
            rels = [item for item in snapshot_rels if item.source_identity in chosen_ids]
            written, missing, failed_rows = _write_batch(graph, chosen, rels, dry_run)
            result["upserted"] += written
            result["missing_references"] += missing
            wrote = wrote or (written > 0 and not dry_run)
            for source_key, message in failed_rows:
                incomplete = True
                result["failed"] += 1
                database.add_error(
                    job_id,
                    batch_no=None,
                    entity_set=entity_set,
                    source_key=source_key,
                    message=message,
                )
    if not incomplete and not dry_run and mode == "full" and fetched > 0:
        for relationship in approved_rels:
            removed = graph.reconcile_relationships(
                relationship_type=relationship.relationship_type,
                mapping_id=relationship.relationship_id,
                entity_type=entity.qualified_name,
                source_system=catalog.source_system,
                pairs=pairs.get(relationship.relationship_id, set()),
            )
            result["reconciled"] += removed
        for relationship in retired_rels:
            removed = graph.reconcile_relationships(
                relationship_type=relationship.relationship_type,
                mapping_id=relationship.relationship_id,
                entity_type=entity.qualified_name,
                source_system=catalog.source_system,
                pairs=set(),
            )
            result["reconciled"] += removed
    elif not incomplete and not dry_run and fetched == 0:
        result["note"] = "empty_result_preserved_existing_graph"
    if not incomplete and not dry_run:
        previous = state.watermark if state else None
        watermark = max_watermark if fetched > 0 and max_watermark else previous
        database.upsert_sync_state(
            SyncState(
                entity_set=entity_set,
                last_success_at=_now(),
                watermark=watermark,
                catalog_hash=catalog.metadata_hash,
                status="succeeded",
            )
        )
        result["status"] = "succeeded"
    elif incomplete:
        result["status"] = "incomplete"
    else:
        result["status"] = "dry_run"
    return result, result["failed"], wrote


def _fetch_page_dropping_unviewable(
    *,
    connector,
    entity_set: str,
    selected: list[str],
    catalog,
    batch_size: int,
    page_filter,
    next_url,
    entity,
    ontology_class,
    approved_rels,
    include_sensitive: bool,
    dropped_fields: set[str],
):
    """Retry $select after dropping properties SF reports as not viewable."""
    current = list(selected)
    attempts = 0
    while True:
        try:
            return connector.fetch_page(
                entity_set,
                select=current,
                catalog=catalog,
                top=batch_size,
                filter_expr=page_filter,
                next_url=next_url,
            )
        except Exception as exc:
            prop = parse_unviewable_property(str(exc))
            if not prop or prop in entity.key.property_names or prop in dropped_fields:
                raise
            if prop not in current and prop.lower() not in {item.lower() for item in current}:
                raise
            match = next((item for item in current if item.lower() == prop.lower()), prop)
            dropped_fields.add(match)
            current = build_select(
                entity,
                ontology_class,
                approved_rels,
                include_sensitive=include_sensitive,
                exclude=dropped_fields,
            )
            attempts += 1
            logger.warning(
                "Dropped non-viewable SuccessFactors property %s from %s $select (attempt %s)",
                match,
                entity_set,
                attempts,
            )
            if attempts > 40 or not current:
                raise


def _class_for(ontology, qualified: str):
    for item in ontology.classes:
        if item.source_entity_type == qualified:
            return item
    return None


def _prepare_node(record, entity, ontology_class, types, provenance, include_sensitive, only_source_keys, source_system):
    source_key = build_source_key(entity.key.property_names, record, types)
    if ontology_class.effective_dating_rule == "preserve_history" and ontology_class.effective_identity_field:
        field = ontology_class.effective_identity_field
        if field not in record or record[field] in {None, ""}:
            raise MissingKeyError(f"Effective history field '{field}' has no value.")
        extra = normalize_value(record[field], types.get(field, "Edm.String"))
        source_key = join_pairs(split_pairs(source_key) + [(field, extra)])
    if only_source_keys is not None and source_key not in only_source_keys:
        return None
    rejected = {prop.source_property for prop in ontology_class.properties if prop.mapping_status == "rejected"}
    sensitive = {prop.source_property for prop in ontology_class.properties if prop.sensitive}
    properties = {}
    for key, value in record.items():
        if key in rejected:
            continue
        if key in sensitive and not include_sensitive:
            continue
        if key == "lastModifiedDateTime":
            continue
        properties[key] = value
    modified = None
    if record.get("lastModifiedDateTime"):
        try:
            modified = normalize_value(record["lastModifiedDateTime"], "Edm.DateTime")
        except MissingKeyError:
            modified = None
    start = _optional_temporal(record, ontology_class.effective_start_field, types)
    end = _optional_temporal(record, ontology_class.effective_end_field, types)
    node = EntityUpsert(
        identity=composite_identity(source_system, entity.qualified_name, source_key),
        source_system=source_system,
        entity_type=entity.qualified_name,
        source_key=source_key,
        last_synced_at=_now(),
        canonical_class=ontology_class.canonical_name,
        display_label=_label(record, source_key, sensitive),
        effective_start=start,
        effective_end=end,
        source_modified_at=modified,
        provenance=provenance,
        properties=sanitize_properties(properties),
    )
    return node, modified


def _optional_temporal(record, field, types):
    if not field or record.get(field) in {None, ""}:
        return None
    try:
        return normalize_value(record[field], types.get(field, "Edm.DateTime"))
    except MissingKeyError:
        return str(record[field])


def _label(record, source_key, sensitive: set[str]) -> str:
    for field in LABEL_FIELDS:
        value = record.get(field)
        if value and field not in sensitive:
            text = str(value)
            if field == "firstName" and record.get("lastName") and "lastName" not in sensitive:
                text = f"{text} {record['lastName']}"
            return text[:200]
    return source_key[:200]


def _target_key(record, relationship, source_entity, target_entity):
    source_props = source_entity.property_map()
    target_types = {prop.name: prop.edm_type for prop in target_entity.properties}
    target_record = {}
    for source_field, target_field in zip(relationship.source_key_fields, relationship.target_key_fields):
        value = record.get(source_field)
        if value is None or value == "":
            prop = source_props.get(source_field)
            if prop is None or prop.nullable:
                return None
            raise MissingKeyError(f"Required relationship field '{source_field}' is empty.")
        target_record[target_field] = value
    return build_source_key(target_entity.key.property_names, target_record, target_types)


def _write_batch(graph, nodes: list[EntityUpsert], rel_rows: list[RelationshipUpsert], dry_run: bool):
    if dry_run:
        missing = sum(1 for row in rel_rows if not graph.contains(row.target_identity))
        return len(nodes), missing, []
    if not nodes and not rel_rows:
        return 0, 0, []
    attempts = 0
    while True:
        try:
            written = graph.upsert_entities(nodes) if nodes else 0
            _, missing = graph.upsert_relationships(rel_rows) if rel_rows else (0, 0)
            return written, missing, []
        except Exception as exc:
            transient = exc.__class__.__name__ == "TransientGraphError"
            attempts += 1
            if transient and attempts <= 2:
                continue
            break
    written = 0
    missing = 0
    failed = []
    saved: list[EntityUpsert] = []
    for node in nodes:
        try:
            written += graph.upsert_entities([node])
            saved.append(node)
        except Exception as exc:
            failed.append((node.source_key, redact_text(str(exc)) or "The record could not be written."))
    saved_ids = {node.identity for node in saved}
    rel_rows = [row for row in rel_rows if row.source_identity in saved_ids]
    if rel_rows:
        try:
            _, missing = graph.upsert_relationships(rel_rows)
        except Exception as exc:
            failed.append((None, redact_text(str(exc)) or "A relationship batch could not be written."))
    return written, missing, failed


def _latest_snapshot(nodes: list[EntityUpsert]) -> list[EntityUpsert]:
    chosen: dict[str, EntityUpsert] = {}
    for node in nodes:
        current = chosen.get(node.source_key)
        if current is None or (node.effective_start or "") >= (current.effective_start or ""):
            chosen[node.source_key] = node
    return list(chosen.values())


def _key_filters(source_keys: set[str] | None, entity, types) -> list[str | None]:
    if not source_keys:
        return [None]
    filters = []
    for source_key in sorted(source_keys):
        values = dict(split_pairs(source_key))
        if not set(entity.key.property_names).issubset(values):
            continue
        filters.append(build_key_filter(entity.key.property_names, values, types))
    return filters or [None]

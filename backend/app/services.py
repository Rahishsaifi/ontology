"""Application workflows shared by the API."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.connector.client import DemoConnector, SuccessFactorsClient
from app.connector.demo import demo_records
from app.discovery.parser import parse_edmx
from app.errors import ConflictError, NotFoundError, ValidationFailed
from app.graph.cypher_guard import sanitize_parameters, validate_readonly_cypher
from app.graph.memory_store import MemoryGraphStore
from app.graph.neo4j_store import Neo4jGraphStore
from app.graph.queries import load_query_library, resolve_query_params
from app.mapping.validate import validate_class_approval, validate_property_approval, validate_relationship_approval
from app.models.jobs import JobRecord
from app.models.ontology import ReviewRecord
from app.ontology.generator import apply_mapping_version, generate_ontology
from app.redaction import redact_text
from app.secrets import SecretOverlay, apply_overlay, effective_auth
from app.storage import load_catalog, load_ontology, load_reviews, save_catalog, save_ontology, save_reviews
from app.sync.runner import build_select, run_ingestion

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AppState:
    def __init__(self, settings, database) -> None:
        self.settings = settings
        self.database = database
        self.secrets = SecretOverlay()
        self.graph = build_graph(settings)
        self.queries = load_query_library(settings.samples_path() / "graph-queries.json")
        self.demo = None
        if settings.demo_mode:
            xml_path = settings.samples_path() / "synthetic-core-hr.edmx"
            self.demo = DemoConnector(
                xml_path.read_bytes(),
                demo_records(),
                page_size=settings.sf_page_size,
            )

    def close(self) -> None:
        self.graph.close()
        self.database.close()

    def open_connector(self, auth=None):
        if self.settings.demo_mode:
            return self.demo, False
        resolved = auth or effective_auth(self.settings, self.secrets)
        client = SuccessFactorsClient(
            resolved,
            timeout=self.settings.sf_timeout_seconds,
            max_retries=self.settings.sf_max_retries,
            page_size=self.settings.sf_page_size,
            tls_verify=self.settings.tls_verify,
            allow_insecure_http=self.settings.sf_allow_insecure_http,
        )
        return client, True


def build_graph(settings):
    if settings.graph_backend == "memory":
        return MemoryGraphStore(settings.source_system)
    if settings.graph_backend == "neo4j":
        return Neo4jGraphStore(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.source_system,
            tls_verify=settings.neo4j_tls_verify,
        )
    raise ValidationFailed("GRAPH_BACKEND must be memory or neo4j.")


def public_health(state: AppState) -> dict:
    graph = {"connected": False, "backend": state.settings.graph_backend, "detail": ""}
    try:
        graph = state.graph.test()
    except Exception as exc:
        graph = {
            "connected": False,
            "backend": state.settings.graph_backend,
            "detail": redact_text(str(exc)),
        }
    credential_source = "demo" if state.settings.demo_mode else "none"
    if not state.settings.demo_mode:
        if state.secrets.configured():
            credential_source = "session"
        elif state.settings.sf_base_url and (
            state.settings.sf_access_token
            or state.settings.sf_username
            or state.settings.sf_saml_assertion
            or state.settings.sf_private_key
        ):
            credential_source = "environment"
    return {
        "status": "ok",
        "version": "0.1.0",
        "demo_mode": state.settings.demo_mode,
        "accepts_demo_tokens": state.settings.demo_tokens_active(),
        "graph_backend": state.settings.graph_backend,
        "graph": graph,
        "successfactors": {
            "mode": "demo" if state.settings.demo_mode else state.settings.sf_auth_method,
            "credential_source": credential_source,
            "tls_verify": state.settings.tls_verify,
        },
    }


def test_successfactors(state: AppState, payload: dict) -> dict:
    if state.settings.demo_mode:
        connector, _owned = state.open_connector()
        catalog = parse_edmx(connector.get_metadata(), source_system=state.settings.source_system, origin="synthetic_demo")
        return {
            "connected": True,
            "demo_mode": True,
            "auth_method": "demo",
            "entity_set_count": len(catalog.entity_sets),
            "base_url": connector.base_url,
            "detail": "Demo mode used synthetic metadata and did not call SuccessFactors or store the submitted credentials.",
        }
    auth = effective_auth(state.settings, state.secrets)
    for field in (
        "base_url",
        "auth_method",
        "access_token",
        "username",
        "password",
        "company_id",
        "token_url",
        "client_id",
        "saml_assertion",
        "user_id",
        "private_key",
        "user_key",
        "idp_url",
    ):
        if payload.get(field):
            setattr(auth, field, payload[field])
    connector, owned = state.open_connector(auth)
    try:
        catalog = parse_edmx(connector.get_metadata(), source_system=state.settings.source_system, origin="successfactors")
    finally:
        if owned:
            connector.close()
    if payload.get("remember_for_session", True):
        apply_overlay(state.secrets, payload)
    return {
        "connected": True,
        "demo_mode": False,
        "auth_method": auth.method,
        "entity_set_count": len(catalog.entity_sets),
        "base_url": connector.base_url,
        "detail": "Metadata was downloaded. Credentials were kept in process memory only."
        if payload.get("remember_for_session", True)
        else "Metadata was downloaded. Credentials were not stored.",
    }


def clear_session(state: AppState) -> dict:
    state.secrets.clear()
    return {"cleared": True}


def run_discovery(state: AppState) -> dict:
    connector, owned = state.open_connector()
    try:
        xml = connector.get_metadata()
    finally:
        if owned:
            connector.close()
    origin = "synthetic_demo" if state.settings.demo_mode else "successfactors"
    catalog = parse_edmx(xml, source_system=state.settings.source_system, origin=origin)
    save_catalog(state.settings, catalog)
    stale = False
    try:
        ontology = load_ontology(state.settings)
        stale = ontology.catalog_hash != catalog.metadata_hash
    except NotFoundError:
        stale = False
    return {
        "origin": origin,
        "demo_mode": state.settings.demo_mode,
        "metadata_hash": catalog.metadata_hash,
        "entity_sets": len(catalog.entity_sets),
        "entity_types": len(catalog.entity_types),
        "associations": len(catalog.associations),
        "warnings": catalog.warnings,
        "ontology_stale": stale,
    }


def generate(state: AppState):
    catalog = load_catalog(state.settings)
    reviews = load_reviews(state.settings)
    ontology = generate_ontology(
        catalog,
        reviews.mappings,
        sensitive_patterns=state.settings.sensitive_patterns(),
    )
    ontology = apply_mapping_version(ontology, reviews.mapping_version)
    save_ontology(state.settings, ontology)
    _sync_schema(state, ontology)
    return ontology


def approve_mapping(state: AppState, mapping_id: str, payload: dict):
    catalog = load_catalog(state.settings)
    reviews = load_reviews(state.settings)
    draft = generate_ontology(catalog, reviews.mappings, sensitive_patterns=state.settings.sensitive_patterns())
    located = _require_mapping(draft, mapping_id)
    review = _approved_review(catalog, located, payload)
    _upsert_review(reviews, review)
    reviews.mapping_version += 1
    save_reviews(state.settings, reviews)
    ontology = generate_ontology(catalog, reviews.mappings, sensitive_patterns=state.settings.sensitive_patterns())
    ontology = apply_mapping_version(ontology, reviews.mapping_version)
    updated = _require_mapping(ontology, mapping_id)
    status = updated["status"]
    if status != "approved":
        raise ValidationFailed(updated.get("note") or "The mapping could not be approved.")
    save_ontology(state.settings, ontology)
    _sync_schema(state, ontology)
    return {"ontology": ontology, "mapping": updated, "warning": review.note if "Explicit mapping from User" in (review.note or "") else None}


def reject_mapping(state: AppState, mapping_id: str, note: str | None):
    catalog = load_catalog(state.settings)
    reviews = load_reviews(state.settings)
    draft = generate_ontology(catalog, reviews.mappings, sensitive_patterns=state.settings.sensitive_patterns())
    located = _require_mapping(draft, mapping_id)
    review = ReviewRecord(
        kind=located["kind"],
        natural_key=located["natural_key"],
        source_entity_type=located["source_entity_type"],
        source_property=located.get("source_property"),
        navigation_property=located.get("navigation_property"),
        status="rejected",
        canonical_name=located.get("canonical_name"),
        relationship_type=located.get("relationship_type") or located.get("relationship_semantics"),
        source_key_fields=located.get("source_key_fields") or [],
        target_key_fields=located.get("target_key_fields") or [],
        signature=located["signature"],
        note=note,
        updated_at=_now(),
    )
    _upsert_review(reviews, review)
    reviews.mapping_version += 1
    save_reviews(state.settings, reviews)
    ontology = generate_ontology(catalog, reviews.mappings, sensitive_patterns=state.settings.sensitive_patterns())
    ontology = apply_mapping_version(ontology, reviews.mapping_version)
    save_ontology(state.settings, ontology)
    _sync_schema(state, ontology)
    return ontology


def import_mappings(state: AppState, payload: dict):
    catalog = load_catalog(state.settings)
    reviews = load_reviews(state.settings)
    draft = generate_ontology(catalog, [], sensitive_patterns=state.settings.sensitive_patterns())
    incoming = []
    for raw in payload.get("mappings") or []:
        if not isinstance(raw, dict):
            raise ValidationFailed("Each mapping must be an object.")
        incoming.append(_review_from_import(catalog, draft, raw))
    by_key = {item.natural_key: item for item in reviews.mappings}
    for review in incoming:
        if review.status in {"discovered", "review_required", "inferred"}:
            by_key.pop(review.natural_key, None)
        else:
            by_key[review.natural_key] = review
    reviews.mappings = list(by_key.values())
    reviews.source_system = state.settings.source_system
    reviews.mapping_version += 1
    save_reviews(state.settings, reviews)
    ontology = generate_ontology(catalog, reviews.mappings, sensitive_patterns=state.settings.sensitive_patterns())
    ontology = apply_mapping_version(ontology, reviews.mapping_version)
    save_ontology(state.settings, ontology)
    _sync_schema(state, ontology)
    return ontology


def export_mappings(state: AppState) -> dict:
    ontology = load_ontology(state.settings)
    mappings = []
    for item in ontology.classes:
        mappings.append(
            {
                "kind": "class",
                "mapping_id": item.class_id,
                "natural_key": item.natural_key,
                "source_entity_type": item.source_entity_type,
                "status": item.status,
                "canonical_name": item.canonical_name,
                "effective_dating_rule": item.effective_dating_rule,
                "effective_identity_field": item.effective_identity_field,
                "signature": item.signature,
                "note": item.inference_note,
            }
        )
        for prop in item.properties:
            mappings.append(
                {
                    "kind": "property",
                    "mapping_id": prop.property_id,
                    "natural_key": prop.natural_key,
                    "source_entity_type": item.source_entity_type,
                    "source_property": prop.source_property,
                    "status": prop.mapping_status,
                    "canonical_name": prop.canonical_property,
                    "signature": prop.signature,
                    "note": prop.inference_note,
                }
            )
    for item in ontology.relationships:
        mappings.append(
            {
                "kind": "relationship",
                "mapping_id": item.relationship_id,
                "natural_key": item.natural_key,
                "source_entity_type": item.source_entity,
                "navigation_property": item.navigation_property,
                "status": item.mapping_status,
                "relationship_type": item.relationship_type,
                "source_key_fields": item.source_key_fields,
                "target_key_fields": item.target_key_fields,
                "signature": item.signature,
                "note": item.inference_note,
            }
        )
    return {
        "version": 1,
        "mapping_version": ontology.mapping_version,
        "source_system": ontology.source_system,
        "mappings": mappings,
    }


def preview_entity(state: AppState, entity_set: str, limit: int) -> dict:
    catalog = load_catalog(state.settings)
    entity = catalog.entity_for_set(entity_set)
    if entity is None:
        raise NotFoundError(f"Entity set '{entity_set}' was not discovered.")
    ontology = _ontology_or_none(state)
    ontology_class = None
    relationships = []
    if ontology:
        ontology_class = next((item for item in ontology.classes if item.source_entity_type == entity.qualified_name), None)
        relationships = [
            item
            for item in ontology.relationships
            if item.source_entity == entity.qualified_name and item.mapping_status == "approved"
        ]
    if ontology_class is None:
        from app.ontology.generator import generate_ontology as _generate

        draft = _generate(catalog, [], sensitive_patterns=state.settings.sensitive_patterns())
        ontology_class = next(item for item in draft.classes if item.source_entity_type == entity.qualified_name)
    selected = build_select(entity, ontology_class, relationships, include_sensitive=False)
    connector, owned = state.open_connector()
    try:
        page = connector.fetch_page(entity_set, select=selected, catalog=catalog, top=max(1, min(limit, 20)))
    finally:
        if owned:
            connector.close()
    omitted = [
        prop.source_property
        for prop in ontology_class.properties
        if prop.sensitive or prop.mapping_status == "rejected" or not prop.data_type.startswith("Edm.")
    ]
    return {
        "demo_mode": state.settings.demo_mode,
        "entity_set": entity_set,
        "fields": selected,
        "omitted_fields": omitted,
        "rows": page.records,
        "mapping_status": ontology_class.status,
    }


def start_job(state: AppState, *, job_type: str, entity_sets: list[str], mode: str, dry_run: bool, batch_size: int | None, only_source_keys=None):
    if not entity_sets:
        raise ValidationFailed("Select at least one entity set.")
    catalog = load_catalog(state.settings)
    ontology = load_ontology(state.settings)
    unknown = [name for name in entity_sets if catalog.entity_for_set(name) is None]
    if unknown:
        raise ValidationFailed(f"Unknown entity sets: {', '.join(unknown)}.")
    job = JobRecord(
        id=str(uuid.uuid4()),
        job_type=job_type,
        status="pending",
        dry_run=dry_run,
        mode=mode,
        entity_sets=entity_sets,
        created_at=_now(),
    )
    state.database.create_job(job)
    size = max(1, min(batch_size or state.settings.ingestion_batch_size, 500))

    def work() -> None:
        connector, owned = state.open_connector()
        try:
            run_ingestion(
                catalog=catalog,
                ontology=ontology,
                connector=connector,
                graph=state.graph,
                database=state.database,
                job_id=job.id,
                entity_sets=entity_sets,
                mode=mode,
                dry_run=dry_run,
                batch_size=size,
                only_source_keys=only_source_keys,
                provenance="synthetic_demo" if state.settings.demo_mode else "successfactors",
            )
        except Exception as exc:
            logger.exception("job failed")
            state.database.add_error(
                job.id,
                batch_no=None,
                entity_set=None,
                source_key=None,
                message=redact_text(str(exc)) or "The job failed.",
            )
            state.database.update_job(job.id, status="failed", finished_at=_now())
        finally:
            if owned:
                connector.close()

    if state.settings.inline_jobs:
        work()
    else:
        threading.Thread(target=work, name=f"job-{job.id}", daemon=True).start()
    return state.database.get_job(job.id)


def retry_job(state: AppState, job_id: str):
    previous = state.database.get_job(job_id)
    if previous is None:
        raise NotFoundError("Job not found.")
    keys: dict[str, set[str]] = {}
    entity_sets = set()
    for error in previous.errors:
        if not error.entity_set:
            continue
        entity_sets.add(error.entity_set)
        if error.source_key:
            keys.setdefault(error.entity_set, set()).add(error.source_key)
    if not entity_sets:
        entity_sets = set(previous.entity_sets)
        keys = None
    return start_job(
        state,
        job_type="retry",
        entity_sets=sorted(entity_sets),
        mode=previous.mode or "full",
        dry_run=False,
        batch_size=state.settings.ingestion_batch_size,
        only_source_keys=keys or None,
    )


def execute_query(state: AppState, *, query_id: str | None, cypher: str | None, parameters: dict | None) -> dict:
    started = time.perf_counter()
    library = {item.id: item for item in state.queries}
    limit = state.settings.query_max_rows
    if query_id:
        definition = library.get(query_id)
        if definition is None:
            raise NotFoundError(f"Query '{query_id}' is not in the library.")
        text = validate_readonly_cypher(definition.cypher)
        params = resolve_query_params(definition, parameters)
        if "limit" in params:
            limit = min(int(params["limit"]), state.settings.query_max_rows)
            params["limit"] = limit
        if state.graph.backend == "memory":
            rows = state.graph.library_rows(query_id, params, limit)
            columns = list(rows[0].keys()) if rows else []
            return _query_response(columns, rows, text, started, state.graph.backend, len(rows) >= limit)
        columns, rows, truncated = state.graph.run_cypher(
            text, params, timeout=state.settings.query_timeout_seconds, limit=limit
        )
        return _query_response(columns, rows, text, started, state.graph.backend, truncated)
    if not cypher:
        raise ValidationFailed("Provide a saved query id or a read-only Cypher statement.")
    text = validate_readonly_cypher(cypher)
    params = sanitize_parameters(parameters)
    if state.graph.backend == "memory":
        raise ConflictError(
            "Raw Cypher requires a Neo4j connection. The in-memory demo executes the saved query library only.",
            code="cypher_requires_neo4j",
        )
    columns, rows, truncated = state.graph.run_cypher(
        text, params, timeout=state.settings.query_timeout_seconds, limit=limit
    )
    return _query_response(columns, rows, text, started, state.graph.backend, truncated)


def retention_preview(state: AppState, older_than_days: int) -> dict:
    cutoff = _cutoff(older_than_days)
    return {"older_than_days": older_than_days, "cutoff": cutoff, "nodes": state.graph.count_older_than(cutoff)}


def retention_apply(state: AppState, older_than_days: int, confirm: bool) -> dict:
    if not confirm:
        raise ValidationFailed("Set confirm to true to delete aged graph nodes. This is never done automatically.")
    cutoff = _cutoff(older_than_days)
    removed = state.graph.delete_older_than(cutoff)
    return {"removed_nodes": removed, "cutoff": cutoff}


def _cutoff(days: int) -> str:
    if days < 1:
        raise ValidationFailed("Retention must be at least one day.")
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def _query_response(columns, rows, cypher, started, engine, truncated) -> dict:
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "engine": engine,
        "cypher": cypher,
    }


def _sync_schema(state: AppState, ontology) -> None:
    try:
        state.graph.sync_ontology(ontology)
    except Exception:
        logger.info("Ontology schema was saved but not written to the graph backend.")


def _ontology_or_none(state: AppState):
    try:
        return load_ontology(state.settings)
    except NotFoundError:
        return None


def _flatten(ontology) -> list[dict]:
    rows = []
    for item in ontology.classes:
        rows.append(
            {
                "kind": "class",
                "mapping_id": item.class_id,
                "natural_key": item.natural_key,
                "source_entity_type": item.source_entity_type,
                "status": item.status,
                "canonical_name": item.canonical_name,
                "signature": item.signature,
                "note": item.inference_note,
                "object": item,
            }
        )
        for prop in item.properties:
            rows.append(
                {
                    "kind": "property",
                    "mapping_id": prop.property_id,
                    "natural_key": prop.natural_key,
                    "source_entity_type": item.source_entity_type,
                    "source_property": prop.source_property,
                    "status": prop.mapping_status,
                    "canonical_name": prop.canonical_property,
                    "signature": prop.signature,
                    "note": prop.inference_note,
                    "object": prop,
                    "parent": item,
                }
            )
    for item in ontology.relationships:
        rows.append(
            {
                "kind": "relationship",
                "mapping_id": item.relationship_id,
                "natural_key": item.natural_key,
                "source_entity_type": item.source_entity,
                "navigation_property": item.navigation_property,
                "status": item.mapping_status,
                "canonical_name": None,
                "relationship_type": item.relationship_type,
                "relationship_semantics": item.relationship_semantics,
                "source_key_fields": item.source_key_fields,
                "target_key_fields": item.target_key_fields,
                "signature": item.signature,
                "note": item.inference_note,
                "object": item,
            }
        )
    return rows


def _require_mapping(ontology, mapping_id: str) -> dict:
    for item in _flatten(ontology):
        if item["mapping_id"] == mapping_id:
            return item
    raise NotFoundError("Mapping not found.")


def _locate_import(ontology, raw: dict) -> dict:
    if raw.get("mapping_id"):
        return _require_mapping(ontology, raw["mapping_id"])
    kind = raw.get("kind")
    source = raw.get("source_entity_type")
    if kind == "class":
        natural = f"class|{source}"
    elif kind == "property":
        natural = f"property|{source}|{raw.get('source_property')}"
    elif kind == "relationship":
        natural = f"relationship|{source}|{raw.get('navigation_property')}"
    else:
        raise ValidationFailed("Mapping kind must be class, property, or relationship.")
    for item in _flatten(ontology):
        if item["natural_key"] == natural:
            return item
    raise ValidationFailed(f"No discovered mapping matches {natural}.")


def _approved_review(catalog, located: dict, payload: dict) -> ReviewRecord:
    entity = catalog.type_index().get(located["source_entity_type"])
    if entity is None:
        raise ValidationFailed("The source entity is no longer in the catalog.")
    note = payload.get("note")
    if located["kind"] == "class":
        approved = validate_class_approval(
            entity,
            {
                "canonical_name": payload.get("canonical_name") or located.get("canonical_name"),
                "effective_dating_rule": payload.get("effective_dating_rule"),
                "effective_identity_field": payload.get("effective_identity_field"),
                "effective_start_field": located["object"].effective_start_field,
            },
        )
        if approved["warning"]:
            note = approved["warning"] if not note else f"{note} {approved['warning']}"
        return ReviewRecord(
            kind="class",
            natural_key=located["natural_key"],
            source_entity_type=located["source_entity_type"],
            status="approved",
            canonical_name=approved["canonical_name"],
            effective_dating_rule=approved["effective_dating_rule"],
            effective_identity_field=approved["effective_identity_field"],
            signature=located["signature"],
            note=note,
            updated_at=_now(),
        )
    if located["kind"] == "property":
        approved = validate_property_approval(
            entity,
            located["source_property"],
            {"canonical_name": payload.get("canonical_name")},
        )
        return ReviewRecord(
            kind="property",
            natural_key=located["natural_key"],
            source_entity_type=located["source_entity_type"],
            source_property=located["source_property"],
            status="approved",
            canonical_name=approved["canonical_property"],
            signature=located["signature"],
            note=note,
            updated_at=_now(),
        )
    relationship = located["object"]
    target = catalog.type_index().get(relationship.target_entity or "")
    approved = validate_relationship_approval(
        entity,
        target,
        {
            "relationship_type": payload.get("relationship_type") or relationship.relationship_semantics,
            "source_key_fields": payload.get("source_key_fields") or relationship.source_key_fields,
            "target_key_fields": payload.get("target_key_fields") or relationship.target_key_fields,
        },
    )
    return ReviewRecord(
        kind="relationship",
        natural_key=located["natural_key"],
        source_entity_type=located["source_entity_type"],
        navigation_property=located["navigation_property"],
        status="approved",
        relationship_type=approved["relationship_type"],
        source_key_fields=approved["source_key_fields"],
        target_key_fields=approved["target_key_fields"],
        signature=located["signature"],
        note=note,
        updated_at=_now(),
    )


def _review_from_import(catalog, draft, raw: dict) -> ReviewRecord:
    status = raw.get("status")
    if status not in {"approved", "rejected", "discovered", "review_required", "inferred"}:
        raise ValidationFailed("Imported mapping status is not recognized.")
    located = _locate_import(draft, raw)
    if status == "approved":
        return _approved_review(catalog, located, raw)
    if status == "rejected":
        return ReviewRecord(
            kind=located["kind"],
            natural_key=located["natural_key"],
            source_entity_type=located["source_entity_type"],
            source_property=located.get("source_property"),
            navigation_property=located.get("navigation_property"),
            status="rejected",
            canonical_name=raw.get("canonical_name"),
            relationship_type=raw.get("relationship_type") or located.get("relationship_type"),
            source_key_fields=raw.get("source_key_fields") or [],
            target_key_fields=raw.get("target_key_fields") or [],
            signature=located["signature"],
            note=raw.get("note"),
            updated_at=_now(),
        )
    return ReviewRecord(
        kind=located["kind"],
        natural_key=located["natural_key"],
        source_entity_type=located["source_entity_type"],
        status=status,
        signature=located["signature"],
        updated_at=_now(),
    )


def _upsert_review(reviews, review: ReviewRecord) -> None:
    reviews.mappings = [item for item in reviews.mappings if item.natural_key != review.natural_key]
    reviews.mappings.append(review)

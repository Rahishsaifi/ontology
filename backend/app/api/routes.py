"""HTTP API for discovery, ontology review, ingestion, and read-only graph access."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import require_admin, require_reader
from app.errors import NotFoundError, ValidationFailed
from app.services import (
    approve_mapping,
    clear_session,
    execute_query,
    export_mappings,
    generate,
    import_mappings,
    preview_entity,
    public_health,
    reject_mapping,
    retention_apply,
    retention_preview,
    retry_job,
    run_discovery,
    start_job,
    test_successfactors,
)
from app.storage import load_catalog, load_ontology

router = APIRouter(prefix="/api")


class ConnectionRequest(BaseModel):
    base_url: str | None = None
    auth_method: str | None = None
    access_token: str | None = None
    username: str | None = None
    password: str | None = None
    company_id: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    saml_assertion: str | None = None
    user_id: str | None = None
    private_key: str | None = None
    user_key: str | None = None
    idp_url: str | None = None
    remember_for_session: bool = True


class MappingDecision(BaseModel):
    canonical_name: str | None = None
    relationship_type: str | None = None
    source_key_fields: list[str] = Field(default_factory=list)
    target_key_fields: list[str] = Field(default_factory=list)
    effective_dating_rule: str | None = None
    effective_identity_field: str | None = None
    note: str | None = None


class RejectRequest(BaseModel):
    note: str | None = None


class ImportRequest(BaseModel):
    version: int | None = 1
    source_system: str | None = None
    mappings: list[dict[str, Any]]


class EntitySelection(BaseModel):
    entity_sets: list[str]
    dry_run: bool = False
    batch_size: int | None = None
    limit: int = 5


class SyncRequest(BaseModel):
    entity_sets: list[str]
    mode: str = "full"
    dry_run: bool = False
    batch_size: int | None = None


class QueryRequest(BaseModel):
    query_id: str | None = None
    cypher: str | None = None
    parameters: dict[str, Any] | None = None


class RetentionRequest(BaseModel):
    older_than_days: int
    confirm: bool = False


def state(request: Request):
    return request.app.state.ctx


@router.get("/health", tags=["system"])
def health(request: Request):
    return public_health(state(request))


@router.get("/me", tags=["system"])
def me(request: Request, role: str = Depends(require_reader)):
    return {"role": role, "demo_mode": state(request).settings.demo_mode}


@router.post("/connections/successfactors/test", tags=["connection"])
def test_connection(body: ConnectionRequest, request: Request, _: str = Depends(require_admin)):
    return test_successfactors(state(request), body.model_dump())


@router.delete("/connections/successfactors/session", tags=["connection"])
def delete_session(request: Request, _: str = Depends(require_admin)):
    return clear_session(state(request))


@router.post("/discovery/run", tags=["discovery"])
def discovery_run(request: Request, _: str = Depends(require_admin)):
    return run_discovery(state(request))


@router.get("/discovery/catalog", tags=["discovery"])
def discovery_catalog(request: Request, _: str = Depends(require_reader)):
    return load_catalog(state(request).settings)


@router.get("/discovery/entities", tags=["discovery"])
def discovery_entities(request: Request, q: str | None = None, _: str = Depends(require_reader)):
    catalog = load_catalog(state(request).settings)
    rows = []
    needle = (q or "").lower()
    for entity_set in catalog.entity_sets:
        entity = catalog.type_index().get(entity_set.entity_type)
        if entity is None:
            continue
        if needle and needle not in entity_set.name.lower() and needle not in entity.qualified_name.lower():
            continue
        unresolved = sum(1 for nav in entity.navigation_properties if not nav.resolved)
        rows.append(
            {
                "entity_set": entity_set.name,
                "entity_type": entity.qualified_name,
                "namespace": entity.namespace,
                "key": entity.key.property_names,
                "key_defined": entity.key_defined,
                "property_count": len(entity.properties),
                "navigation_count": len(entity.navigation_properties),
                "unresolved_relationships": unresolved,
                "exposed": entity.exposed,
            }
        )
    return {"entities": rows, "origin": catalog.origin, "demo_mode": catalog.origin == "synthetic_demo"}


@router.get("/discovery/entities/{entity_name}", tags=["discovery"])
def discovery_entity(entity_name: str, request: Request, _: str = Depends(require_reader)):
    catalog = load_catalog(state(request).settings)
    entity = catalog.entity_for_set(entity_name) or catalog.type_index().get(entity_name)
    if entity is None:
        raise NotFoundError(f"Entity '{entity_name}' was not discovered.")
    return entity


@router.post("/ontology/generate", tags=["ontology"])
def ontology_generate(request: Request, _: str = Depends(require_admin)):
    return generate(state(request))


@router.get("/ontology", tags=["ontology"])
def ontology_get(request: Request, _: str = Depends(require_reader)):
    return load_ontology(state(request).settings)


@router.get("/ontology/classes", tags=["ontology"])
def ontology_classes(request: Request, _: str = Depends(require_reader)):
    ontology = load_ontology(state(request).settings)
    return {"classes": ontology.classes, "concept_coverage": ontology.concept_coverage, "mapping_version": ontology.mapping_version}


@router.get("/ontology/relationships", tags=["ontology"])
def ontology_relationships(request: Request, _: str = Depends(require_reader)):
    ontology = load_ontology(state(request).settings)
    return {"relationships": ontology.relationships, "mapping_version": ontology.mapping_version}


@router.post("/ontology/mappings/import", tags=["ontology"])
def mappings_import(body: ImportRequest, request: Request, _: str = Depends(require_admin)):
    return import_mappings(state(request), body.model_dump())


@router.get("/ontology/mappings/export", tags=["ontology"])
def mappings_export(request: Request, _: str = Depends(require_reader)):
    return export_mappings(state(request))


@router.post("/ontology/mappings/{mapping_id}/approve", tags=["ontology"])
def mappings_approve(mapping_id: str, body: MappingDecision, request: Request, _: str = Depends(require_admin)):
    return approve_mapping(state(request), mapping_id, body.model_dump())


@router.post("/ontology/mappings/{mapping_id}/reject", tags=["ontology"])
def mappings_reject(mapping_id: str, body: RejectRequest, request: Request, _: str = Depends(require_admin)):
    return reject_mapping(state(request), mapping_id, body.note)


@router.post("/neo4j/test", tags=["graph"])
def neo4j_test(request: Request, _: str = Depends(require_admin)):
    try:
        return state(request).graph.test()
    except Exception as exc:
        return {"connected": False, "backend": state(request).settings.graph_backend, "detail": str(exc)}


@router.post("/ingestion/preview", tags=["ingestion"])
def ingestion_preview(body: EntitySelection, request: Request, _: str = Depends(require_admin)):
    if len(body.entity_sets) != 1:
        raise ValidationFailed("Preview one entity set at a time.")
    return preview_entity(state(request), body.entity_sets[0], body.limit)


@router.post("/ingestion/start", tags=["ingestion"])
def ingestion_start(body: EntitySelection, request: Request, _: str = Depends(require_admin)):
    return start_job(
        state(request),
        job_type="ingestion",
        entity_sets=body.entity_sets,
        mode="full",
        dry_run=body.dry_run,
        batch_size=body.batch_size,
    )


@router.get("/ingestion/jobs/{job_id}", tags=["ingestion"])
def ingestion_job(job_id: str, request: Request, _: str = Depends(require_reader)):
    job = state(request).database.get_job(job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    return job


@router.post("/ingestion/jobs/{job_id}/retry", tags=["ingestion"])
def ingestion_retry(job_id: str, request: Request, _: str = Depends(require_admin)):
    return retry_job(state(request), job_id)


@router.post("/sync/start", tags=["sync"])
def sync_start(body: SyncRequest, request: Request, _: str = Depends(require_admin)):
    if body.mode not in {"full", "incremental"}:
        raise ValidationFailed("Sync mode must be full or incremental.")
    return start_job(
        state(request),
        job_type="sync",
        entity_sets=body.entity_sets,
        mode=body.mode,
        dry_run=body.dry_run,
        batch_size=body.batch_size,
    )


@router.get("/sync/history", tags=["sync"])
def sync_history(request: Request, _: str = Depends(require_reader)):
    app_state = state(request)
    jobs = [
        job
        for job in app_state.database.list_jobs(limit=50)
        if job.job_type in {"sync", "ingestion", "retry"}
    ]
    return {"states": app_state.database.list_sync_states(), "jobs": jobs}


@router.get("/jobs", tags=["sync"])
def jobs(request: Request, _: str = Depends(require_reader)):
    return {"jobs": state(request).database.list_jobs(limit=30)}


@router.get("/graph/summary", tags=["graph"])
def graph_summary(request: Request, _: str = Depends(require_reader)):
    summary = state(request).graph.summary()
    summary["demo_mode"] = state(request).settings.demo_mode
    return summary


@router.get("/graph/nodes", tags=["graph"])
def graph_nodes(
    request: Request,
    entity_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
    _: str = Depends(require_reader),
):
    capped = max(1, min(limit, 200))
    return {"nodes": state(request).graph.list_nodes(entity_type=entity_type, query=q, limit=capped)}


@router.get("/graph/neighborhood/{entity_type}/{source_key:path}", tags=["graph"])
def graph_neighborhood(entity_type: str, source_key: str, request: Request, _: str = Depends(require_reader)):
    return state(request).graph.neighborhood(entity_type, source_key)


@router.get("/graph/explore", tags=["graph"])
def graph_explore(
    request: Request,
    entity_types: str | None = None,
    limit: int = 80,
    _: str = Depends(require_reader),
):
    types = [part.strip() for part in (entity_types or "").split(",") if part.strip()] or None
    capped = max(1, min(limit, 200))
    return state(request).graph.explore(entity_types=types, limit=capped)


@router.get("/graph/queries", tags=["graph"])
def graph_queries(request: Request, _: str = Depends(require_reader)):
    return {
        "queries": [item.model_dump() for item in state(request).queries],
        "engine": state(request).graph.backend,
    }


@router.post("/graph/query", tags=["graph"])
def graph_query(body: QueryRequest, request: Request, _: str = Depends(require_reader)):
    return execute_query(
        state(request),
        query_id=body.query_id,
        cypher=body.cypher,
        parameters=body.parameters,
    )


@router.post("/admin/retention/preview", tags=["admin"])
def admin_retention_preview(body: RetentionRequest, request: Request, _: str = Depends(require_admin)):
    return retention_preview(state(request), body.older_than_days)


@router.post("/admin/retention/apply", tags=["admin"])
def admin_retention_apply(body: RetentionRequest, request: Request, _: str = Depends(require_admin)):
    return retention_apply(state(request), body.older_than_days, body.confirm)

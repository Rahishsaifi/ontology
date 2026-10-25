"""Neo4j Community Edition store.

Community Edition does not support multi-property node-key constraints.
Uniqueness is enforced on a deterministic identity that is the composite of
sourceSystem, entityType, and sourceKey. Labels and relationship types used
here are fixed constants, never values taken from metadata.
"""

from __future__ import annotations

from app.errors import GraphError, NotFoundError, TransientGraphError
from app.graph.models import EntityUpsert, RelationshipUpsert
from app.mapping.keys import composite_identity
from app.ontology.canonical import BUSINESS_REL_TYPES
from app.redaction import redact_text

ENTITY_CONSTRAINT = """
CREATE CONSTRAINT sf_entity_identity IF NOT EXISTS
FOR (n:SFEntity) REQUIRE n.identity IS UNIQUE
"""
CLASS_CONSTRAINT = """
CREATE CONSTRAINT ontology_class_identity IF NOT EXISTS
FOR (n:OntologyClass) REQUIRE n.identity IS UNIQUE
"""
PROPERTY_CONSTRAINT = """
CREATE CONSTRAINT ontology_property_identity IF NOT EXISTS
FOR (n:OntologyProperty) REQUIRE n.identity IS UNIQUE
"""
RELATION_CONSTRAINT = """
CREATE CONSTRAINT ontology_relation_identity IF NOT EXISTS
FOR (n:OntologyRelation) REQUIRE n.identity IS UNIQUE
"""

UPSERT_ENTITIES = """
UNWIND $rows AS row
MERGE (n:SFEntity {identity: row.identity})
SET n.sourceSystem = row.sourceSystem,
    n.entityType = row.entityType,
    n.sourceKey = row.sourceKey,
    n.lastSyncedAt = row.lastSyncedAt,
    n.canonicalClass = row.canonicalClass,
    n.displayLabel = row.displayLabel,
    n.effectiveStart = row.effectiveStart,
    n.effectiveEnd = row.effectiveEnd,
    n.sourceModifiedAt = row.sourceModifiedAt,
    n.provenance = row.provenance
SET n += row.properties
"""

_REL_TEMPLATE = """
UNWIND $rows AS row
MATCH (a:SFEntity {identity: row.sourceIdentity})
MATCH (b:SFEntity {identity: row.targetIdentity})
MERGE (a)-[r:%s {mappingId: row.mappingId, targetIdentity: row.targetIdentity}]->(b)
SET r.navigationProperty = row.navigationProperty,
    r.syncedAt = row.syncedAt,
    r.provenance = 'approved_mapping'
"""

_RECONCILE_TEMPLATE = """
MATCH (a:SFEntity {entityType: $entityType, sourceSystem: $sourceSystem})-[r:%s {mappingId: $mappingId}]->(b:SFEntity)
WHERE NOT (a.sourceKey + '\t' + b.sourceKey) IN $pairs
WITH collect(r) AS rels
FOREACH (rel IN rels | DELETE rel)
RETURN size(rels) AS removed
"""

RELATION_QUERIES = {name: _REL_TEMPLATE % name for name in sorted(BUSINESS_REL_TYPES)}
RECONCILE_QUERIES = {name: _RECONCILE_TEMPLATE % name for name in sorted(BUSINESS_REL_TYPES)}


def _row(entity: EntityUpsert) -> dict:
    return {
        "identity": entity.identity,
        "sourceSystem": entity.source_system,
        "entityType": entity.entity_type,
        "sourceKey": entity.source_key,
        "lastSyncedAt": entity.last_synced_at,
        "canonicalClass": entity.canonical_class,
        "displayLabel": entity.display_label,
        "effectiveStart": entity.effective_start,
        "effectiveEnd": entity.effective_end,
        "sourceModifiedAt": entity.source_modified_at,
        "provenance": entity.provenance,
        "properties": entity.properties,
    }


class Neo4jGraphStore:
    backend = "neo4j"

    def __init__(self, uri: str, user: str, password: str, source_system: str) -> None:
        self.uri = uri
        self.user = user
        self._password = password
        self.source_system = source_system
        self._driver = None

    def __repr__(self) -> str:
        return f"Neo4jGraphStore(uri={self.uri!r}, user={self.user!r})"

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _connect(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise GraphError("The Neo4j driver is not installed.") from exc
        if not self._password:
            raise GraphError("NEO4J_PASSWORD is not configured.")

        candidates = _uri_candidates(self.uri)
        last_error: Exception | None = None
        for uri in candidates:
            driver = GraphDatabase.driver(uri, auth=(self.user, self._password))
            try:
                driver.verify_connectivity()
                # Aura bolt+s often verifies but cannot open the tenant DB without routing.
                with driver.session() as session:
                    session.run("RETURN 1 AS ok").consume()
                self.uri = uri
                self._driver = driver
                return self._driver
            except Exception as exc:
                last_error = exc
                try:
                    driver.close()
                except Exception:
                    pass
                continue

        message = "Neo4j connection failed."
        if last_error and _is_routing_failure(last_error):
            message = (
                "Neo4j Aura needs neo4j+s:// routing to open the tenant database. "
                "Set NEO4J_URI=neo4j+s://YOUR_ID.databases.neo4j.io (not bolt+s://). "
                "If your office network blocks routing, use GRAPH_BACKEND=memory or allow "
                "*.databases.neo4j.io."
            )
        elif last_error:
            message = f"Neo4j connection failed: {redact_text(str(last_error))[:180]}"
        raise GraphError(message) from last_error

    def _reset_driver(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

    def _run(self, query: str, params: dict | None = None, *, write: bool = False):
        driver = self._connect()
        try:
            with driver.session() as session:
                if write:
                    return session.execute_write(lambda tx: list(tx.run(query, params or {})))
                return session.execute_read(lambda tx: list(tx.run(query, params or {})))
        except GraphError:
            raise
        except Exception as exc:
            self._reset_driver()
            detail = redact_text(str(exc)).strip() or "unknown Neo4j error"
            text = detail.lower()
            if _is_routing_failure(exc) or "routing" in text:
                raise GraphError(
                    "Neo4j could not retrieve routing information. "
                    "On office networks set NEO4J_URI to bolt+s://YOUR_ID.databases.neo4j.io "
                    "or use GRAPH_BACKEND=memory."
                ) from exc
            if any(
                token in text
                for token in (
                    "unavailable",
                    "timeout",
                    "defunct",
                    "connection refused",
                    "failed to",
                    "serviceunavailable",
                    "cannot resolve",
                    "nodename nor servname",
                )
            ):
                raise TransientGraphError(f"Neo4j is temporarily unavailable: {detail[:180]}") from exc
            raise GraphError(f"Neo4j request failed: {detail[:180]}") from exc

    def init_schema(self) -> dict:
        for statement in (ENTITY_CONSTRAINT, CLASS_CONSTRAINT, PROPERTY_CONSTRAINT, RELATION_CONSTRAINT):
            self._run(statement, write=True)
        return {
            "backend": self.backend,
            "constraints": [
                "SFEntity.identity unique composite of sourceSystem, entityType, and sourceKey",
                "OntologyClass.identity unique",
                "OntologyProperty.identity unique",
                "OntologyRelation.identity unique",
            ],
            "note": (
                "Neo4j Community Edition uses a single-property uniqueness constraint. "
                "The identity value is the deterministic composite key."
            ),
        }

    def contains(self, identity: str) -> bool:
        records = self._run(
            "MATCH (n:SFEntity {identity: $identity}) RETURN count(n) AS count",
            {"identity": identity},
        )
        return bool(records and records[0]["count"])

    def test(self) -> dict:
        try:
            self._reset_driver()
            self._run("RETURN 1 AS ok")
        except (GraphError, TransientGraphError) as exc:
            return {
                "connected": False,
                "backend": self.backend,
                "ephemeral": False,
                "detail": exc.message,
            }
        return {
            "connected": True,
            "backend": self.backend,
            "ephemeral": False,
            "detail": f"Neo4j accepted a read query via {self.uri}.",
        }

    def upsert_entities(self, rows: list[EntityUpsert]) -> int:
        if not rows:
            return 0
        try:
            self._run(UPSERT_ENTITIES, {"rows": [_row(row) for row in rows]}, write=True)
            return len(rows)
        except TransientGraphError:
            raise
        except GraphError:
            written = 0
            for row in rows:
                self._run(UPSERT_ENTITIES, {"rows": [_row(row)]}, write=True)
                written += 1
            return written

    def upsert_relationships(self, rows: list[RelationshipUpsert]) -> tuple[int, int]:
        written = 0
        missing = 0
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            if row.relationship_type not in RELATION_QUERIES:
                raise GraphError("The relationship type is not in the allowlist.")
            grouped.setdefault(row.relationship_type, []).append(
                {
                    "sourceIdentity": row.source_identity,
                    "targetIdentity": row.target_identity,
                    "mappingId": row.mapping_id,
                    "navigationProperty": row.navigation_property,
                    "syncedAt": row.synced_at,
                }
            )
        for relationship_type, payload in grouped.items():
            before = self._count_edges(relationship_type, [item["mappingId"] for item in payload])
            self._run(RELATION_QUERIES[relationship_type], {"rows": payload}, write=True)
            after = self._count_edges(relationship_type, [item["mappingId"] for item in payload])
            # MATCH misses absent endpoints, so the delta under-counts repeats.
            # Count a row as missing when its endpoints are not both present.
            present = self._present_identities([item["sourceIdentity"] for item in payload] + [item["targetIdentity"] for item in payload])
            for item in payload:
                if item["sourceIdentity"] in present and item["targetIdentity"] in present:
                    written += 1
                else:
                    missing += 1
            _ = before, after
        return written, missing

    def _present_identities(self, identities: list[str]) -> set[str]:
        records = self._run(
            "MATCH (n:SFEntity) WHERE n.identity IN $ids RETURN n.identity AS identity",
            {"ids": list(set(identities))},
        )
        return {record["identity"] for record in records}

    def _count_edges(self, relationship_type: str, mapping_ids: list[str]) -> int:
        if relationship_type not in BUSINESS_REL_TYPES:
            return 0
        query = f"MATCH ()-[r:{relationship_type}]->() WHERE r.mappingId IN $ids RETURN count(r) AS count"
        records = self._run(query, {"ids": mapping_ids})
        return records[0]["count"] if records else 0

    def reconcile_relationships(
        self,
        *,
        relationship_type: str,
        mapping_id: str,
        entity_type: str,
        source_system: str,
        pairs: set[tuple[str, str]],
    ) -> int:
        if relationship_type not in RECONCILE_QUERIES:
            raise GraphError("The relationship type is not in the allowlist.")
        encoded = [f"{source}\t{target}" for source, target in pairs]
        records = self._run(
            RECONCILE_QUERIES[relationship_type],
            {
                "entityType": entity_type,
                "sourceSystem": source_system,
                "mappingId": mapping_id,
                "pairs": encoded,
            },
            write=True,
        )
        return records[0]["removed"] if records else 0

    def sync_ontology(self, ontology) -> None:
        class_rows = []
        property_rows = []
        relation_rows = []
        for item in ontology.classes:
            class_rows.append(
                {
                    "identity": item.class_id,
                    "classId": item.class_id,
                    "sourceEntityType": item.source_entity_type,
                    "canonicalName": item.canonical_name,
                    "status": item.status,
                    "namespace": item.namespace,
                }
            )
            for prop in item.properties:
                property_rows.append(
                    {
                        "identity": prop.property_id,
                        "classId": item.class_id,
                        "sourceProperty": prop.source_property,
                        "canonicalProperty": prop.canonical_property,
                        "dataType": prop.data_type,
                        "status": prop.mapping_status,
                        "sensitive": prop.sensitive,
                    }
                )
        for item in ontology.relationships:
            relation_rows.append(
                {
                    "identity": item.relationship_id,
                    "classId": next((cls.class_id for cls in ontology.classes if cls.source_entity_type == item.source_entity), ""),
                    "navigationProperty": item.navigation_property,
                    "targetEntity": item.target_entity,
                    "relationshipType": item.relationship_type,
                    "status": item.mapping_status,
                    "multiplicity": item.target_multiplicity,
                }
            )
        self._run(
            """
            UNWIND $rows AS row
            MERGE (n:OntologyClass {identity: row.identity})
            SET n.classId = row.classId, n.sourceEntityType = row.sourceEntityType,
                n.canonicalName = row.canonicalName, n.status = row.status, n.namespace = row.namespace
            """,
            {"rows": class_rows},
            write=True,
        )
        self._run(
            """
            UNWIND $rows AS row
            MERGE (n:OntologyProperty {identity: row.identity})
            SET n.sourceProperty = row.sourceProperty, n.canonicalProperty = row.canonicalProperty,
                n.dataType = row.dataType, n.status = row.status, n.sensitive = row.sensitive
            WITH n, row
            MATCH (c:OntologyClass {identity: row.classId})
            MERGE (c)-[:HAS_PROPERTY]->(n)
            """,
            {"rows": property_rows},
            write=True,
        )
        self._run(
            """
            UNWIND $rows AS row
            MERGE (n:OntologyRelation {identity: row.identity})
            SET n.navigationProperty = row.navigationProperty, n.targetEntity = row.targetEntity,
                n.relationshipType = row.relationshipType, n.status = row.status, n.multiplicity = row.multiplicity
            WITH n, row
            MATCH (c:OntologyClass {identity: row.classId})
            MERGE (c)-[:HAS_RELATION]->(n)
            """,
            {"rows": relation_rows},
            write=True,
        )

    def summary(self) -> dict:
        records = self._run(
            """
            MATCH (n:SFEntity)
            RETURN n.entityType AS entityType, count(n) AS count
            """
        )
        by_type = [{"entity_type": record["entityType"], "count": record["count"]} for record in records]
        rel_records = self._run(
            """
            MATCH ()-[r]->()
            WHERE type(r) IN $types
            RETURN type(r) AS relationshipType, count(r) AS count
            """,
            {"types": sorted(BUSINESS_REL_TYPES)},
        )
        nodes = self._run("MATCH (n:SFEntity) RETURN count(n) AS count")
        schema = self._run("MATCH (n:OntologyClass) RETURN count(n) AS count")
        return {
            "backend": self.backend,
            "ephemeral": False,
            "nodes": nodes[0]["count"] if nodes else 0,
            "relationships": sum(record["count"] for record in rel_records),
            "schema_classes": schema[0]["count"] if schema else 0,
            "by_entity_type": by_type,
            "by_relationship": [
                {"relationship_type": record["relationshipType"], "count": record["count"]}
                for record in rel_records
            ],
        }

    def list_nodes(self, *, entity_type: str | None, query: str | None, limit: int) -> list[dict]:
        records = self._run(
            """
            MATCH (n:SFEntity)
            WHERE ($entityType IS NULL OR n.entityType = $entityType)
              AND ($query IS NULL OR toLower(n.sourceKey) CONTAINS toLower($query)
                   OR toLower(n.displayLabel) CONTAINS toLower($query))
            RETURN n
            ORDER BY n.entityType, n.sourceKey
            LIMIT $limit
            """,
            {"entityType": entity_type, "query": query, "limit": limit},
        )
        return [_node_from_record(record["n"]) for record in records]

    def neighborhood(self, entity_type: str, source_key: str, *, limit: int = 100) -> dict:
        identity = composite_identity(self.source_system, entity_type, source_key)
        records = self._run(
            """
            MATCH (n:SFEntity {identity: $identity})
            OPTIONAL MATCH (n)-[r]-(m:SFEntity)
            WHERE type(r) IN $types OR r IS NULL
            RETURN n, r, m
            LIMIT $limit
            """,
            {"identity": identity, "types": sorted(BUSINESS_REL_TYPES), "limit": limit},
        )
        if not records or records[0]["n"] is None:
            raise NotFoundError("No graph node exists for that entity type and source key.")
        center = _node_from_record(records[0]["n"])
        nodes = {center["identity"]: center}
        edges = []
        for record in records:
            if record["m"] is not None:
                node = _node_from_record(record["m"])
                nodes[node["identity"]] = node
            if record["r"] is not None:
                edges.append(_edge_from_record(record["r"], records[0]["n"], record["m"]))
        return {"center": center, "nodes": list(nodes.values()), "edges": edges}

    def run_cypher(self, cypher: str, params: dict, *, timeout: float, limit: int) -> tuple[list[str], list[dict], bool]:
        driver = self._connect()
        try:
            from neo4j import Query
        except ImportError as exc:
            raise GraphError("The Neo4j driver is not installed.") from exc

        def work(tx):
            result = tx.run(Query(cypher, timeout=timeout), params)
            columns = list(result.keys())
            rows = []
            truncated = False
            for index, record in enumerate(result):
                if index >= limit:
                    truncated = True
                    break
                rows.append({key: _jsonable(record[key]) for key in columns})
            return columns, rows, truncated

        try:
            with driver.session() as session:
                return session.execute_read(work)
        except Exception as exc:
            text = str(exc).lower()
            if "writing" in text or "read" in text and "not supported" in text:
                raise GraphError("Neo4j rejected the query in a read transaction.") from exc
            if any(token in text for token in ("unavailable", "timeout", "defunct")):
                raise TransientGraphError("Neo4j is temporarily unavailable.") from exc
            raise GraphError("The read-only query failed.") from exc

    def delete_older_than(self, cutoff: str) -> int:
        records = self._run(
            """
            MATCH (n:SFEntity)
            WHERE n.lastSyncedAt < $cutoff
            DETACH DELETE n
            RETURN count(n) AS removed
            """,
            {"cutoff": cutoff},
            write=True,
        )
        return records[0]["removed"] if records else 0

    def count_older_than(self, cutoff: str) -> int:
        records = self._run(
            """
            MATCH (n:SFEntity)
            WHERE n.lastSyncedAt < $cutoff
            RETURN count(n) AS count
            """,
            {"cutoff": cutoff},
        )
        return records[0]["count"] if records else 0


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "labels") and hasattr(value, "items"):
        return {
            "labels": sorted(value.labels),
            "properties": {key: _jsonable(item) for key, item in dict(value).items()},
        }
    if hasattr(value, "type") and hasattr(value, "start_node"):
        return {"type": value.type, "properties": {key: _jsonable(item) for key, item in dict(value).items()}}
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            return str(value)
    return str(value)


def _node_from_record(node) -> dict:
    properties = {key: _jsonable(value) for key, value in dict(node).items()}
    business = {
        key: value
        for key, value in properties.items()
        if key
        not in {
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
    }
    return {
        "identity": properties.get("identity"),
        "source_system": properties.get("sourceSystem"),
        "entity_type": properties.get("entityType"),
        "source_key": properties.get("sourceKey"),
        "canonical_class": properties.get("canonicalClass"),
        "display_label": properties.get("displayLabel"),
        "effective_start": properties.get("effectiveStart"),
        "effective_end": properties.get("effectiveEnd"),
        "source_modified_at": properties.get("sourceModifiedAt"),
        "last_synced_at": properties.get("lastSyncedAt"),
        "provenance": properties.get("provenance"),
        "properties": business,
    }


def _edge_from_record(relationship, source, target) -> dict:
    source_props = dict(source) if source is not None else {}
    target_props = dict(target) if target is not None else {}
    props = dict(relationship)
    return {
        "relationship_type": relationship.type,
        "mapping_id": props.get("mappingId"),
        "navigation_property": props.get("navigationProperty"),
        "source_key": source_props.get("sourceKey"),
        "source_entity_type": source_props.get("entityType"),
        "target_key": target_props.get("sourceKey"),
        "target_entity_type": target_props.get("entityType"),
        "provenance": props.get("provenance") or "approved_mapping",
        "synced_at": props.get("syncedAt"),
    }

def _uri_candidates(uri: str) -> list[str]:
    """Aura needs neo4j+s routing to reach the tenant database.

    bolt+s can verify TLS but then fail with DatabaseNotFound because the
    direct host is not the routed database member. Prefer neo4j+s for Aura.
    """
    cleaned = (uri or "").strip()
    if not cleaned:
        return []
    out: list[str] = []

    def add(value: str) -> None:
        if value and value not in out:
            out.append(value)

    aura = "databases.neo4j.io" in cleaned.lower()
    if cleaned.startswith("bolt+s://") and aura:
        add("neo4j+s://" + cleaned[len("bolt+s://") :])
        add(cleaned)
    elif cleaned.startswith("neo4j+s://"):
        add(cleaned)
        add("bolt+s://" + cleaned[len("neo4j+s://") :])
    elif cleaned.startswith("neo4j://"):
        add(cleaned)
        add("bolt://" + cleaned[len("neo4j://") :])
    else:
        add(cleaned)
    return out


def _is_routing_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "routing" in text
        or "unable to retrieve routing information" in text
        or "databasenotfound" in text
        or "database not found" in text
    )

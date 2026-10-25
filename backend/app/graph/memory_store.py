"""Process-local graph used by demo mode and tests. It is not a substitute for Neo4j."""

from __future__ import annotations

from collections import Counter

from app.errors import NotFoundError
from app.graph.models import EntityUpsert, RelationshipUpsert
from app.mapping.keys import composite_identity


class MemoryGraphStore:
    backend = "memory"

    def __init__(self, source_system: str) -> None:
        self.source_system = source_system
        self.nodes: dict[str, EntityUpsert] = {}
        self.edges: dict[tuple, RelationshipUpsert] = {}
        self.schema: dict[str, dict] = {}

    def close(self) -> None:
        return None

    def contains(self, identity: str) -> bool:
        return identity in self.nodes

    def init_schema(self) -> dict:
        return {
            "backend": self.backend,
            "constraints": ["memory identity map on (sourceSystem, entityType, sourceKey)"],
            "note": "In-memory graph. Data is ephemeral. Neo4j Community Edition is the durable backend.",
        }

    def test(self) -> dict:
        return {"connected": True, "backend": self.backend, "ephemeral": True, "detail": "In-memory demo graph."}

    def upsert_entities(self, rows: list[EntityUpsert]) -> int:
        for row in rows:
            self.nodes[row.identity] = row
        return len(rows)

    def upsert_relationships(self, rows: list[RelationshipUpsert]) -> tuple[int, int]:
        written = 0
        missing = 0
        for row in rows:
            if row.source_identity not in self.nodes or row.target_identity not in self.nodes:
                missing += 1
                continue
            key = (row.relationship_type, row.source_identity, row.target_identity, row.mapping_id)
            self.edges[key] = row
            written += 1
        return written, missing

    def reconcile_relationships(
        self,
        *,
        relationship_type: str,
        mapping_id: str,
        entity_type: str,
        source_system: str,
        pairs: set[tuple[str, str]],
    ) -> int:
        removed = 0
        for key, edge in list(self.edges.items()):
            if edge.relationship_type != relationship_type or edge.mapping_id != mapping_id:
                continue
            source = self.nodes.get(edge.source_identity)
            target = self.nodes.get(edge.target_identity)
            if source is None or source.entity_type != entity_type or source.source_system != source_system:
                continue
            pair = (source.source_key, target.source_key if target else "")
            if pair not in pairs:
                del self.edges[key]
                removed += 1
        return removed

    def sync_ontology(self, ontology) -> None:
        self.schema = {
            "ontology_id": ontology.ontology_id,
            "classes": [item.model_dump(mode="json") for item in ontology.classes],
            "relationships": [item.model_dump(mode="json") for item in ontology.relationships],
        }

    def summary(self) -> dict:
        by_type = Counter(node.entity_type for node in self.nodes.values())
        by_rel = Counter(edge.relationship_type for edge in self.edges.values())
        return {
            "backend": self.backend,
            "ephemeral": True,
            "nodes": len(self.nodes),
            "relationships": len(self.edges),
            "schema_classes": len(self.schema.get("classes", [])),
            "by_entity_type": [
                {"entity_type": key, "count": value} for key, value in sorted(by_type.items())
            ],
            "by_relationship": [
                {"relationship_type": key, "count": value} for key, value in sorted(by_rel.items())
            ],
        }

    def list_nodes(self, *, entity_type: str | None, query: str | None, limit: int) -> list[dict]:
        rows = list(self.nodes.values())
        if entity_type:
            rows = [row for row in rows if row.entity_type == entity_type]
        if query:
            needle = query.lower()
            rows = [
                row
                for row in rows
                if needle in row.source_key.lower() or needle in row.display_label.lower()
            ]
        rows.sort(key=lambda row: (row.entity_type, row.source_key))
        return [_public_node(row) for row in rows[:limit]]

    def neighborhood(self, entity_type: str, source_key: str, *, limit: int = 100) -> dict:
        identity = composite_identity(self.source_system, entity_type, source_key)
        center = self.nodes.get(identity)
        if center is None:
            raise NotFoundError("No graph node exists for that entity type and source key.")
        nodes = {identity: center}
        edges = []
        for edge in self.edges.values():
            if edge.source_identity != identity and edge.target_identity != identity:
                continue
            other_id = edge.target_identity if edge.source_identity == identity else edge.source_identity
            other = self.nodes.get(other_id)
            if other:
                nodes[other_id] = other
            edges.append(_public_edge(edge, self.nodes))
            if len(edges) >= limit:
                break
        return {
            "center": _public_node(center),
            "nodes": [_public_node(node) for node in nodes.values()],
            "edges": edges,
        }

    def library_rows(self, query_id: str, params: dict, limit: int) -> list[dict]:
        if query_id == "entities-by-type":
            counts = Counter(node.entity_type for node in self.nodes.values())
            rows = [{"entityType": key, "count": value} for key, value in counts.items()]
            rows.sort(key=lambda item: item["count"], reverse=True)
            return rows[:limit]
        if query_id == "reporting-lines":
            return self._edge_rows("REPORTS_TO", limit)
        if query_id == "effective-dated-jobs":
            entity_type = params.get("entityType") or "SFOData.EmpJob"
            rows = [
                {
                    "sourceKey": node.source_key,
                    "effectiveStart": node.effective_start,
                    "effectiveEnd": node.effective_end,
                    "displayLabel": node.display_label,
                }
                for node in self.nodes.values()
                if node.entity_type == entity_type
            ]
            rows.sort(key=lambda item: item["sourceKey"])
            return rows[:limit]
        if query_id == "approved-relationships":
            rows = []
            for edge in self.edges.values():
                source = self.nodes.get(edge.source_identity)
                target = self.nodes.get(edge.target_identity)
                if not source or not target:
                    continue
                rows.append(
                    {
                        "relationshipType": edge.relationship_type,
                        "sourceType": source.entity_type,
                        "sourceKey": source.source_key,
                        "targetType": target.entity_type,
                        "targetKey": target.source_key,
                        "mappingId": edge.mapping_id,
                    }
                )
            return rows[:limit]
        raise NotFoundError(f"Query '{query_id}' is not in the library.")

    def _edge_rows(self, relationship_type: str, limit: int) -> list[dict]:
        rows = []
        for edge in self.edges.values():
            if edge.relationship_type != relationship_type:
                continue
            source = self.nodes.get(edge.source_identity)
            target = self.nodes.get(edge.target_identity)
            if not source or not target:
                continue
            rows.append(
                {
                    "sourceType": source.entity_type,
                    "sourceKey": source.source_key,
                    "targetType": target.entity_type,
                    "targetKey": target.source_key,
                    "mappingId": edge.mapping_id,
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def delete_older_than(self, cutoff: str) -> int:
        doomed = [identity for identity, node in self.nodes.items() if node.last_synced_at < cutoff]
        for identity in doomed:
            del self.nodes[identity]
        for key, edge in list(self.edges.items()):
            if edge.source_identity in doomed or edge.target_identity in doomed:
                del self.edges[key]
        return len(doomed)

    def count_older_than(self, cutoff: str) -> int:
        return sum(1 for node in self.nodes.values() if node.last_synced_at < cutoff)


def _public_node(node: EntityUpsert) -> dict:
    return {
        "identity": node.identity,
        "source_system": node.source_system,
        "entity_type": node.entity_type,
        "source_key": node.source_key,
        "canonical_class": node.canonical_class,
        "display_label": node.display_label,
        "effective_start": node.effective_start,
        "effective_end": node.effective_end,
        "source_modified_at": node.source_modified_at,
        "last_synced_at": node.last_synced_at,
        "provenance": node.provenance,
        "properties": node.properties,
    }


def _public_edge(edge: RelationshipUpsert, nodes: dict[str, EntityUpsert]) -> dict:
    source = nodes.get(edge.source_identity)
    target = nodes.get(edge.target_identity)
    return {
        "relationship_type": edge.relationship_type,
        "mapping_id": edge.mapping_id,
        "navigation_property": edge.navigation_property,
        "source_key": source.source_key if source else None,
        "source_entity_type": source.entity_type if source else None,
        "target_key": target.source_key if target else None,
        "target_entity_type": target.entity_type if target else None,
        "provenance": "approved_mapping",
        "synced_at": edge.synced_at,
    }

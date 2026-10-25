import os

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("NEO4J_INTEGRATION") != "1", reason="Set NEO4J_INTEGRATION=1 to run against local Neo4j.")
def test_neo4j_round_trip(tmp_path):
    from app.graph.models import EntityUpsert
    from app.graph.neo4j_store import Neo4jGraphStore

    store = Neo4jGraphStore(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", ""),
        "successfactors",
    )
    store.init_schema()
    store.upsert_entities(
        [
            EntityUpsert(
                identity="integration-node",
                source_system="successfactors",
                entity_type="SFOData.User",
                source_key="userId=INTEGRATION",
                last_synced_at="2024-01-01T00:00:00+00:00",
                display_label="Integration Example",
                provenance="synthetic_demo",
            )
        ]
    )
    store.upsert_entities(
        [
            EntityUpsert(
                identity="integration-node",
                source_system="successfactors",
                entity_type="SFOData.User",
                source_key="userId=INTEGRATION",
                last_synced_at="2024-02-01T00:00:00+00:00",
                display_label="Integration Example",
                provenance="synthetic_demo",
                properties={"status": "active"},
            )
        ]
    )
    rows = store.list_nodes(entity_type="SFOData.User", query="INTEGRATION", limit=10)
    assert len(rows) == 1
    assert rows[0]["properties"]["status"] == "active"
    columns, records, _truncated = store.run_cypher(
        "MATCH (n:SFEntity {identity: $identity}) RETURN n.sourceKey AS sourceKey",
        {"identity": "integration-node"},
        timeout=5,
        limit=10,
    )
    assert columns == ["sourceKey"]
    assert records[0]["sourceKey"] == "userId=INTEGRATION"
    store.close()

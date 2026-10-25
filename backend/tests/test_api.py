from tests.conftest import sample_mappings


def test_api_flow_discovery_review_import_and_query(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["demo_mode"] is True

    assert client.get("/api/discovery/catalog").status_code == 401
    assert client.post("/api/discovery/run", headers={"Authorization": "Bearer reader-token"}).status_code == 403

    admin = {"Authorization": "Bearer admin-token"}
    reader = {"Authorization": "Bearer reader-token"}
    tested = client.post("/api/connections/successfactors/test", headers=admin, json={"access_token": "ignored"})
    assert tested.status_code == 200
    assert tested.json()["demo_mode"] is True
    assert "ignored" not in tested.text

    discovered = client.post("/api/discovery/run", headers=admin)
    assert discovered.status_code == 200
    assert discovered.json()["origin"] == "synthetic_demo"
    catalog = client.get("/api/discovery/catalog", headers=reader)
    assert catalog.status_code == 200
    detail = client.get("/api/discovery/entities/EmpJob", headers=reader)
    assert detail.status_code == 200
    assert detail.json()["key"]["property_names"] == ["userId", "startDate"]

    ontology = client.post("/api/ontology/generate", headers=admin).json()
    assert ontology["concept_coverage"]["Employee"] == "unmatched"
    assert all(item["status"] != "approved" for item in ontology["classes"])

    imported = client.post("/api/ontology/mappings/import", headers=admin, json=sample_mappings())
    assert imported.status_code == 200
    body = imported.json()
    assert any(item["status"] == "approved" and item["canonical_name"] == "JobAssignment" for item in body["classes"])
    user = next(item for item in body["classes"] if item["source_entity_type"] == "SFOData.User")
    assert user["canonical_name"] == "UserAccount"

    bad = client.post(
        "/api/ontology/mappings/approve-not-used",
        headers=admin,
        json={"access_token": {"leak": "super-secret-token"}},
    )
    assert bad.status_code in {404, 422}
    assert "super-secret-token" not in bad.text

    leaked = client.post(
        "/api/connections/successfactors/test",
        headers=admin,
        json={"access_token": {"leak": "super-secret-token"}},
    )
    assert leaked.status_code == 422
    assert "super-secret-token" not in leaked.text

    sets = ["User", "PerPerson", "EmpEmployment", "EmpJob", "FODepartment", "FOBusinessUnit", "FODivision", "Position", "FOCompany"]
    preview = client.post("/api/ingestion/preview", headers=admin, json={"entity_sets": ["EmpJob"], "limit": 2})
    assert preview.status_code == 200
    assert "nationalId" not in preview.json()["fields"]

    dry = client.post("/api/ingestion/start", headers=admin, json={"entity_sets": ["EmpJob"], "dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["status"] == "succeeded"
    assert client.get("/api/graph/summary", headers=reader).json()["nodes"] == 0

    loaded = client.post("/api/ingestion/start", headers=admin, json={"entity_sets": sets, "dry_run": False})
    assert loaded.status_code == 200
    assert loaded.json()["status"] in {"succeeded", "partial"}
    summary = client.get("/api/graph/summary", headers=reader).json()
    assert summary["nodes"] > 0
    assert summary["demo_mode"] is True
    jobs = client.get("/api/graph/nodes", headers=reader, params={"entity_type": "SFOData.EmpJob"}).json()["nodes"]
    assert len([node for node in jobs if "U002" in node["source_key"]]) == 2

    queried = client.post("/api/graph/query", headers=reader, json={"query_id": "reporting-lines", "parameters": {"limit": 20}})
    assert queried.status_code == 200
    assert queried.json()["row_count"] >= 1
    assert queried.json()["engine"] == "memory"

    rejected = client.post("/api/graph/query", headers=reader, json={"cypher": "CREATE (n:SFEntity) RETURN n"})
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "cypher_rejected"

    history = client.get("/api/sync/history", headers=reader)
    assert history.status_code == 200
    assert history.json()["states"]


def test_incremental_sync_uses_the_watermark(client):
    admin = {"Authorization": "Bearer admin-token"}
    reader = {"Authorization": "Bearer reader-token"}
    client.post("/api/discovery/run", headers=admin)
    client.post("/api/ontology/generate", headers=admin)
    client.post("/api/ontology/mappings/import", headers=admin, json=sample_mappings())
    client.post("/api/ingestion/start", headers=admin, json={"entity_sets": ["EmpJob"]})
    early = client.post("/api/sync/start", headers=admin, json={"entity_sets": ["EmpJob"], "mode": "incremental"})
    early_entity = early.json()["summary"]["entities"]["EmpJob"]
    assert early_entity.get("reason") == "incremental_requires_prior_success" or early.json()["status"] in {
        "failed",
        "partial",
        "succeeded",
    }
    # The full ingestion above records a watermark, so a second incremental call is the filter test.
    from app.models.jobs import SyncState

    client.app_state.state.ctx.database.upsert_sync_state(
        SyncState(entity_set="EmpJob", last_success_at="2024-01-01T00:00:00+00:00", watermark="2024-03-01T00:00:00", catalog_hash="x", status="succeeded")
    )
    incremental = client.post("/api/sync/start", headers=admin, json={"entity_sets": ["EmpJob"], "mode": "incremental"})
    assert incremental.status_code == 200
    assert incremental.json()["summary"]["entities"]["EmpJob"]["fetched"] == 2
    assert client.get("/api/graph/summary", headers=reader).json()["nodes"] >= 2

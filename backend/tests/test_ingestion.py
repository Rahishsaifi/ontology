import json
from pathlib import Path

from app.connector.client import DemoConnector
from app.connector.demo import demo_records
from app.connector.odata import EntityPage
from app.db import Database
from app.discovery.parser import parse_edmx
from app.errors import TransientGraphError, GraphError
from app.graph.memory_store import MemoryGraphStore
from app.graph.models import EntityUpsert, RelationshipUpsert
from app.models.jobs import JobRecord
from app.ontology.generator import generate_ontology
from app.sync.runner import run_ingestion

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "samples" / "synthetic-core-hr.edmx").read_bytes()
REVIEWS = json.loads((ROOT / "samples" / "reviewed-mappings.json").read_text(encoding="utf-8"))


def build(tmp_path, graph=None):
    catalog = parse_edmx(FIXTURE, source_system="successfactors", origin="synthetic_demo")
    from app.models.ontology import ReviewRecord
    from app.services import import_mappings

    # Build reviews through the same validation used by import, without the API.
    from app.services import _review_from_import

    draft = generate_ontology(catalog, [], sensitive_patterns=["nationalid", "password", "dateofbirth", "salary"])
    reviews = [_review_from_import(catalog, draft, item) for item in REVIEWS["mappings"]]
    ontology = generate_ontology(
        catalog,
        reviews,
        sensitive_patterns=["nationalid", "password", "dateofbirth", "salary"],
    )
    connector = DemoConnector(FIXTURE, demo_records(), page_size=1)
    database = Database(tmp_path / "app.db")
    database.migrate()
    store = graph or MemoryGraphStore("successfactors")
    job = JobRecord(id="job-1", job_type="ingestion", status="pending", mode="full", entity_sets=["User"], created_at="2024-01-01T00:00:00+00:00")
    database.create_job(job)
    return catalog, ontology, connector, database, store


def test_effective_dated_jobs_stay_distinct_and_duplicates_do_not_multiply(tmp_path):
    catalog, ontology, connector, database, store = build(tmp_path)
    sets = ["User", "EmpJob", "FODepartment", "Position", "EmpEmployment", "PerPerson", "FOBusinessUnit", "FODivision", "FOCompany"]
    database.create_job(
        JobRecord(id="job-jobs", job_type="ingestion", status="pending", mode="full", entity_sets=sets, created_at="2024-01-01T00:00:00+00:00")
    )
    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=connector,
        graph=store,
        database=database,
        job_id="job-jobs",
        entity_sets=sets,
        mode="full",
        dry_run=False,
        batch_size=1,
        provenance="synthetic_demo",
    )
    jobs = [node for node in store.nodes.values() if node.entity_type == "SFOData.EmpJob" and "U002" in node.source_key]
    assert len(jobs) == 2
    assert {node.effective_start for node in jobs} == {"2020-01-01T00:00:00", "2022-06-01T00:00:00"}
    before = len(store.nodes)
    database.create_job(
        JobRecord(id="job-again", job_type="ingestion", status="pending", mode="full", entity_sets=sets, created_at="2024-01-02T00:00:00+00:00")
    )
    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=connector,
        graph=store,
        database=database,
        job_id="job-again",
        entity_sets=sets,
        mode="full",
        dry_run=False,
        batch_size=10,
        provenance="synthetic_demo",
    )
    assert len(store.nodes) == before
    user = next(node for node in store.nodes.values() if node.entity_type == "SFOData.User")
    assert "nationalId" not in user.properties
    assert "password" not in user.properties
    assert any(edge.relationship_type == "REPORTS_TO" for edge in store.edges.values())


def test_rejected_mapping_does_not_create_edges_and_failure_does_not_delete(tmp_path):
    catalog, ontology, connector, database, store = build(tmp_path)
    for item in ontology.relationships:
        if item.navigation_property == "departmentNav":
            item.mapping_status = "rejected"
    survivor = EntityUpsert(
        identity="keep",
        source_system="successfactors",
        entity_type="SFOData.FODepartment",
        source_key="externalCode=KEEP",
        last_synced_at="2020-01-01T00:00:00+00:00",
        display_label="Keep",
        provenance="synthetic_demo",
    )
    store.upsert_entities([survivor])
    store.edges[("BELONGS_TO", "keep", "keep", "old")] = RelationshipUpsert(
        relationship_type="BELONGS_TO",
        source_identity="keep",
        target_identity="keep",
        mapping_id="old",
        navigation_property="legacy",
        synced_at="2020-01-01T00:00:00+00:00",
    )

    class Boom:
        def fetch_page(self, *args, **kwargs):
            raise RuntimeError("upstream failed with Bearer super-secret-token")

    database.create_job(
        JobRecord(id="job-fail", job_type="sync", status="pending", mode="full", entity_sets=["EmpJob"], created_at="2024-01-01T00:00:00+00:00")
    )
    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=Boom(),
        graph=store,
        database=database,
        job_id="job-fail",
        entity_sets=["EmpJob"],
        mode="full",
        dry_run=False,
        batch_size=10,
        provenance="synthetic_demo",
    )
    assert store.nodes["keep"].display_label == "Keep"
    assert ("BELONGS_TO", "keep", "keep", "old") in store.edges
    job = database.get_job("job-fail")
    assert job.status == "failed"
    assert "super-secret-token" not in job.errors[0].message


def test_empty_successful_feed_does_not_delete_existing_graph(tmp_path):
    catalog, ontology, connector, database, store = build(tmp_path)
    survivor = EntityUpsert(
        identity="keep",
        source_system="successfactors",
        entity_type="SFOData.User",
        source_key="userId=KEEP",
        last_synced_at="2020-01-01T00:00:00+00:00",
        display_label="Keep",
        provenance="synthetic_demo",
    )
    store.upsert_entities([survivor])

    class Empty:
        def fetch_page(self, *args, **kwargs):
            return EntityPage(records=[], next_url=None)

    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=Empty(),
        graph=store,
        database=database,
        job_id="job-1",
        entity_sets=["User"],
        mode="full",
        dry_run=False,
        batch_size=10,
        provenance="synthetic_demo",
    )
    assert "keep" in store.nodes
    assert database.get_job("job-1").summary["entities"]["User"]["note"] == "empty_result_preserved_existing_graph"


def test_transient_batch_is_retried_and_permanent_record_failure_is_isolated(tmp_path):
    catalog, ontology, connector, database, store = build(tmp_path)

    class Flaky(MemoryGraphStore):
        def __init__(self):
            super().__init__("successfactors")
            self.calls = 0

        def upsert_entities(self, rows):
            self.calls += 1
            if self.calls == 1:
                raise TransientGraphError("temporary")
            if any("U003" in row.source_key for row in rows):
                raise GraphError("record failed")
            return super().upsert_entities(rows)

    flaky = Flaky()
    database.create_job(
        JobRecord(id="job-flaky", job_type="ingestion", status="pending", mode="full", entity_sets=["User"], created_at="2024-01-01T00:00:00+00:00")
    )
    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=DemoConnector(FIXTURE, demo_records(), page_size=10),
        graph=flaky,
        database=database,
        job_id="job-flaky",
        entity_sets=["User"],
        mode="full",
        dry_run=False,
        batch_size=10,
        provenance="synthetic_demo",
    )
    assert flaky.calls > 1
    assert any(node.source_key == "userId=U001" for node in flaky.nodes.values())
    assert all("U003" not in node.source_key for node in flaky.nodes.values())
    assert database.get_job("job-flaky").status == "partial"


def test_missing_key_record_is_rejected(tmp_path):
    catalog, ontology, connector, database, store = build(tmp_path)

    class Broken:
        def fetch_page(self, *args, **kwargs):
            return EntityPage(records=[{"displayName": "No Key"}], next_url=None)

    run_ingestion(
        catalog=catalog,
        ontology=ontology,
        connector=Broken(),
        graph=store,
        database=database,
        job_id="job-1",
        entity_sets=["User"],
        mode="full",
        dry_run=False,
        batch_size=10,
        provenance="synthetic_demo",
    )
    assert store.nodes == {}
    assert database.get_job("job-1").errors

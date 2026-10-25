from app.discovery.parser import parse_edmx
from app.ontology.generator import generate_ontology
from app.sync.runner import NON_SELECTABLE_PROPERTIES, build_select, parse_unviewable_property
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "samples" / "synthetic-core-hr.edmx").read_bytes()


def test_parse_unviewable_property_from_sf_message():
    assert parse_unviewable_property("bad property expression empjob/operation is not viewable") == "operation"
    assert parse_unviewable_property("EmpJob/operation is not viewable") == "operation"
    assert parse_unviewable_property("bad property expression FODepartment/md5Checksum") == "md5Checksum"
    assert parse_unviewable_property("connection refused") is None


def test_build_select_excludes_operation_by_default():
    catalog = parse_edmx(FIXTURE, source_system="successfactors", origin="synthetic_demo")
    ontology = generate_ontology(catalog, [], sensitive_patterns=[])
    entity = catalog.entity_for_set("EmpJob")
    assert entity is not None
    # Inject an EmpJob-like operation property if the fixture lacks it.
    if "operation" not in entity.property_map():
        from app.models.catalog import PropertyModel

        entity.properties.append(
            PropertyModel(name="operation", edm_type="Edm.String", nullable=True, sensitive=False)
        )
    ontology_class = next(item for item in ontology.classes if item.source_entity_set == "EmpJob")
    selected = build_select(entity, ontology_class, [], include_sensitive=False)
    assert "operation" not in selected
    assert "operation" in NON_SELECTABLE_PROPERTIES
    for key in entity.key.property_names:
        assert key in selected

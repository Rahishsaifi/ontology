import json
from pathlib import Path

import pytest

from app.discovery.parser import parse_edmx
from app.errors import ValidationFailed
from app.mapping.validate import validate_relationship_approval
from app.models.ontology import ReviewRecord
from app.ontology.generator import generate_ontology

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "samples" / "synthetic-core-hr.edmx").read_bytes()


def parsed():
    return parse_edmx(FIXTURE, source_system="successfactors", origin="synthetic_demo")


def test_generator_never_auto_approves_and_does_not_treat_user_as_person():
    ontology = generate_ontology(parsed(), [], sensitive_patterns=["nationalid", "password", "dateofbirth"])
    assert all(item.status != "approved" for item in ontology.classes)
    assert all(item.mapping_status != "approved" for item in ontology.relationships)
    person = next(item for item in ontology.classes if item.source_entity_type == "SFOData.PerPerson")
    assert person.canonical_name == "Person"
    assert person.status == "review_required"
    user = next(item for item in ontology.classes if item.source_entity_type == "SFOData.User")
    assert user.canonical_name is None
    assert user.status == "discovered"
    assert "not treated as a Person" in user.inference_note
    assert ontology.concept_coverage["Employee"] == "unmatched"
    assert ontology.concept_coverage["Manager"] == "relationship_only"
    national = next(prop for prop in user.properties if prop.source_property == "nationalId")
    assert national.sensitive is True
    assert national.mapping_status == "review_required"
    payroll = next(item for item in ontology.relationships if item.navigation_property == "payrollAreaNav")
    assert payroll.mapping_status == "unresolved"
    department = next(item for item in ontology.relationships if item.navigation_property == "departmentNav")
    assert department.mapping_status == "review_required"
    assert department.relationship_semantics == "BELONGS_TO"
    assert department.key_resolution == "discovered"


def test_relationship_approval_rejects_unknown_fields_and_partial_keys():
    catalog = parsed()
    job = catalog.type_index()["SFOData.EmpJob"]
    department = catalog.type_index()["SFOData.FODepartment"]
    with pytest.raises(ValidationFailed):
        validate_relationship_approval(
            job,
            department,
            {"relationship_type": "BELONGS_TO", "source_key_fields": ["missing"], "target_key_fields": ["externalCode"]},
        )
    with pytest.raises(ValidationFailed):
        validate_relationship_approval(
            job,
            None,
            {"relationship_type": "BELONGS_TO", "source_key_fields": ["department"], "target_key_fields": ["externalCode"]},
        )
    approved = validate_relationship_approval(
        job,
        department,
        {"relationship_type": "BELONGS_TO", "source_key_fields": ["department"], "target_key_fields": ["externalCode"]},
    )
    assert approved["target_key_fields"] == ["externalCode"]


def test_rejected_review_is_applied_and_signature_mismatch_clears_approval():
    catalog = parsed()
    ontology = generate_ontology(catalog, [], sensitive_patterns=["nationalid"])
    relationship = next(item for item in ontology.relationships if item.navigation_property == "departmentNav")
    rejected = ReviewRecord(
        kind="relationship",
        natural_key=relationship.natural_key,
        source_entity_type=relationship.source_entity,
        navigation_property="departmentNav",
        status="rejected",
        relationship_type="BELONGS_TO",
        signature=relationship.signature,
        note="Not in scope",
    )
    reviewed = generate_ontology(catalog, [rejected], sensitive_patterns=["nationalid"])
    updated = next(item for item in reviewed.relationships if item.navigation_property == "departmentNav")
    assert updated.mapping_status == "rejected"
    stale = rejected.model_copy(update={"signature": "not-the-signature", "status": "approved"})
    cleared = generate_ontology(catalog, [stale], sensitive_patterns=["nationalid"])
    again = next(item for item in cleared.relationships if item.navigation_property == "departmentNav")
    assert again.mapping_status != "approved"


def test_sample_mapping_file_is_valid_json():
    payload = json.loads((ROOT / "samples" / "reviewed-mappings.json").read_text(encoding="utf-8"))
    assert payload["mappings"]
    assert any(item["status"] == "rejected" for item in payload["mappings"])

from pathlib import Path

from app.discovery.parser import parse_edmx
from app.errors import ValidationFailed

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "samples" / "synthetic-core-hr.edmx").read_bytes()


def catalog():
    return parse_edmx(FIXTURE, source_system="successfactors", generated_at="2024-01-01T00:00:00+00:00")


def nav_map(entity):
    return {item.name: item for item in entity.navigation_properties}


def prop_map(entity):
    return {item.name: item for item in entity.properties}


def test_parses_entity_sets_and_types():
    parsed = catalog()
    names = {item.name for item in parsed.entity_sets}
    assert {"User", "EmpJob", "FODepartment", "VendorNote", "UnkeyedCustom"} <= names
    assert "SFOData" in parsed.schemas
    assert "SFODataExt" in parsed.schemas
    assert len(parsed.containers) == 2


def test_composite_key_and_types():
    parsed = catalog()
    job = parsed.type_index()["SFOData.EmpJob"]
    assert job.key.property_names == ["userId", "startDate"]
    props = prop_map(job)
    assert props["userId"].nullable is False
    assert props["userId"].edm_type == "Edm.String"
    assert props["endDate"].nullable is True
    assert props["endDate"].edm_type == "Edm.DateTime"
    assert props["seqNumber"].edm_type == "Edm.Int32"
    assert props["fte"].edm_type == "Edm.Decimal"
    assert props["fte"].precision == 10
    assert props["fte"].scale == 2
    user = parsed.type_index()["SFOData.User"]
    assert prop_map(user)["displayName"].nullable is True
    assert prop_map(user)["displayName"].max_length == 100
    assert prop_map(user)["displayName"].extensions["label"] == "Display Name"
    assert prop_map(user)["homeAddress"].edm_type == "SFOData.Address"
    assert all(item.name != "Address" for item in parsed.entity_types)


def test_namespace_qualified_association_and_roles():
    parsed = catalog()
    department = nav_map(parsed.type_index()["SFOData.EmpJob"])["departmentNav"]
    assert department.resolved is True
    assert department.target_entity_type == "SFOData.FODepartment"
    assert department.target_multiplicity == "0..1"
    assert department.source_multiplicity == "*"
    assert department.key_resolution == "discovered"
    assert department.source_key_fields == ["department"]
    assert department.target_key_fields == ["externalCode"]
    manager = nav_map(parsed.type_index()["SFOData.User"])["manager"]
    assert manager.target_entity_type == "SFOData.User"
    assert manager.source_key_fields == ["managerId"]
    assert manager.target_key_fields == ["userId"]


def test_unqualified_association_name_resolves_when_unique():
    parsed = catalog()
    person = nav_map(parsed.type_index()["SFOData.PerPersonal"])["personNav"]
    assert person.resolved is True
    assert person.target_entity_type == "SFOData.PerPerson"


def test_unresolved_navigation_and_missing_key():
    parsed = catalog()
    payroll = nav_map(parsed.type_index()["SFOData.EmpJob"])["payrollAreaNav"]
    assert payroll.resolved is False
    assert payroll.unresolved_reason == "association_not_found"
    assert payroll.key_resolution == "unresolved"
    unkeyed = parsed.type_index()["SFOData.UnkeyedCustom"]
    assert unkeyed.key_defined is False
    assert unkeyed.exposed is True
    shadow = parsed.type_index()["SFODataExt.AuditShadow"]
    assert shadow.exposed is False
    assert parsed.type_index()["SFODataExt.VendorNote"].exposed is True


def test_external_references_are_not_instructions_to_fetch():
    parsed = catalog()
    assert any(item.startswith("external_edmx_reference_ignored:") for item in parsed.warnings)
    assert any("169.254.169.254" in item for item in parsed.warnings)


def test_metadata_hash_is_stable():
    assert catalog().metadata_hash == catalog().metadata_hash


def test_entity_expansion_is_not_trusted():
    xml = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe "EXPANDED">]>
    <edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
      <edmx:DataServices>
        <Schema Namespace="SFOData" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
          <EntityType Name="User">
            <Key><PropertyRef Name="userId"/></Key>
            <Property Name="&xxe;" Type="Edm.String" Nullable="false"/>
          </EntityType>
        </Schema>
      </edmx:DataServices>
    </edmx:Edmx>
    """
    try:
        parsed = parse_edmx(xml)
    except ValidationFailed:
        return
    names = [prop.name for entity in parsed.entity_types for prop in entity.properties]
    assert "EXPANDED" not in names


def test_composite_referential_constraint():
    parsed = catalog()
    employment = nav_map(parsed.type_index()["SFOData.EmpJob"])["employmentNav"]
    assert employment.source_key_fields == ["userId", "startDate"]
    assert employment.target_key_fields == ["userId", "startDate"]
    assert employment.target_entity_type == "SFOData.EmpEmployment"

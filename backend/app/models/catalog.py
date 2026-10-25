"""Normalized SuccessFactors schema catalog."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PropertyModel(BaseModel):
    name: str
    edm_type: str
    nullable: bool = True
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    sensitive: bool = False
    extensions: dict[str, str] = Field(default_factory=dict)


class KeyModel(BaseModel):
    property_names: list[str] = Field(default_factory=list)


class AssociationEndModel(BaseModel):
    role: str
    type_name: str
    multiplicity: str | None = None


class ReferentialModel(BaseModel):
    principal_role: str
    dependent_role: str
    principal_fields: list[str]
    dependent_fields: list[str]


class AssociationModel(BaseModel):
    name: str
    namespace: str
    qualified_name: str
    ends: list[AssociationEndModel]
    referential: ReferentialModel | None = None


class NavigationModel(BaseModel):
    name: str
    relationship: str
    from_role: str
    to_role: str
    target_entity_type: str | None = None
    target_entity_set: str | None = None
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None
    resolved: bool = False
    unresolved_reason: str | None = None
    key_resolution: str = "unresolved"
    source_key_fields: list[str] = Field(default_factory=list)
    target_key_fields: list[str] = Field(default_factory=list)
    key_resolution_note: str | None = None


class EntityTypeModel(BaseModel):
    name: str
    namespace: str
    qualified_name: str
    description: str | None = None
    key: KeyModel = Field(default_factory=KeyModel)
    key_defined: bool = False
    properties: list[PropertyModel] = Field(default_factory=list)
    navigation_properties: list[NavigationModel] = Field(default_factory=list)
    exposed: bool = False
    entity_set_names: list[str] = Field(default_factory=list)

    def property_map(self) -> dict[str, PropertyModel]:
        return {item.name: item for item in self.properties}


class EntitySetModel(BaseModel):
    name: str
    entity_type: str
    container: str
    namespace: str


class SchemaCatalog(BaseModel):
    source_system: str
    generated_at: str
    metadata_hash: str = ""
    origin: str = "successfactors"
    schemas: list[str] = Field(default_factory=list)
    containers: list[str] = Field(default_factory=list)
    entity_types: list[EntityTypeModel] = Field(default_factory=list)
    entity_sets: list[EntitySetModel] = Field(default_factory=list)
    associations: list[AssociationModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def type_index(self) -> dict[str, EntityTypeModel]:
        return {item.qualified_name: item for item in self.entity_types}

    def set_index(self) -> dict[str, EntitySetModel]:
        return {item.name: item for item in self.entity_sets}

    def entity_for_set(self, name: str) -> EntityTypeModel | None:
        entity_set = self.set_index().get(name)
        if not entity_set:
            return None
        return self.type_index().get(entity_set.entity_type)

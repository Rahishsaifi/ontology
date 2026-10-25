"""Saved read-only queries."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.errors import CypherRejected
from app.graph.cypher_guard import sanitize_parameters, validate_readonly_cypher


class QueryParameter(BaseModel):
    type: str
    default: str | int | float | bool | None = None
    min: int | None = None
    max: int | None = None


class QueryDefinition(BaseModel):
    id: str
    name: str
    description: str
    cypher: str
    parameters: dict[str, QueryParameter] = Field(default_factory=dict)


def load_query_library(path: Path) -> list[QueryDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = [QueryDefinition.model_validate(item) for item in payload]
    for query in queries:
        validate_readonly_cypher(query.cypher)
    return queries


def resolve_query_params(definition: QueryDefinition, supplied: dict | None) -> dict:
    allowed = set(definition.parameters)
    cleaned = sanitize_parameters(supplied or {}, allowed=allowed)
    resolved = {}
    for name, spec in definition.parameters.items():
        value = cleaned.get(name, spec.default)
        if spec.type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise CypherRejected(f"Parameter '{name}' must be an integer.")
            if spec.min is not None and value < spec.min:
                value = spec.min
            if spec.max is not None and value > spec.max:
                value = spec.max
        elif spec.type == "string":
            if not isinstance(value, str) or len(value) > 200:
                raise CypherRejected(f"Parameter '{name}' must be a short string.")
        resolved[name] = value
    return resolved

"""OData v2 JSON helpers and system-built filters."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.connector.pagination import identifier
from app.errors import ConnectorError, ValidationFailed
from app.mapping.keys import is_canonical_datetime, normalize_value

_STRING_EQ = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) eq '((?:[^']|'')*)'$")
_DATETIME_EQ = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) eq datetime'([^']+)'$")
_DATETIME_GT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) gt datetime'([^']+)'$")
_NUMBER_EQ = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) eq (-?\d+(?:\.\d+)?)$")
_BOOL_EQ = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) eq (true|false)$")


@dataclass
class EntityPage:
    records: list[dict]
    next_url: str | None


def extract_records(payload: object) -> tuple[list[dict], str | None]:
    if not isinstance(payload, dict):
        raise ConnectorError("The OData payload was not an object.")
    next_link = None
    if "d" in payload:
        data = payload["d"]
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            rows = data["results"]
            next_link = data.get("__next")
        elif isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            raise ConnectorError("The OData payload could not be read.")
    elif isinstance(payload.get("value"), list):
        rows = payload["value"]
        next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")
    else:
        raise ConnectorError("The OData payload did not contain results.")
    return [_clean_record(row) for row in rows], next_link


def _clean_record(row: object) -> dict:
    if not isinstance(row, dict):
        raise ConnectorError("An OData record was not an object.")
    cleaned = {}
    for key, value in row.items():
        if key in {"__metadata", "@odata.type"} or str(key).startswith("@"):
            continue
        if isinstance(value, dict) and ("__deferred" in value or "results" in value):
            continue
        cleaned[key] = value
    return cleaned


def odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_key_filter(key_fields: list[str], values: dict[str, str], types: dict[str, str]) -> str:
    parts: list[str] = []
    for field in key_fields:
        identifier(field, "Key field")
        if field not in values:
            raise ValidationFailed(f"Cannot retry a record without key field '{field}'.")
        edm = types.get(field, "Edm.String")
        literal = values[field]
        if edm in {"Edm.DateTime", "Edm.DateTimeOffset"}:
            if not is_canonical_datetime(literal):
                raise ValidationFailed("A datetime key is not in canonical form.")
            parts.append(f"{field} eq datetime'{literal}'")
        elif edm in {"Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Decimal", "Edm.Double", "Edm.Single", "Edm.Byte"}:
            parts.append(f"{field} eq {literal}")
        elif edm == "Edm.Boolean":
            parts.append(f"{field} eq {literal}")
        else:
            parts.append(f"{field} eq {odata_string(literal)}")
    return " and ".join(parts)


def build_incremental_filter(watermark: str) -> str:
    if not is_canonical_datetime(watermark):
        raise ValidationFailed("The sync watermark is not a canonical datetime.")
    return f"lastModifiedDateTime gt datetime'{watermark}'"


def demo_matches(row: dict, expression: str | None) -> bool:
    if not expression:
        return True
    for clause in [part.strip() for part in expression.split(" and ") if part.strip()]:
        if not _clause_matches(row, clause):
            return False
    return True


def _clause_matches(row: dict, clause: str) -> bool:
    match = _DATETIME_GT.match(clause)
    if match:
        field, literal = match.groups()
        current = row.get(field)
        if current is None:
            return False
        return str(current) > literal
    match = _DATETIME_EQ.match(clause)
    if match:
        field, literal = match.groups()
        return str(row.get(field) or "") == literal
    match = _STRING_EQ.match(clause)
    if match:
        field, literal = match.groups()
        return str(row.get(field) or "") == literal.replace("''", "'")
    match = _NUMBER_EQ.match(clause)
    if match:
        field, literal = match.groups()
        try:
            return normalize_value(row.get(field), "Edm.Decimal") == normalize_value(literal, "Edm.Decimal")
        except Exception:
            return False
    match = _BOOL_EQ.match(clause)
    if match:
        field, literal = match.groups()
        return str(row.get(field)).lower() == literal
    raise ValidationFailed("The demo connector cannot evaluate this filter, so it will not return unfiltered rows.")

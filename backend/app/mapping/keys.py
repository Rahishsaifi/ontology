"""Deterministic source identities for OData keys."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone

from app.errors import MissingKeyError

_DATE_LITERAL = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")
_CANONICAL_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

NUMERIC_TYPES = {"Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Decimal", "Edm.Double", "Edm.Single", "Edm.Byte"}
TEMPORAL_TYPES = {"Edm.DateTime", "Edm.DateTimeOffset"}
BOOLEAN_TYPES = {"Edm.Boolean"}


def escape_token(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("=", "\\=")


def unescape_token(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            output.append(value[index + 1])
            index += 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


def join_pairs(pairs: list[tuple[str, str]]) -> str:
    return "|".join(f"{escape_token(key)}={escape_token(val)}" for key, val in pairs)


def split_pairs(source_key: str) -> list[tuple[str, str]]:
    parts: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(source_key):
        char = source_key[index]
        if char == "\\" and index + 1 < len(source_key):
            current.append(source_key[index : index + 2])
            index += 2
            continue
        if char == "|":
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    pairs: list[tuple[str, str]] = []
    for part in parts:
        if not part:
            continue
        raw_key, separator, raw_value = part.partition("=")
        if not separator:
            raise MissingKeyError(f"Source key segment '{part}' is not a field assignment.")
        pairs.append((unescape_token(raw_key), unescape_token(raw_value)))
    return pairs


def stable_id(*parts: str) -> str:
    payload = "\u001f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def signature(*parts: str) -> str:
    payload = "\u001f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_datetime_string(text: str) -> str | None:
    match = _DATE_LITERAL.match(text)
    if match:
        millis = int(match.group(1))
        parsed = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
        return _canonical_datetime(parsed)
    candidate = text.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return _canonical_datetime(parsed)


def normalize_value(value: object, edm_type: str) -> str:
    if value is None:
        raise MissingKeyError("A key value is missing.")
    if edm_type in BOOLEAN_TYPES:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "false"}:
                return lowered
            raise MissingKeyError("A boolean key value is invalid.")
        return "true" if bool(value) else "false"
    if edm_type in NUMERIC_TYPES:
        if isinstance(value, bool) or value == "":
            raise MissingKeyError("A numeric key value is invalid.")
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if not math.isfinite(value):
                raise MissingKeyError("A numeric key value is not finite.")
            if value.is_integer():
                return str(int(value))
            return format(value, "f").rstrip("0").rstrip(".") or "0"
        text = str(value).strip()
        if text == "":
            raise MissingKeyError("A numeric key value is empty.")
        if "." in text:
            number = float(text)
            if number.is_integer():
                return str(int(number))
            return format(number, "f").rstrip("0").rstrip(".")
        return str(int(text))
    if edm_type in TEMPORAL_TYPES:
        if isinstance(value, datetime):
            return _canonical_datetime(value)
        text = str(value).strip()
        parsed = _parse_datetime_string(text)
        if not parsed:
            raise MissingKeyError("A datetime key value is invalid.")
        return parsed
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise MissingKeyError("A key value is empty.")
        parsed = _parse_datetime_string(text)
        if parsed and (_DATE_LITERAL.match(text) or "T" in text):
            return parsed
        return text
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    raise MissingKeyError("The key value type is not supported.")


def build_source_key(key_fields: list[str], record: dict, types: dict[str, str]) -> str:
    if not key_fields:
        raise MissingKeyError("The entity type does not define a key.")
    pairs: list[tuple[str, str]] = []
    for field in key_fields:
        if not _IDENT.match(field):
            raise MissingKeyError(f"Key field '{field}' is not a safe identifier.")
        if field not in record or record[field] is None:
            raise MissingKeyError(f"Key field '{field}' has no value.")
        pairs.append((field, normalize_value(record[field], types.get(field, "Edm.String"))))
    return join_pairs(pairs)


def composite_identity(source_system: str, entity_type: str, source_key: str) -> str:
    return join_pairs(
        [
            ("sourceSystem", source_system),
            ("entityType", entity_type),
            ("sourceKey", source_key),
        ]
    )


def is_canonical_datetime(value: str) -> bool:
    return bool(_CANONICAL_DT.match(value))

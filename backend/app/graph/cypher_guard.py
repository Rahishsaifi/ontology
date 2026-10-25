"""Read-only Cypher gate.

The guard is defense in depth. Neo4j queries also run inside a read transaction.
"""

from __future__ import annotations

from app.errors import CypherRejected

FORBIDDEN_WORDS = {
    "alter",
    "apoc",
    "call",
    "commit",
    "constraint",
    "create",
    "dbms",
    "delete",
    "deny",
    "detach",
    "drop",
    "explain",
    "foreach",
    "gds",
    "grant",
    "index",
    "insert",
    "load",
    "merge",
    "periodic",
    "profile",
    "remove",
    "revoke",
    "schema",
    "set",
    "show",
    "start",
    "stop",
    "terminate",
    "update",
    "use",
}

START_WORDS = {"match", "optional", "with", "unwind", "return"}
MAX_CYPHER_LENGTH = 4000


def _tokens_outside_literals(query: str) -> list[str]:
    words: list[str] = []
    index = 0
    length = len(query)
    while index < length:
        char = query[index]
        if char in {"'", '"'}:
            quote = char
            index += 1
            while index < length:
                if query[index] == "\\":
                    index += 2
                    continue
                if query[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "`":
            index += 1
            while index < length and query[index] != "`":
                index += 1
            index += 1
            continue
        if char == "/" and index + 1 < length and query[index + 1] in {"/", "*"}:
            raise CypherRejected("Comments are not allowed in graph queries.")
        if char == ";":
            raise CypherRejected("Multiple statements are not allowed.")
        if char.isalpha() or char == "_":
            end = index + 1
            while end < length and (query[end].isalnum() or query[end] == "_"):
                end += 1
            words.append(query[index:end].lower())
            index = end
            continue
        index += 1
    return words


def validate_readonly_cypher(query: str) -> str:
    if query is None or not str(query).strip():
        raise CypherRejected("The query is empty.")
    text = str(query).strip()
    if len(text) > MAX_CYPHER_LENGTH:
        raise CypherRejected("The query exceeds the length limit.")
    lowered = text.lower()
    if " db." in f" {lowered}" or lowered.startswith("db.") or "\ndb." in lowered:
        raise CypherRejected("Procedure and DBMS names are not allowed.")
    words = _tokens_outside_literals(text)
    if not words:
        raise CypherRejected("The query has no readable clauses.")
    if words[0] not in START_WORDS:
        raise CypherRejected("The query must start with a read clause.")
    if "return" not in words:
        raise CypherRejected("The query must return results.")
    blocked = sorted(set(words) & FORBIDDEN_WORDS)
    if blocked:
        raise CypherRejected(f"The query contains a forbidden clause: {', '.join(blocked)}.")
    return text


def sanitize_parameters(params: dict | None, *, allowed: set[str] | None = None) -> dict:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise CypherRejected("Query parameters must be an object.")
    if allowed is not None:
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise CypherRejected(f"Unknown query parameters: {', '.join(unknown)}.")
    cleaned: dict = {}
    for key, value in params.items():
        if not isinstance(key, str) or not key.replace("_", "").isalnum():
            raise CypherRejected("Parameter names must be alphanumeric.")
        cleaned[key] = _scalar_or_list(value)
    return cleaned


def _scalar_or_list(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 2000:
            raise CypherRejected("A parameter value is too long.")
        return value
    if isinstance(value, list):
        if len(value) > 100:
            raise CypherRejected("A parameter list is too long.")
        return [_scalar_or_list(item) if not isinstance(item, list) else _reject_nested() for item in value]
    raise CypherRejected("Only scalar parameters and lists of scalars are accepted.")


def _reject_nested():
    raise CypherRejected("Nested parameter lists are not accepted.")

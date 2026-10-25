import pytest

from app.errors import CypherRejected
from app.graph.cypher_guard import sanitize_parameters, validate_readonly_cypher
from app.graph.queries import load_query_library
from pathlib import Path


def test_read_query_is_accepted():
    text = validate_readonly_cypher("MATCH (n:SFEntity) WHERE n.entityType = 'SFOData.User' RETURN n.sourceKey LIMIT 10")
    assert text.startswith("MATCH")


def test_writes_procedures_and_multiple_statements_are_rejected():
    for query in [
        "CREATE (n:SFEntity) RETURN n",
        "MATCH (n) DELETE n RETURN n",
        "MATCH (n) SET n.name = 'x' RETURN n",
        "MATCH (n) CALL db.labels() YIELD label RETURN label",
        "MATCH (n) RETURN n; MATCH (m) RETURN m",
        "MATCH (n) RETURN n // hidden",
        "MERGE (n:SFEntity) RETURN n",
        "MATCH (n) REMOVE n.name RETURN n",
        "DROP CONSTRAINT foo",
    ]:
        with pytest.raises(CypherRejected):
            validate_readonly_cypher(query)


def test_words_inside_strings_are_not_treated_as_clauses():
    validate_readonly_cypher("MATCH (n) WHERE n.displayLabel = 'DELETE ME' RETURN n")


def test_parameter_shapes_are_limited():
    assert sanitize_parameters({"limit": 10}) == {"limit": 10}
    with pytest.raises(CypherRejected):
        sanitize_parameters({"limit": {"nested": True}})
    with pytest.raises(CypherRejected):
        sanitize_parameters({"ok": 1}, allowed={"limit"})


def test_saved_queries_are_read_only():
    path = Path(__file__).resolve().parents[2] / "samples" / "graph-queries.json"
    queries = load_query_library(path)
    assert {item.id for item in queries} >= {"entities-by-type", "reporting-lines", "effective-dated-jobs"}

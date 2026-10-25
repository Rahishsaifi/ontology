from app.graph.neo4j_store import Neo4jGraphStore, _is_ssl_failure, _uri_candidates


def test_aura_uri_prefers_routing():
    uris = _uri_candidates("neo4j+s://demo.databases.neo4j.io")
    assert uris[0].startswith("neo4j+s://")


def test_ssl_failure_detection():
    assert _is_ssl_failure(Exception("SSLCertVerificationError: certificate verify failed"))
    assert not _is_ssl_failure(Exception("DatabaseNotFound"))


def test_trust_all_when_tls_verify_disabled():
    store = Neo4jGraphStore(
        "neo4j+s://demo.databases.neo4j.io",
        "neo4j",
        "secret",
        "successfactors",
        tls_verify=False,
    )
    kwargs = store._driver_kwargs()
    assert "trusted_certificates" in kwargs
    assert Neo4jGraphStore(
        "neo4j+s://demo.databases.neo4j.io",
        "neo4j",
        "secret",
        "successfactors",
        tls_verify=True,
    )._driver_kwargs() == {}

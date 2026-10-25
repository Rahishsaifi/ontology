from app.graph.neo4j_store import Neo4jGraphStore, _is_ssl_failure, _to_ssc_uri, _uri_candidates


def test_aura_uri_prefers_routing():
    uris = _uri_candidates("neo4j+s://demo.databases.neo4j.io")
    assert uris[0].startswith("neo4j+s://")


def test_office_tls_uses_ssc_scheme():
    uris = _uri_candidates("neo4j+s://demo.databases.neo4j.io", tls_verify=False)
    assert uris[0] == "neo4j+ssc://demo.databases.neo4j.io"
    assert uris[1] == "bolt+ssc://demo.databases.neo4j.io"
    assert _to_ssc_uri("bolt+s://demo.databases.neo4j.io") == "bolt+ssc://demo.databases.neo4j.io"


def test_ssl_failure_detection():
    assert _is_ssl_failure(Exception("SSLCertVerificationError: certificate verify failed"))
    assert not _is_ssl_failure(Exception("DatabaseNotFound"))


def test_store_accepts_tls_verify_flag():
    store = Neo4jGraphStore(
        "neo4j+s://demo.databases.neo4j.io",
        "neo4j",
        "secret",
        "successfactors",
        tls_verify=False,
    )
    assert store.tls_verify is False

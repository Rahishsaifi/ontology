import httpx
import pytest

from app.connector.auth import ResolvedAuth
from app.connector.client import SuccessFactorsClient
from app.connector.odata import extract_records
from app.discovery.parser import parse_edmx
from app.errors import ConnectorError, UnsafeNextLinkError, UpstreamAuthenticationError
from pathlib import Path

BASE = "https://example.successfactors.com/odata/v2"
FIXTURE = (Path(__file__).resolve().parents[2] / "samples" / "synthetic-core-hr.edmx").read_bytes()


def client(handler, **kwargs):
    auth = ResolvedAuth(method="oauth_bearer", base_url=BASE, access_token="super-secret-token")
    return SuccessFactorsClient(
        auth,
        transport=httpx.MockTransport(handler),
        sleeper=kwargs.get("sleeper", lambda _: None),
        max_retries=kwargs.get("max_retries", 2),
        tls_verify=True,
    )


def test_authentication_failure_is_not_retried_and_token_is_not_in_the_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["authorization"].startswith("Bearer ")
        return httpx.Response(401, json={"error": {"message": {"value": "bad credentials"}}})

    with pytest.raises(UpstreamAuthenticationError) as caught:
        client(handler).get_metadata()
    assert len(calls) == 1
    assert "super-secret-token" not in str(caught.value)


def test_retries_server_errors_and_honors_retry_after():
    calls = {"count": 0}
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500, json={"error": {"message": "unavailable"}})
        return httpx.Response(200, content=FIXTURE, headers={"content-type": "application/xml"})

    client(handler, sleeper=delays.append).get_metadata()
    assert calls["count"] == 3
    assert delays

    calls["count"] = 0

    def limited(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"message": "slow down"}})
        return httpx.Response(200, content=FIXTURE, headers={"content-type": "application/xml"})

    paced = []
    client(limited, sleeper=paced.append, max_retries=1).get_metadata()
    assert paced == [0]


def test_html_login_page_is_an_authentication_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Sign in</body></html>", headers={"content-type": "text/html"})

    with pytest.raises(UpstreamAuthenticationError):
        client(handler).get_metadata()


def test_next_link_to_another_host_is_not_followed():
    calls = []
    catalog = parse_edmx(FIXTURE)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "d": {
                    "results": [
                        {
                            "userId": "U001",
                            "__metadata": {"uri": "secret"},
                            "manager": {"__deferred": {"uri": "https://evil.example/private"}},
                        }
                    ],
                    "__next": "https://evil.example/odata/v2/User?$skiptoken=1",
                }
            },
        )

    with pytest.raises(UnsafeNextLinkError):
        client(handler).fetch_page("User", select=["userId"], catalog=catalog, top=1)
    assert len(calls) == 1


def test_same_host_next_link_is_followed():
    calls = []
    catalog = parse_edmx(FIXTURE)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "d": {
                        "results": [{"userId": "U001"}],
                        "__next": f"{BASE}/User?$skiptoken=1",
                    }
                },
            )
        return httpx.Response(200, json={"d": {"results": [{"userId": "U002"}]}})

    page = client(handler).fetch_page("User", select=["userId"], catalog=catalog, top=1)
    assert page.records == [{"userId": "U001"}]
    assert page.next_url.endswith("$skiptoken=1")
    second = client(handler).fetch_page("User", select=["userId"], catalog=catalog, next_url=page.next_url)
    assert second.records == [{"userId": "U002"}]


def test_redirects_are_not_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    with pytest.raises(ConnectorError):
        client(handler).get_metadata()


def test_odata_cleaner_drops_metadata_and_deferred_values():
    records, link = extract_records(
        {
            "d": {
                "results": [{"userId": "U001", "__metadata": {"type": "User"}, "manager": {"__deferred": {"uri": "x"}}}],
                "__next": f"{BASE}/User?$skiptoken=2",
            }
        }
    )
    assert records == [{"userId": "U001"}]
    assert link.endswith("skiptoken=2")

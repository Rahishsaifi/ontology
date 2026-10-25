import pytest

from app.connector.pagination import validate_base_url, validate_next_link
from app.errors import UnsafeNextLinkError, ValidationFailed

BASE = "https://example.successfactors.com/odata/v2"


def test_next_link_must_stay_on_the_odata_host():
    safe = validate_next_link(f"{BASE}/User?$skiptoken=abc", BASE)
    assert safe.startswith(BASE)
    with pytest.raises(UnsafeNextLinkError):
        validate_next_link("https://evil.example/odata/v2/User", BASE)
    with pytest.raises(UnsafeNextLinkError):
        validate_next_link("http://example.successfactors.com/odata/v2/User", BASE)
    with pytest.raises(UnsafeNextLinkError):
        validate_next_link("https://user:secret@example.successfactors.com/odata/v2/User", BASE)
    with pytest.raises(UnsafeNextLinkError):
        validate_next_link("https://example.successfactors.com/other/User", BASE)
    with pytest.raises(UnsafeNextLinkError):
        validate_next_link("file:///etc/passwd", BASE)


def test_base_url_requires_https_and_rejects_embedded_credentials():
    assert validate_base_url(BASE + "/", allow_insecure_http=False) == BASE
    with pytest.raises(ValidationFailed):
        validate_base_url("http://example.successfactors.com/odata/v2", allow_insecure_http=False)
    with pytest.raises(ValidationFailed):
        validate_base_url("https://user:secret@example.successfactors.com/odata/v2", allow_insecure_http=False)
    assert (
        validate_base_url("http://localhost/odata/v2", allow_insecure_http=True)
        == "http://localhost/odata/v2"
    )

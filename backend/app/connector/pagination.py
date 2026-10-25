"""Validation of server-provided OData next links."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from app.errors import UnsafeNextLinkError, ValidationFailed

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def identifier(value: str, label: str) -> str:
    if not _IDENT.match(value or ""):
        raise ValidationFailed(f"{label} '{value}' is not an allowed identifier.")
    return value


def _explicit_port(parsed) -> int:
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    raise UnsafeNextLinkError("The next link uses an unsupported scheme.")


def validate_base_url(url: str, *, allow_insecure_http: bool) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.username or parsed.password:
        raise ValidationFailed("Credentials must not be embedded in the SuccessFactors URL.")
    if not parsed.hostname:
        raise ValidationFailed("The SuccessFactors URL is missing a host.")
    if parsed.scheme == "https":
        pass
    elif parsed.scheme == "http" and allow_insecure_http:
        pass
    else:
        raise ValidationFailed(
            "The SuccessFactors URL must use HTTPS unless insecure HTTP is explicitly enabled."
        )
    path = parsed.path.rstrip("/") or ""
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def validate_next_link(next_url: str, base_url: str) -> str:
    if not next_url or not next_url.strip():
        raise UnsafeNextLinkError("The next link is empty.")
    base = urlparse(base_url)
    nxt = urlparse(next_url.strip())
    if nxt.username or nxt.password:
        raise UnsafeNextLinkError("The next link contains embedded credentials.")
    if nxt.scheme not in {"https", "http"}:
        raise UnsafeNextLinkError("The next link scheme is not allowed.")
    if base.scheme == "https" and nxt.scheme != "https":
        raise UnsafeNextLinkError("The next link would downgrade HTTPS.")
    if not nxt.hostname or not base.hostname:
        raise UnsafeNextLinkError("The next link is missing a host.")
    if nxt.hostname.casefold() != base.hostname.casefold():
        raise UnsafeNextLinkError("The next link host does not match the SuccessFactors host.")
    if _explicit_port(nxt) != _explicit_port(base):
        raise UnsafeNextLinkError("The next link port does not match the SuccessFactors host.")
    base_path = base.path.rstrip("/")
    next_path = nxt.path or ""
    if base_path and not (next_path == base_path or next_path.startswith(base_path + "/")):
        raise UnsafeNextLinkError("The next link path is outside the configured OData service.")
    if nxt.fragment:
        raise UnsafeNextLinkError("The next link must not contain a fragment.")
    return urlunparse((nxt.scheme, nxt.netloc, nxt.path, "", nxt.query, ""))

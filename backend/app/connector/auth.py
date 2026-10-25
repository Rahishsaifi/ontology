"""Authentication providers. Tokens and private keys are never logged by these objects."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.connector.pagination import validate_base_url
from app.errors import ConfigError, UpstreamAuthenticationError
from app.redaction import redact_text

SAML_GRANT = "urn:ietf:params:oauth:grant-type:saml2-bearer"


@dataclass
class ResolvedAuth:
    method: str
    base_url: str
    access_token: str = ""
    username: str = ""
    password: str = ""
    company_id: str = ""
    token_url: str = ""
    client_id: str = ""
    saml_assertion: str = ""
    user_id: str = ""
    private_key: str = ""
    user_key: str = ""
    idp_url: str = ""

    def __repr__(self) -> str:
        return f"ResolvedAuth(method={self.method!r}, base_url={self.base_url!r}, configured=True)"


class BearerAuth:
    name = "oauth_bearer"

    def __init__(self, token: str) -> None:
        if not token:
            raise ConfigError("An OAuth bearer token is required. There is no fallback to another authentication method.")
        self._token = token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}


class BasicAuthProvider:
    name = "basic"

    def __init__(self, username: str, password: str, company_id: str = "") -> None:
        if not username or not password:
            raise ConfigError("Basic authentication requires a username and password.")
        user = username
        if company_id and "@" not in username:
            user = f"{username}@{company_id}"
        self._username = user
        self._password = password

    def headers(self) -> dict[str, str]:
        raw = base64.b64encode(f"{self._username}:{self._password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {raw}"}


class SamlBearerAuth:
    """Exchange a caller-supplied SAML assertion for an access token."""

    name = "oauth_saml_bearer"

    def __init__(self, auth: ResolvedAuth, *, client: httpx.Client) -> None:
        if not auth.saml_assertion or not auth.token_url or not auth.client_id or not auth.company_id:
            raise ConfigError(
                "SAML bearer authentication requires a token URL, client id, company id, and a pre-issued assertion."
            )
        validate_base_url(auth.token_url, allow_insecure_http=False)
        self._auth = auth
        self._client = client
        self._cached: str | None = None

    def headers(self) -> dict[str, str]:
        if not self._cached:
            self._cached = exchange_assertion_for_token(self._client, self._auth, self._auth.saml_assertion)
        return {"Authorization": f"Bearer {self._cached}"}


class SamlPrivateKeyAuth:
    """Mint a SAML assertion from the SuccessFactors IdP, then exchange it for an access token.

    IdP step uses company_id, client_id, user_id, private_key, token_url, and the user_key header.
    Token step uses client_id, company_id, grant_type, and assertion.
    Username/password are not used.
    """

    name = "oauth_saml_private_key"

    def __init__(self, auth: ResolvedAuth, *, client: httpx.Client) -> None:
        missing = [
            name
            for name, value in (
                ("token_url", auth.token_url),
                ("client_id", auth.client_id),
                ("company_id", auth.company_id),
                ("user_id", auth.user_id),
                ("private_key", auth.private_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Private-key SAML authentication requires token_url, client_id, company_id, user_id, and private_key. "
                f"Missing: {', '.join(missing)}."
            )
        validate_base_url(auth.token_url, allow_insecure_http=False)
        idp = auth.idp_url or derive_idp_url(auth.token_url)
        validate_base_url(idp, allow_insecure_http=False)
        self._auth = auth
        self._idp_url = idp
        self._client = client
        self._cached: str | None = None

    def headers(self) -> dict[str, str]:
        if not self._cached:
            assertion = mint_saml_assertion(self._client, self._auth, self._idp_url)
            self._cached = exchange_assertion_for_token(self._client, self._auth, assertion)
        return {"Authorization": f"Bearer {self._cached}"}


def derive_idp_url(token_url: str) -> str:
    """Map .../oauth/token to .../oauth/idp. Fail closed if the shape is unexpected."""
    parts = urlsplit(token_url.strip())
    path = parts.path.rstrip("/")
    lowered = path.lower()
    if lowered.endswith("/oauth/token"):
        new_path = path[: -len("/token")] + "/idp"
    elif lowered.endswith("/oauth/token.do"):
        new_path = path[: -len("/token.do")] + "/idp"
    elif "/oauth/" in lowered:
        raise ConfigError(
            "Could not derive the IdP URL from token_url. Set idp_url explicitly to the SuccessFactors /oauth/idp endpoint."
        )
    else:
        raise ConfigError(
            "token_url must end with /oauth/token, or set idp_url to the SuccessFactors IdP endpoint."
        )
    return urlunsplit((parts.scheme, parts.netloc, new_path, "", ""))


def normalize_private_key(value: str) -> str:
    key = value.replace("\\n", "\n").strip()
    if "BEGIN" not in key or "PRIVATE KEY" not in key:
        raise ConfigError("private_key must be a PEM private key including BEGIN/END markers.")
    return key


def mint_saml_assertion(client: httpx.Client, auth: ResolvedAuth, idp_url: str) -> str:
    headers = {
        "Accept": "text/plain, application/json, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "user_key": auth.user_key or auth.user_id,
    }
    data = {
        "client_id": auth.client_id,
        "user_id": auth.user_id,
        "token_url": auth.token_url,
        "private_key": normalize_private_key(auth.private_key),
        "company_id": auth.company_id,
    }
    try:
        response = client.post(idp_url, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise UpstreamAuthenticationError("The SuccessFactors IdP endpoint could not be reached.") from exc
    if response.status_code in {301, 302, 303, 307, 308}:
        raise UpstreamAuthenticationError("The IdP endpoint returned a redirect, which was not followed.")
    if response.status_code != 200:
        raise UpstreamAuthenticationError("The SuccessFactors IdP rejected the private-key assertion request.")
    assertion = _extract_assertion(response)
    if not assertion:
        raise UpstreamAuthenticationError("The IdP response did not contain a SAML assertion.")
    return assertion


def exchange_assertion_for_token(client: httpx.Client, auth: ResolvedAuth, assertion: str) -> str:
    try:
        response = client.post(
            auth.token_url,
            data={
                "grant_type": SAML_GRANT,
                "company_id": auth.company_id,
                "client_id": auth.client_id,
                "assertion": assertion,
            },
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
    except httpx.HTTPError as exc:
        raise UpstreamAuthenticationError("The OAuth token endpoint could not be reached.") from exc
    if response.status_code in {301, 302, 303, 307, 308}:
        raise UpstreamAuthenticationError("The OAuth token endpoint returned a redirect, which was not followed.")
    if response.status_code != 200:
        raise UpstreamAuthenticationError("The OAuth token endpoint rejected the assertion.")
    try:
        payload = response.json()
    except Exception as exc:
        raise UpstreamAuthenticationError("The OAuth token endpoint did not return JSON.") from exc
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise UpstreamAuthenticationError("The OAuth token response did not contain an access token.")
    return str(token)


def _extract_assertion(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text.strip()
    if "json" in content_type:
        try:
            payload = response.json()
        except Exception:
            return text
        if isinstance(payload, dict):
            for key in ("assertion", "samlAssertion", "saml_assertion", "status"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(payload, str):
            return payload.strip()
        return ""
    return text


def build_provider(auth: ResolvedAuth, *, client: httpx.Client):
    if auth.method == "oauth_bearer":
        return BearerAuth(auth.access_token)
    if auth.method == "basic":
        return BasicAuthProvider(auth.username, auth.password, auth.company_id)
    if auth.method == "oauth_saml_bearer":
        return SamlBearerAuth(auth, client=client)
    if auth.method == "oauth_saml_private_key":
        return SamlPrivateKeyAuth(auth, client=client)
    raise ConfigError(
        "Authentication method must be oauth_bearer, basic, oauth_saml_bearer, or oauth_saml_private_key. "
        "The connector will not choose a method automatically."
    )


def safe_http_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return f"HTTP {response.status_code}"
    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            inner = error.get("message")
            if isinstance(inner, dict):
                message = str(inner.get("value") or "")
            elif isinstance(inner, str):
                message = inner
            else:
                message = str(error.get("code") or "")
        elif isinstance(error, str):
            message = error
    return redact_text(f"HTTP {response.status_code}: {message}")[:300]

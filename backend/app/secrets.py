"""Process-memory credentials. These values are never serialized."""

from __future__ import annotations

from dataclasses import dataclass

from app.connector.auth import ResolvedAuth
from app.config import Settings

OVERLAY_FIELDS = (
    "base_url",
    "auth_method",
    "access_token",
    "username",
    "password",
    "company_id",
    "token_url",
    "client_id",
    "saml_assertion",
    "user_id",
    "private_key",
    "user_key",
    "idp_url",
)


@dataclass
class SecretOverlay:
    base_url: str | None = None
    auth_method: str | None = None
    access_token: str | None = None
    username: str | None = None
    password: str | None = None
    company_id: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    saml_assertion: str | None = None
    user_id: str | None = None
    private_key: str | None = None
    user_key: str | None = None
    idp_url: str | None = None

    def __repr__(self) -> str:
        return "SecretOverlay(redacted)"

    def clear(self) -> None:
        for field in OVERLAY_FIELDS:
            setattr(self, field, None)

    def configured(self) -> bool:
        return any(
            [
                self.base_url,
                self.access_token,
                self.username,
                self.password,
                self.saml_assertion,
                self.private_key,
                self.user_id,
            ]
        )


def _pick(overlay_value: str | None, settings_value: str) -> str:
    if overlay_value:
        return overlay_value
    return settings_value or ""


def effective_auth(settings: Settings, overlay: SecretOverlay) -> ResolvedAuth:
    return ResolvedAuth(
        method=_pick(overlay.auth_method, settings.sf_auth_method),
        base_url=_pick(overlay.base_url, settings.sf_base_url),
        access_token=_pick(overlay.access_token, settings.sf_access_token),
        username=_pick(overlay.username, settings.sf_username),
        password=_pick(overlay.password, settings.sf_password),
        company_id=_pick(overlay.company_id, settings.sf_company_id),
        token_url=_pick(overlay.token_url, settings.sf_token_url),
        client_id=_pick(overlay.client_id, settings.sf_client_id),
        saml_assertion=_pick(overlay.saml_assertion, settings.sf_saml_assertion),
        user_id=_pick(overlay.user_id, settings.sf_user_id),
        private_key=_pick(overlay.private_key, settings.sf_private_key),
        user_key=_pick(overlay.user_key, settings.sf_user_key),
        idp_url=_pick(overlay.idp_url, settings.sf_idp_url),
    )


def apply_overlay(overlay: SecretOverlay, payload: dict) -> None:
    for field in OVERLAY_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value != "":
            setattr(overlay, field, value)

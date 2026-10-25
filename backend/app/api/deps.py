"""Bearer-token roles for the application API."""

from __future__ import annotations

import hmac

from fastapi import Header, Request

from app.errors import Forbidden, ServiceUnavailable, Unauthorized


def _equal(left: str, right: str) -> bool:
    try:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
    except Exception:
        return False


def resolve_role(authorization: str | None, settings) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("A bearer token is required.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise Unauthorized("A bearer token is required.")
    if settings.app_admin_token and _equal(token, settings.app_admin_token):
        return "admin"
    if settings.app_api_token and _equal(token, settings.app_api_token):
        return "reader"
    custom = bool(settings.app_api_token or settings.app_admin_token)
    if settings.demo_mode and not custom and _equal(token, "demo-admin"):
        return "admin"
    if settings.demo_mode and not custom and _equal(token, "demo-reader"):
        return "reader"
    if not settings.demo_mode and not custom:
        raise ServiceUnavailable("API tokens are not configured.")
    raise Unauthorized("The bearer token was not accepted.")


def require_reader(request: Request, authorization: str | None = Header(default=None)) -> str:
    return resolve_role(authorization, request.app.state.settings)


def require_admin(request: Request, authorization: str | None = Header(default=None)) -> str:
    role = resolve_role(authorization, request.app.state.settings)
    if role != "admin":
        raise Forbidden("This operation requires an administrator token.")
    return role

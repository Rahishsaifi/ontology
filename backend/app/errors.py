"""Application errors. Messages must never include credentials."""

from __future__ import annotations


class AppError(Exception):
    code = "error"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or []


class Unauthorized(AppError):
    code = "unauthorized"
    status_code = 401


class Forbidden(AppError):
    code = "forbidden"
    status_code = 403


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ValidationFailed(AppError):
    code = "validation_failed"
    status_code = 400


class ConfigError(AppError):
    code = "configuration_error"
    status_code = 400


class UpstreamAuthenticationError(AppError):
    code = "upstream_authentication_failed"
    status_code = 401


class ConnectorError(AppError):
    code = "connector_error"
    status_code = 502


class UnsafeNextLinkError(AppError):
    code = "unsafe_next_link"
    status_code = 400


class MissingKeyError(AppError):
    code = "missing_key"
    status_code = 400


class CypherRejected(AppError):
    code = "cypher_rejected"
    status_code = 400


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class TransientGraphError(AppError):
    code = "graph_transient"
    status_code = 503


class GraphError(AppError):
    code = "graph_error"
    status_code = 502


class ServiceUnavailable(AppError):
    code = "service_unavailable"
    status_code = 503


# Names used by the alternate connector modules.
MetadataParseError = ValidationFailed
UnsafeNextLink = UnsafeNextLinkError
SFAuthenticationError = UpstreamAuthenticationError
SFAuthorizationError = Forbidden
SFRequestError = ConnectorError
SFConnectionError = ConnectorError
FieldSelectionError = ValidationFailed
GraphUnavailable = GraphError

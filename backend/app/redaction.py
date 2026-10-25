"""Redaction helpers for logs and API previews."""

from __future__ import annotations

import logging
import re

SENSITIVE_KEY_NAMES = {
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "password",
    "passwd",
    "secret",
    "token",
    "accesstoken",
    "access_token",
    "refreshtoken",
    "refresh_token",
    "assertion",
    "samlassertion",
    "saml_assertion",
    "privatekey",
    "private_key",
    "userkey",
    "user_key",
    "clientsecret",
    "client_secret",
    "ssn",
    "nationalid",
    "taxid",
    "passport",
    "iban",
    "bankaccount",
}

_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*")
_BASIC = re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]+")
_ASSIGN = re.compile(
    r"(?i)\b(password|token|secret|assertion|access_token|saml_assertion|private_key|user_key)=([^&\s,;]+)"
)
_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def _normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def is_sensitive_key(name: str) -> bool:
    normalized = _normalized(name)
    if normalized in {_normalized(item) for item in SENSITIVE_KEY_NAMES}:
        return True
    return normalized in SENSITIVE_KEY_NAMES


def redact_text(value: str) -> str:
    text = _PEM.sub("-----BEGIN PRIVATE KEY-----\n***\n-----END PRIVATE KEY-----", value)
    text = _BEARER.sub("Bearer ***", text)
    text = _BASIC.sub("Basic ***", text)
    text = _ASSIGN.sub(r"\1=***", text)
    return text


def redact(value, depth: int = 0):
    if depth > 8:
        return "..."
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                cleaned[key] = "***"
            else:
                cleaned[key] = redact(item, depth + 1)
        return cleaned
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value[:100]]
    if isinstance(value, tuple):
        return [redact(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return redact_text(value)
    return value


def is_sensitive_property(name: str, patterns: list[str]) -> bool:
    normalized = _normalized(name)
    for pattern in patterns:
        token = _normalized(pattern)
        if token and token in normalized:
            return True
    return False


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            try:
                rendered = record.msg % record.args
            except Exception:
                rendered = str(record.msg)
            record.msg = redact_text(str(rendered))
            record.args = ()
        else:
            record.msg = redact_text(str(record.msg))
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.addFilter(RedactionFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if not any(isinstance(existing, RedactionFilter) for existing in handler.filters):
                handler.addFilter(RedactionFilter())

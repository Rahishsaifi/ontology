import logging

from app.redaction import RedactionFilter, configure_logging, redact, redact_text


def test_redacts_tokens_headers_and_secret_fields():
    cleaned = redact(
        {
            "Authorization": "Bearer super-secret-token",
            "password": "local-secret",
            "nested": {"access_token": "another-secret", "displayName": "Avery Example"},
        }
    )
    assert cleaned["Authorization"] == "***"
    assert cleaned["password"] == "***"
    assert cleaned["nested"]["access_token"] == "***"
    assert cleaned["nested"]["displayName"] == "Avery Example"
    assert "super-secret-token" not in redact_text("Authorization: Bearer super-secret-token")
    assert "Basic ***" in redact_text("Authorization: Basic c2VjcmV0")


def test_log_records_are_redacted(caplog):
    configure_logging("INFO")
    logger = logging.getLogger("redaction-test")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactionFilter())
    with caplog.at_level(logging.INFO):
        logger.info("Authorization: Bearer super-secret-token")
        logger.info("password=%s", "local-secret")
    assert "super-secret-token" not in caplog.text
    assert "local-secret" not in caplog.text
    assert "Bearer ***" in caplog.text

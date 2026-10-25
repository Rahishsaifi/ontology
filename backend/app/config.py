"""Environment configuration. Secrets stay in the environment, never in code."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BUILTIN_SENSITIVE = (
    "ssn,nationalid,dateofbirth,password,salary,bankaccount,taxid,passport,iban,compensation"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    demo_mode: bool = False
    app_api_token: str = Field(default="", validation_alias=AliasChoices("APP_API_TOKEN", "APP_READER_TOKEN"))
    app_admin_token: str = ""

    sf_base_url: str = ""
    sf_auth_method: str = "oauth_bearer"
    sf_access_token: str = ""
    sf_username: str = ""
    sf_password: str = ""
    sf_company_id: str = ""
    sf_token_url: str = ""
    sf_client_id: str = ""
    sf_saml_assertion: str = ""
    sf_user_id: str = ""
    sf_private_key: str = ""
    sf_user_key: str = ""
    sf_idp_url: str = ""
    sf_timeout_seconds: float = 30.0
    sf_max_retries: int = 3
    sf_page_size: int = 100
    sf_allow_insecure_http: bool = Field(
        default=False, validation_alias=AliasChoices("SF_ALLOW_INSECURE_HTTP", "ALLOW_INSECURE_HTTP")
    )
    tls_verify: bool = Field(default=True, validation_alias=AliasChoices("TLS_VERIFY", "SF_VERIFY_TLS"))

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    graph_backend: str = "neo4j"

    data_dir: str = "./data"
    source_system: str = "successfactors"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    query_timeout_seconds: float = 5.0
    query_max_rows: int = 200
    ingestion_batch_size: int = 100
    inline_jobs: bool = False
    sensitive_property_patterns: str = Field(
        default="",
        validation_alias=AliasChoices("SENSITIVE_PROPERTY_PATTERNS", "SENSITIVE_PROPERTIES"),
    )
    samples_dir: str = ""
    max_metadata_bytes: int = Field(default=20 * 1024 * 1024)

    def sensitive_patterns(self) -> list[str]:
        seen: list[str] = []
        for part in f"{BUILTIN_SENSITIVE},{self.sensitive_property_patterns}".split(","):
            token = part.strip().lower()
            if token and token not in seen:
                seen.append(token)
        return seen

    def samples_path(self) -> Path:
        if self.samples_dir:
            return Path(self.samples_dir)
        return repo_root() / "samples"

    def data_path(self) -> Path:
        return Path(self.data_dir)

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def demo_tokens_active(self) -> bool:
        return self.demo_mode and not self.app_api_token and not self.app_admin_token


def load_settings() -> Settings:
    if os.getenv("SF_ONTOLOGY_IGNORE_ENV_FILE") == "1":
        return Settings(_env_file=None)
    return Settings()

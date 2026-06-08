from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    slack_client_id: str
    slack_client_secret: str
    slack_signing_secret: str
    slack_bot_token: str = ""

    database_url: str
    test_database_url: str = "postgresql+asyncpg://relay:relay@localhost:5432/relay_test"
    redis_url: str = "redis://localhost:6379/0"

    token_encryption_key: str = Field(
        description="Legacy fallback key used before workspace KMS envelope encryption is migrated.",
    )

    anthropic_api_key: str
    classifier_model: str = "claude-3-5-haiku-latest"
    draft_model: str = "claude-3-5-sonnet-latest"
    summary_model: str = "claude-haiku-4-5-20251001"
    classifier_open_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    classifier_candidate_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    classifier_variant: str = "a"

    app_base_url: str
    environment: str = "development"
    sentry_dsn: str = ""
    kms_provider: str = "none"
    kms_key_id: str = ""

    # HubSpot OAuth (optional — defaults to "" so existing tests don't break)
    hubspot_client_id: str = ""
    hubspot_client_secret: str = ""
    hubspot_redirect_uri: str = ""

    # Embedding provider + API keys
    embedding_provider: str = "voyage"
    voyage_api_key: str = ""
    openai_api_key: str = ""

    # Connector credentials (dev/test fallbacks)
    google_drive_credentials_json: str = ""
    github_token: str = ""

    # GDPR erasure (leave empty to disable the endpoint on deployments that don't need it)
    erasure_secret: str = ""

    @field_validator("token_encryption_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if len(value) != 64:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be exactly 64 hex chars")
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be valid hexadecimal") from exc
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "Settings":
        if self.classifier_open_threshold < self.classifier_candidate_threshold:
            raise ValueError("CLASSIFIER_OPEN_THRESHOLD must be >= CANDIDATE threshold")
        return self

    @property
    def token_encryption_key_bytes(self) -> bytes:
        return bytes.fromhex(self.token_encryption_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

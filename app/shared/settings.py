from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "dev"
    app_debug: bool = True
    app_port: Annotated[int, Field(ge=1, le=65535)] = 8000
    # Frontend / share-link origin (users open this in browser).
    app_public_base_url: str = "http://localhost:8000"
    # Public API origin for Telegram/provider webhooks. Empty = same as app_public_base_url.
    app_api_public_base_url: str = ""

    jwt_secret: str = "changeme_dev_secret_min_32_chars_xxxxxx"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000
    ws_ticket_ttl_seconds: int = 60
    ws_heartbeat_interval_seconds: int = 20
    ws_idle_timeout_seconds: int = 60

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5433/crm"
    redis_url: str = "redis://localhost:6379/0"

    seed_admin_email: str = "admin@crm.local"
    seed_admin_password: str = "ChangeMe!234567"

    s3_endpoint: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minio"
    s3_secret_key: str = "miniominio"
    s3_bucket_files: str = "crm-files"
    s3_bucket_backups: str = "crm-backups"

    pgcrypto_key: str = "changeme_dev_pgcrypto_key"

    sentry_dsn: str = ""
    sentry_environment: str = "dev"
    sentry_traces_sample_rate: float = 0.0

    metrics_enabled: bool = False

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@crm.local"

    log_level: str = "INFO"
    log_json: bool = True
    log_pii_mask: bool = True

    ownership_v2: bool = True
    workers_in_api: bool = False

    max_upload_photo_bytes: int = 10 * 1024 * 1024
    max_upload_file_bytes: int = 50 * 1024 * 1024
    login_rate_limit_per_minute: int = 10
    login_rate_limit_use_redis: bool = True
    bot_job_reclaim_idle_ms: int = 300_000
    bot_health_check_interval_seconds: int = 21_600

    wa_bridge_outbound_url: str = "http://host.docker.internal:8766/crm/cmd"
    wa_bridge_health_url: str = "http://host.docker.internal:8766/crm/health"
    wa_bridge_webhook_public_base: str = "https://api.example.com/green/webhook"
    wa_bridge_sync_secret: str = "changeme_wa_bridge_sync_secret_min32"

    telephony_stun_urls: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["stun:stun.l.google.com:19302"],
    )
    telephony_turn_urls: Annotated[list[str], NoDecode] = Field(default_factory=list)
    telephony_turn_username: str = ""
    telephony_turn_password: str = ""

    search_rate_limit_per_minute: int = 60
    search_rate_limit_use_redis: bool = True

    chat_messages_rate_limit_per_minute: int = 60
    chat_messages_rate_limit_use_redis: bool = True

    contacts_update_rate_limit_per_minute: int = 30
    contacts_update_rate_limit_use_redis: bool = True

    leads_list_rate_limit_per_minute: int = 60
    leads_create_rate_limit_per_minute: int = 30
    leads_rate_limit_use_redis: bool = True

    # Retention policy for closed leads. NULL = keep forever (not recommended for production).
    # Set to e.g. 365 to purge leads closed more than 365 days ago.
    # Requires lead_purge_enabled = True to take effect.
    lead_retention_days: int | None = None
    # Enable periodic purge of closed leads older than lead_retention_days.
    # Safe to enable in production; only deletes leads with closed_at < now() - retention_days.
    lead_purge_enabled: bool = False

    # crm_summary aggregates (contact card + dashboard) — Redis TTL cache.
    crm_summary_cache_enabled: bool = True
    crm_summary_cache_ttl_seconds: int = 300

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
    )

    # 1C Mole integration (OPT wholesale orders)
    mole_api_base_url: str = ""
    mole_api_orders_path: str = "/hs/mole/orders"
    mole_api_timeout_seconds: float = 60.0
    mole_api_username: str = ""
    mole_api_password: str = ""
    opt_vat_rate_percent: float = 22.0

    # External service token for POST /accounting/requirements/ingest
    accounting_ingest_token: str = ""

    # sbis-norm FNS requirements pull (http://host:8000/api/sbis/requirements/)
    sbis_norm_api_base_url: str = ""
    sbis_norm_api_token: str = ""
    sbis_norm_api_timeout_seconds: float = 60.0
    sbis_norm_sync_enabled: bool = True
    sbis_norm_sync_interval_seconds: int = 3600
    sbis_norm_sync_batch_limit: int = 50
    # Token expected from sbis-norm webhook (REQUIREMENTS_WEBHOOK_TOKEN on their side)
    sbis_norm_webhook_token: str = ""

    @field_validator("sentry_traces_sample_rate")
    @classmethod
    def validate_traces_sample_rate(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            msg = "SENTRY_TRACES_SAMPLE_RATE must be between 0.0 and 1.0"
            raise ValueError(msg)
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            msg = "JWT_SECRET must be at least 32 characters"
            raise ValueError(msg)
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return []

    @field_validator("telephony_stun_urls", "telephony_turn_urls", mode="before")
    @classmethod
    def parse_ice_urls(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [url.strip() for url in value.split(",") if url.strip()]
        if isinstance(value, list):
            return [str(url).strip() for url in value if str(url).strip()]
        return []

    @property
    def api_public_base_url(self) -> str:
        """Origin Telegram and other providers must reach (API host)."""
        raw = (self.app_api_public_base_url or self.app_public_base_url or "").strip()
        return raw.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

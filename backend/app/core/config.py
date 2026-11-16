from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SolidPro HireAI"
    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://hireai:hireai@localhost:5432/hireai"

    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    remember_me_expire_minutes: int = 43200
    cookie_name: str = "hireai_session"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    rate_limit_enabled: bool = True
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    email_verification_expire_hours: int = 24
    password_reset_expire_minutes: int = 60

    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_from: str = "SolidPro HireAI <no-reply@solidpro.example>"
    support_email: str = "hr-support@solidpro.example"

    upload_dir: str = "./storage"
    max_upload_mb: int = 5
    bulk_max_files: int = 50  # files per bulk batch
    bulk_max_attempts: int = 3  # automatic processing attempts per file

    # AI. "mock" is deterministic keyword matching and is always labelled as MOCK in the UI.
    ai_provider: Literal["mock", "anthropic"] = "mock"
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-5-5"
    ai_timeout_seconds: int = 60
    # Speech-to-text for Repeat the Sentence (Phase 6)
    stt_provider: Literal["mock", "openai"] = "mock"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    stt_base_url: str = "https://api.openai.com/v1"
    stt_timeout_seconds: int = 60
    stt_min_confidence: float = 0.6  # below this a transcript is flagged for a human to listen
    ai_max_resume_chars: int = 15000

    # Online testing (Phase 5)
    sweeper_enabled: bool = True  # background task that auto-submits overdue attempts and expires missed schedules
    sweeper_interval_seconds: int = 60
    submit_grace_seconds: int = 20  # tolerated lag between the deadline and the final autosave / upload
    max_recording_mb: int = 8

    company_email_domains: str = ""
    admin_email: str = ""
    admin_name: str = "System Administrator"
    admin_initial_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def company_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.company_email_domains.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.is_production:
            if len(self.secret_key) < 32 or self.secret_key.startswith("change-me"):
                raise ValueError("SECRET_KEY must be a random value of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

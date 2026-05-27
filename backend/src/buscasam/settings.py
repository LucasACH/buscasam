from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-do-not-use-in-prod"
DEV_OIDC_CLIENT_SECRET = "dev-client-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSCASAM_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://buscasam:buscasam@localhost:5432/buscasam"
    tei_url: str = "http://localhost:8080"
    min_semantic_similarity: float = 0.78
    # ADR-0007 §12: per-row provenance stamp for the extraction pipeline.
    extract_pipeline_version: str = "extract-v1"

    base_url: str = "http://localhost:3000"
    secret_key: str = DEV_SECRET_KEY
    oidc_client_id: str = "dev-client-id"
    oidc_client_secret: str = DEV_OIDC_CLIENT_SECRET
    oidc_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )

    @field_validator("base_url", mode="after")
    @classmethod
    def _normalize_base_url(cls, raw: str) -> str:
        """Match the shape a browser sends in `Origin`: `scheme://host[:port]`.

        The Origin-check middleware compares against this verbatim, so a
        trailing slash or path component in the env var would silently 403
        every authenticated unsafe method.
        """
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            raise ValueError(
                f"BUSCASAM_BASE_URL must be an absolute URL, got {raw!r}"
            )
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError(
                "BUSCASAM_BASE_URL must not carry a path, query, or fragment "
                f"(got {raw!r}); the Origin header never includes one"
            )
        return f"{parts.scheme}://{parts.netloc}"

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> "Settings":
        if self.env == "prod":
            if self.secret_key == DEV_SECRET_KEY:
                raise ValueError(
                    "BUSCASAM_SECRET_KEY must be set to a non-dev value when BUSCASAM_ENV=prod"
                )
            if self.oidc_client_secret == DEV_OIDC_CLIENT_SECRET:
                raise ValueError(
                    "BUSCASAM_OIDC_CLIENT_SECRET must be set to a non-dev value when BUSCASAM_ENV=prod"
                )
        return self


settings = Settings()

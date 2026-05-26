from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-do-not-use-in-prod"
DEV_OIDC_CLIENT_SECRET = "dev-client-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSCASAM_")

    env: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://buscasam:buscasam@localhost:5432/buscasam"
    tei_url: str = "http://localhost:8080"
    min_semantic_similarity: float = 0.78

    base_url: str = "http://localhost:3000"
    secret_key: str = DEV_SECRET_KEY
    oidc_client_id: str = "dev-client-id"
    oidc_client_secret: str = DEV_OIDC_CLIENT_SECRET
    oidc_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )

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

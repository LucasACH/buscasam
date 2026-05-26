from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSCASAM_")

    database_url: str = "postgresql+psycopg://buscasam:buscasam@localhost:5432/buscasam"
    tei_url: str = "http://localhost:8080"
    min_semantic_similarity: float = 0.78

    base_url: str = "http://localhost:3000"
    secret_key: str = "dev-secret-do-not-use-in-prod"
    oidc_client_id: str = "dev-client-id"
    oidc_client_secret: str = "dev-client-secret"
    oidc_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )


settings = Settings()

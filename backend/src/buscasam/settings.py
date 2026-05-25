from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSCASAM_")

    database_url: str = "postgresql+psycopg://buscasam:buscasam@localhost:5432/buscasam"
    tei_url: str = "http://localhost:8080"
    min_semantic_similarity: float = 0.78


settings = Settings()

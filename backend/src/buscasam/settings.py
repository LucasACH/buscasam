import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-do-not-use-in-prod"
DEV_OIDC_CLIENT_SECRET = "dev-client-secret"


def _vendored_tokenizer_revision() -> str:
    """Default model revision: the SHA the vendored e5 tokenizer was pinned to.

    Operators override via `BUSCASAM_EMBEDDING_MODEL_REVISION` in prod; startup
    verifies the vendored tokenizer manifest still matches (ADR-0002 §5).
    """
    manifest = (
        Path(__file__).parent / "core" / "vendor" / "e5_tokenizer" / "manifest.json"
    )
    return json.loads(manifest.read_text())["revision"]


class Settings(BaseSettings):
    # Tests set BUSCASAM_DISABLE_DOTENV to assert against committed defaults
    # regardless of a developer's local `.env`.
    model_config = SettingsConfigDict(
        env_prefix="BUSCASAM_",
        env_file=None if os.environ.get("BUSCASAM_DISABLE_DOTENV") else ".env",
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://buscasam:buscasam@localhost:5432/buscasam"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    tei_url: str = "http://localhost:8080"
    # ADR-0002 §5: single source for the HF model + vendored tokenizer revision.
    embedding_model_revision: str = Field(default_factory=_vendored_tokenizer_revision)
    # Semantic floor: a pure-semantic candidate (no lexical hit) is shown only if
    # its best chunk cosine clears this (ADR-0001 §12). Lexical hits bypass it.
    # Interim value pending calibration on a real corpus via
    # `scripts/calibrate_floor.py`; the committed fixture sweep currently favors
    # this. Override per-env with BUSCASAM_MIN_SEMANTIC_SIMILARITY.
    min_semantic_similarity: float = 0.84
    # Trigram word_similarity floor for the fuzzy fallback (typo tolerance) that
    # runs only when exact retrieval returns 0 rows. Lower => more permissive.
    # Kept permissive (0.3) so transposition typos still recover; stopword-only
    # queries are handled by the lexeme guard in `core/search`, not this floor.
    fuzzy_word_similarity_threshold: float = 0.3
    # Lexical grounding for pure-semantic hits: a candidate with NO full-text
    # lexical match is shown only if it also shares trigram signal with the query
    # above this floor. Guards against e5 short-query cosine inflation surfacing
    # off-topic docs (e.g. "recetas"). 0 disables grounding (revert to floor-only,
    # the original SPEC §Ranking behavior). Override with
    # BUSCASAM_SEMANTIC_ONLY_TRGM_THRESHOLD. Interim value pending calibration.
    semantic_only_trgm_threshold: float = 0.4
    embed_query_timeout_s: float = 0.5
    # ADR-0007 §12: per-row provenance stamp for the extraction pipeline.
    extract_pipeline_version: str = "extract-v2"
    metadata_llm_enabled: bool = False
    metadata_llm_provider: Literal["ollama", "vertex"] = "ollama"
    metadata_llm_url: str = "http://localhost:11434"
    metadata_llm_model: str = "qwen2.5:7b-instruct"
    metadata_llm_timeout_s: float = 60.0
    vertex_project: str = ""
    vertex_location: str = "us-central1"

    base_url: str = "http://localhost:3000"
    blob_root: Path = Path("/var/lib/buscasam/blobs")
    serve_blobs_inline: bool = False
    secret_key: str = DEV_SECRET_KEY
    oidc_client_id: str = "dev-client-id"
    oidc_client_secret: str = DEV_OIDC_CLIENT_SECRET
    oidc_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )
    # Comma-separated exact emails granted the `docente` role even though their
    # `hd` is not an UNSAM domain (ADR-0005 §3 override). Intended for demo /
    # non-UNSAM accounts that must moderate; `email_verified` is still required,
    # so this only loosens the domain map, not the verification gate. Set via
    # BUSCASAM_DOCENTE_EMAIL_ALLOWLIST; empty (the default) is a no-op.
    docente_email_allowlist: str = ""

    @property
    def docente_emails(self) -> frozenset[str]:
        """Normalized (lowercased, stripped) set parsed from the allowlist."""
        return frozenset(
            e.strip().lower()
            for e in self.docente_email_allowlist.split(",")
            if e.strip()
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
            raise ValueError(f"BUSCASAM_BASE_URL must be an absolute URL, got {raw!r}")
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError(
                "BUSCASAM_BASE_URL must not carry a path, query, or fragment "
                f"(got {raw!r}); the Origin header never includes one"
            )
        return f"{parts.scheme}://{parts.netloc}"

    @model_validator(mode="after")
    def _require_vertex_project(self) -> "Settings":
        if (
            self.metadata_llm_enabled
            and self.metadata_llm_provider == "vertex"
            and not self.vertex_project
        ):
            raise ValueError(
                "BUSCASAM_VERTEX_PROJECT must be set when "
                "BUSCASAM_METADATA_LLM_PROVIDER=vertex and the metadata LLM is enabled"
            )
        return self

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

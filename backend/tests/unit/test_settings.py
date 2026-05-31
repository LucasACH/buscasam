import pytest

from buscasam.settings import Settings


def test_min_semantic_similarity_calibrated_to_committed_value():
    s = Settings()
    assert 0.0 < s.min_semantic_similarity < 1.0
    assert s.min_semantic_similarity == 0.78


def test_fuzzy_word_similarity_threshold_default():
    s = Settings()
    assert 0.0 < s.fuzzy_word_similarity_threshold < 1.0
    assert s.fuzzy_word_similarity_threshold == 0.3


def test_tei_url_default():
    s = Settings()
    assert s.tei_url == "http://localhost:8080"


def test_metadata_llm_defaults_are_local_opt_in():
    s = Settings()
    assert s.metadata_llm_enabled is False
    assert s.metadata_llm_provider == "ollama"
    assert s.metadata_llm_url == "http://localhost:11434"
    assert s.metadata_llm_model == "qwen2.5:7b-instruct"
    assert s.metadata_llm_timeout_s == 60.0
    assert s.vertex_project == ""
    assert s.vertex_location == "us-central1"
    assert s.extract_pipeline_version == "extract-v2"


def test_vertex_provider_requires_project_when_enabled():
    with pytest.raises(ValueError, match="BUSCASAM_VERTEX_PROJECT"):
        Settings(
            metadata_llm_enabled=True,
            metadata_llm_provider="vertex",
            _env_file=None,
        )


def test_vertex_provider_ok_with_project():
    s = Settings(
        metadata_llm_enabled=True,
        metadata_llm_provider="vertex",
        vertex_project="buscasam-prod",
        _env_file=None,
    )
    assert s.vertex_project == "buscasam-prod"


def test_prod_env_rejects_dev_secret_key():
    with pytest.raises(ValueError, match="BUSCASAM_SECRET_KEY"):
        Settings(env="prod", oidc_client_secret="real-client-secret", _env_file=None)


def test_prod_env_rejects_dev_oidc_client_secret():
    with pytest.raises(ValueError, match="BUSCASAM_OIDC_CLIENT_SECRET"):
        Settings(env="prod", secret_key="real-secret", _env_file=None)


def test_prod_env_accepts_non_dev_secrets():
    s = Settings(
        env="prod", secret_key="real-secret", oidc_client_secret="real-client-secret"
    )
    assert s.env == "prod"


def test_dev_env_allows_dev_defaults():
    s = Settings()
    assert s.env == "dev"


def test_base_url_strips_trailing_slash():
    s = Settings(base_url="https://app.example.com/")
    assert s.base_url == "https://app.example.com"


def test_base_url_default_unchanged():
    assert Settings().base_url == "http://localhost:3000"


def test_base_url_rejects_path():
    with pytest.raises(ValueError, match="must not carry a path"):
        Settings(base_url="https://app.example.com/api")


def test_base_url_rejects_query():
    with pytest.raises(ValueError, match="must not carry a path"):
        Settings(base_url="https://app.example.com?x=1")


def test_base_url_rejects_relative():
    with pytest.raises(ValueError, match="must be an absolute URL"):
        Settings(base_url="app.example.com")

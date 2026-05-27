import pytest

from buscasam.settings import Settings


def test_min_semantic_similarity_calibrated_to_committed_value():
    s = Settings()
    assert 0.0 < s.min_semantic_similarity < 1.0
    assert s.min_semantic_similarity == 0.78


def test_tei_url_default():
    s = Settings()
    assert s.tei_url == "http://localhost:8080"


def test_prod_env_rejects_dev_secret_key():
    with pytest.raises(ValueError, match="BUSCASAM_SECRET_KEY"):
        Settings(env="prod", oidc_client_secret="real-client-secret", _env_file=None)


def test_prod_env_rejects_dev_oidc_client_secret():
    with pytest.raises(ValueError, match="BUSCASAM_OIDC_CLIENT_SECRET"):
        Settings(env="prod", secret_key="real-secret", _env_file=None)


def test_prod_env_accepts_non_dev_secrets():
    s = Settings(env="prod", secret_key="real-secret", oidc_client_secret="real-client-secret")
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

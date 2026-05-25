from buscasam.settings import Settings


def test_min_semantic_similarity_calibrated_to_committed_value():
    s = Settings()
    assert 0.0 < s.min_semantic_similarity < 1.0
    assert s.min_semantic_similarity == 0.78


def test_tei_url_default():
    s = Settings()
    assert s.tei_url == "http://localhost:8080"

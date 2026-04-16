from cv_agent.utils import canonical_url, fingerprint, slugify, word_count


def test_slugify_basic():
    assert slugify("Head of Sales — Paris") == "head_of_sales_paris"


def test_slugify_accents():
    assert slugify("Société Générale — Directeur") == "societe_generale_directeur"


def test_canonical_url_strips_query_and_fragment():
    a = canonical_url("https://example.com/jobs/123?utm=x#section")
    b = canonical_url("https://EXAMPLE.com/jobs/123/")
    assert a == b


def test_fingerprint_stable_and_unique():
    a = fingerprint("BNP Paribas", "Head of Coverage", "https://x.com/jobs/1")
    b = fingerprint("BNP Paribas", "Head of Coverage", "https://x.com/jobs/1?utm=y")
    c = fingerprint("BNP Paribas", "Other role", "https://x.com/jobs/1")
    assert a == b
    assert a != c


def test_word_count():
    assert word_count("a b c d") == 4
    assert word_count("") == 0

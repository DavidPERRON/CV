from cv_agent.editorial.scorer import junior_title_blocked, _load_blocklist


def test_junior_blocklist_catches_obvious():
    blocked, tok = junior_title_blocked("Junior Analyst — Equities")
    assert blocked is True
    assert tok in {"junior", "analyst"}


def test_junior_blocklist_catches_french():
    blocked, _ = junior_title_blocked("Stagiaire M&A H/F")
    assert blocked is True


def test_junior_blocklist_passes_senior_titles():
    for title in [
        "Head of Transaction Banking Sales",
        "Managing Director, Corporate Coverage",
        "VP, Applied AI Go-to-Market",
        "Director of Strategic Accounts",
        "Chief of Staff to the CEO",
    ]:
        blocked, _ = junior_title_blocked(title)
        assert blocked is False, title


def test_blocklist_loads_from_yaml():
    items = _load_blocklist()
    assert "junior" in items
    assert "stagiaire" in items

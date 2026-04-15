import json
from datetime import datetime, timedelta

import pytest

from cv_agent import state as state_mod
from cv_agent.settings import Settings


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    applied = tmp_path / "applied.json"
    pending = tmp_path / "pending.json"
    monkeypatch.setattr(state_mod, "APPLIED_PATH", applied)
    monkeypatch.setattr(state_mod, "PENDING_PATH", pending)
    return applied, pending


def _settings():
    return Settings(applied_jobs_cap=3, applied_jobs_ttl_days=30, pending_applications_cap=2)


def test_applied_cap_fifo(tmp_state):
    s = _settings()
    now = datetime.utcnow()
    entries = {
        f"fp{i}": {"discovered_at": (now - timedelta(days=i)).isoformat()}
        for i in range(5)
    }
    state_mod.save_applied(entries, s)
    kept = state_mod.load_applied()
    assert len(kept) == 3  # cap
    # The three kept should be the freshest (smallest i)
    assert set(kept.keys()) == {"fp0", "fp1", "fp2"}


def test_applied_ttl_drops_old(tmp_state):
    s = _settings()
    now = datetime.utcnow()
    entries = {
        "new": {"discovered_at": now.isoformat()},
        "old": {"discovered_at": (now - timedelta(days=90)).isoformat()},
    }
    state_mod.save_applied(entries, s)
    kept = state_mod.load_applied()
    assert "new" in kept and "old" not in kept


def test_pending_add_and_remove(tmp_state):
    s = _settings()
    state_mod.add_pending("fpA", {"title": "A", "generated_at": "2026-01-01T00:00:00"}, s)
    state_mod.add_pending("fpB", {"title": "B", "generated_at": "2026-01-02T00:00:00"}, s)
    state_mod.add_pending("fpC", {"title": "C", "generated_at": "2026-01-03T00:00:00"}, s)
    pending = state_mod.load_pending()
    assert len(pending) == 2
    # oldest (A) should have been evicted
    assert "fpA" not in pending

    removed = state_mod.remove_pending("fpB")
    assert removed is not None
    assert "fpB" not in state_mod.load_pending()

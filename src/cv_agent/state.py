"""Persistent state on disk as JSON. Mirrors ai_press_review.state pattern."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .settings import DATA_DIR, Settings
from .utils import ensure_dir

STATE_DIR = DATA_DIR / "state"
APPLIED_PATH = STATE_DIR / "applied_jobs.json"
PENDING_PATH = STATE_DIR / "pending_applications.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_applied() -> dict[str, dict[str, Any]]:
    return _load(APPLIED_PATH).get("entries", {})


def save_applied(entries: dict[str, dict[str, Any]], settings: Settings) -> None:
    # Enforce TTL + cap (FIFO on discovered_at).
    cutoff = datetime.utcnow() - timedelta(days=settings.applied_jobs_ttl_days)
    fresh = {
        fp: e for fp, e in entries.items()
        if datetime.fromisoformat(e.get("discovered_at", "1970-01-01T00:00:00")) >= cutoff
    }
    if len(fresh) > settings.applied_jobs_cap:
        ordered = sorted(fresh.items(), key=lambda kv: kv[1].get("discovered_at", ""))
        fresh = dict(ordered[-settings.applied_jobs_cap:])
    _save(APPLIED_PATH, {"entries": fresh, "saved_at": datetime.utcnow().isoformat()})


def mark_applied(fingerprint: str, payload: dict[str, Any], settings: Settings) -> None:
    entries = load_applied()
    entries[fingerprint] = payload
    save_applied(entries, settings)


def is_known(fingerprint: str) -> bool:
    return fingerprint in load_applied()


def load_pending() -> dict[str, dict[str, Any]]:
    return _load(PENDING_PATH).get("entries", {})


def save_pending(entries: dict[str, dict[str, Any]]) -> None:
    _save(PENDING_PATH, {"entries": entries, "saved_at": datetime.utcnow().isoformat()})


def add_pending(fingerprint: str, payload: dict[str, Any], settings: Settings) -> None:
    entries = load_pending()
    entries[fingerprint] = payload
    if len(entries) > settings.pending_applications_cap:
        ordered = sorted(entries.items(), key=lambda kv: kv[1].get("generated_at", ""))
        entries = dict(ordered[-settings.pending_applications_cap:])
    save_pending(entries)


def remove_pending(fingerprint: str) -> dict[str, Any] | None:
    entries = load_pending()
    payload = entries.pop(fingerprint, None)
    save_pending(entries)
    return payload

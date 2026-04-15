"""Shared helpers."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def slugify(value: str, max_length: int = 80) -> str:
    """Filesystem-safe slug, lowercase, ASCII, separated by underscores."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "_", value)
    return value[:max_length].strip("_")


def canonical_url(url: str) -> str:
    """Strip query/fragment noise for dedup, keep host + path."""
    p = urlparse(url.strip())
    if not p.scheme:
        return url.strip().lower()
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", "", ""))


def fingerprint(company: str, title: str, url: str) -> str:
    """Stable sha256 fingerprint for dedup across runs."""
    key = f"{company.strip().lower()}|{title.strip().lower()}|{canonical_url(url)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text or "") if w])


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

"""RSS/Atom collector for job boards. Shape mirrors ai_press_review.collectors.rss."""
from __future__ import annotations

import logging
from typing import Iterable

from ..models import JobPosting
from ..utils import fingerprint

log = logging.getLogger(__name__)


def collect_rss(feeds: Iterable[dict]) -> list[JobPosting]:
    try:
        import feedparser  # imported lazily so the package imports without the dep
    except ImportError:
        log.warning("feedparser not installed — skipping RSS collection.")
        return []
    postings: list[JobPosting] = []
    for feed in feeds:
        name = feed.get("name", "rss")
        url = feed.get("url")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning("feedparser failed on %s: %s", url, e)
            continue
        for entry in parsed.entries[:100]:
            link = entry.get("link") or ""
            title = (entry.get("title") or "").strip()
            if not (link and title):
                continue
            company = _guess_company(entry, name)
            job = JobPosting(
                title=title,
                company=company,
                url=link,
                source=f"rss:{name}",
                location=entry.get("location", "") or "",
                description=_strip_html(entry.get("summary", "")),
                posted_at=entry.get("published", "") or entry.get("updated", ""),
            )
            job.fingerprint = fingerprint(job.company, job.title, job.url)
            postings.append(job)
    log.info("rss: %d postings collected from %d feeds", len(postings), len(list(feeds)))
    return postings


def _guess_company(entry, feed_name: str) -> str:
    # Feedparser puts many shapes here — we try a few.
    for key in ("author", "source", "publisher"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            title = v.get("title") or v.get("name")
            if title:
                return title.strip()
    # Fall back to feed name
    return feed_name


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", s or "").strip()

"""Career-page collector. Given a listing URL and an optional CSS selector for
job links, returns a list of JobPosting stubs (title + url). Full JD text is
filled later by the extractor."""
from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

from ..models import JobPosting
from ..settings import Settings
from ..utils import fingerprint

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(2), reraise=True)
def _fetch(url: str, settings: Settings) -> str:
    r = requests.get(
        url,
        headers={"User-Agent": settings.user_agent, "Accept-Language": "en,fr;q=0.9"},
        timeout=settings.extraction_timeout,
    )
    r.raise_for_status()
    return r.text


def collect_career_page(page: dict, sector: str, settings: Settings) -> list[JobPosting]:
    """One career page -> list of JobPosting stubs."""
    name = page.get("name", "careers")
    url = page.get("url")
    selector = page.get("link_selector", "a")
    if not url:
        return []
    try:
        html = _fetch(url, settings)
    except Exception as e:
        log.warning("careers fetch failed for %s: %s", name, e)
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    postings: list[JobPosting] = []
    try:
        nodes = soup.select(selector)
    except Exception:
        nodes = soup.find_all("a")
    for a in nodes:
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if not (href and title) or len(title) < 6:
            continue
        full = urljoin(url, href)
        if full in seen:
            continue
        seen.add(full)
        job = JobPosting(
            title=title[:160],
            company=name,
            url=full,
            source=f"careers:{name}",
            sector=sector,
        )
        job.fingerprint = fingerprint(job.company, job.title, job.url)
        postings.append(job)
    log.info("careers[%s]: %d postings from %s", sector, len(postings), name)
    return postings


def collect_career_pages(sources: dict, settings: Settings) -> list[JobPosting]:
    """Iterate all categorized career pages in the sources.yaml dict."""
    results: list[JobPosting] = []
    for sector, section in (sources or {}).items():
        if sector == "job_boards":
            continue
        pages = (section or {}).get("career_pages", []) if isinstance(section, dict) else []
        for page in pages:
            results.extend(collect_career_page(page, sector=sector, settings=settings))
    return results

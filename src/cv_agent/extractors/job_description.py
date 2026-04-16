"""Full-text extraction for a single job posting URL.

Stack inspired by ai_press_review.extractors.web_content:
trafilatura (best for long-form content) -> BeautifulSoup fallback.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

from ..settings import Settings
from ..utils import word_count

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def _fetch(url: str, settings: Settings) -> str:
    headers = {"User-Agent": settings.user_agent, "Accept-Language": "en,fr;q=0.9"}
    r = requests.get(url, headers=headers, timeout=settings.extraction_timeout)
    r.raise_for_status()
    return r.text


def _extract_trafilatura(html: str) -> str:
    try:
        import trafilatura
    except ImportError:
        return ""
    text = trafilatura.extract(
        html,
        favor_recall=True,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    return text or ""


def _extract_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    # Prefer main / article / the largest div.
    node = soup.find("main") or soup.find("article")
    if node is None:
        candidates = soup.find_all("div")
        node = max(candidates, key=lambda n: len(n.get_text(" ", strip=True)), default=None)
    if node is None:
        return soup.get_text(" ", strip=True)
    return node.get_text(" ", strip=True)


@lru_cache(maxsize=512)
def _cached_fetch(url: str, ua: str, timeout: int) -> str:
    headers = {"User-Agent": ua}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_job_description(url: str, settings: Settings) -> str:
    """Fetch + extract the full job description from a URL.

    Returns empty string on any failure. The caller decides whether to keep
    the posting (`min_jd_words` threshold).
    """
    try:
        html = _cached_fetch(url, settings.user_agent, settings.extraction_timeout)
    except Exception as e:
        log.warning("fetch failed for %s: %s", url, e)
        return ""
    text = _extract_trafilatura(html)
    if word_count(text) < settings.min_jd_words:
        alt = _extract_bs4(html)
        if word_count(alt) > word_count(text):
            text = alt
    return text.strip()


def batch_extract(urls: Iterable[str], settings: Settings, max_workers: int = 8) -> dict[str, str]:
    """Parallel extraction. Returns {url: text}."""
    urls = list(urls)
    results: dict[str, str] = {u: "" for u in urls}
    if not urls:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_url = {ex.submit(extract_job_description, u, settings): u for u in urls}
        for fut in as_completed(future_to_url):
            u = future_to_url[fut]
            try:
                results[u] = fut.result()
            except Exception as e:
                log.warning("extract failed for %s: %s", u, e)
    return results

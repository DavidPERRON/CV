"""LinkedIn Job Alerts collector via IMAP Gmail.

Reads emails matching configured filters (from, subject) and extracts job
links + titles. Credentials come from env vars: LINKEDIN_EMAIL, GMAIL_APP_PASSWORD.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header
from typing import Iterable

from bs4 import BeautifulSoup

from ..models import JobPosting
from ..settings import Settings
from ..utils import fingerprint

log = logging.getLogger(__name__)

_LINKEDIN_JOB_RE = re.compile(r"https?://[^\s\"']*linkedin\.com/(?:jobs/view|comm/jobs/view)/[0-9]+[^\s\"']*")


def collect_linkedin_emails(filters: Iterable[dict], settings: Settings, since_days: int = 7) -> list[JobPosting]:
    if not (settings.linkedin_email and settings.gmail_app_password):
        log.info("LinkedIn IMAP credentials not set — skipping.")
        return []
    try:
        M = imaplib.IMAP4_SSL(settings.imap_host)
        M.login(settings.linkedin_email, settings.gmail_app_password)
    except Exception as e:
        log.error("IMAP login failed: %s", e)
        return []
    postings: list[JobPosting] = []
    try:
        for f in filters:
            mailbox = f.get("mailbox", settings.imap_folder)
            from_contains = f.get("from_contains", "")
            subject_contains = f.get("subject_contains", "")
            M.select(f'"{mailbox}"')
            criteria = [f'SINCE {_since(since_days)}']
            if from_contains:
                criteria.append(f'FROM "{from_contains}"')
            if subject_contains:
                criteria.append(f'SUBJECT "{subject_contains}"')
            typ, data = M.search(None, *criteria) if len(criteria) > 1 else M.search(None, criteria[0])
            if typ != "OK":
                continue
            ids = data[0].split()
            log.info("IMAP: %d messages matched %s", len(ids), criteria)
            for mid in ids[-100:]:  # cap per pass
                typ, msg_data = M.fetch(mid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                postings.extend(_extract_postings_from_msg(msg, source_name=f.get("name", "linkedin_email")))
    finally:
        try:
            M.close()
        except Exception:
            pass
        try:
            M.logout()
        except Exception:
            pass
    # Deduplicate by fingerprint
    uniq: dict[str, JobPosting] = {}
    for p in postings:
        uniq.setdefault(p.fingerprint, p)
    return list(uniq.values())


def _since(days: int) -> str:
    from datetime import datetime, timedelta
    d = datetime.utcnow() - timedelta(days=days)
    return d.strftime("%d-%b-%Y")


def _decode(h: str | None) -> str:
    if not h:
        return ""
    parts = decode_header(h)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_postings_from_msg(msg, source_name: str) -> list[JobPosting]:
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html_body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
    else:
        if msg.get_content_type() == "text/html":
            try:
                html_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                html_body = ""

    if not html_body:
        return []

    soup = BeautifulSoup(html_body, "html.parser")
    postings: list[JobPosting] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _LINKEDIN_JOB_RE.search(href):
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue
        # company is often the sibling cell — best effort
        company = _guess_company(a)
        job = JobPosting(
            title=title[:160],
            company=company or "LinkedIn (unknown company)",
            url=href.split("?")[0],  # strip LinkedIn tracking
            source=f"linkedin_email:{source_name}",
        )
        job.fingerprint = fingerprint(job.company, job.title, job.url)
        postings.append(job)
    return postings


def _guess_company(anchor) -> str:
    # Walk up to find a text node that looks like a company name
    parent = anchor.parent
    for _ in range(4):
        if parent is None:
            break
        text = parent.get_text(" ", strip=True)
        # Very loose heuristic: line right after the title usually has the company
        lines = [t.strip() for t in text.split("\n") if t.strip()]
        if len(lines) >= 2:
            # Anchor text is usually first; take next short line
            for line in lines[1:]:
                if 2 < len(line) < 80 and not line.startswith("http"):
                    return line
        parent = parent.parent
    return ""

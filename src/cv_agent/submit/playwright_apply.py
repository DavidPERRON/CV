"""Semi-auto application submission via Playwright.

Design choices:
- headless=False by default (you WATCH the browser while it pre-fills).
- Persistent user_data_dir — you stay logged in to LinkedIn / career sites
  between runs. Session cookies NEVER leave your machine.
- The script fills what it can deterministically (CV upload, cover letter)
  then STOPS before the final Submit button. It prints a gate message and
  waits for an explicit `ENTER` keystroke from the operator.
- Ctrl+C or timeout -> status "aborted_by_user" and NO submission.

Adapters per site are kept minimal. LinkedIn Easy Apply is the only fully
supported automation path; generic ATS forms (Greenhouse, Lever, Workable,
Workday, SmartRecruiters) are best-effort detection + open-the-tab fallback.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Callable

from ..settings import Settings

log = logging.getLogger(__name__)

GATE_BANNER = r"""
================================================================
READY TO SUBMIT — review the pre-filled form in the browser now.
Press ENTER in this terminal to confirm submission.
Press Ctrl+C to abort (no submission will be sent).
================================================================
"""


def _wait_for_human(timeout_minutes: int) -> bool:
    """Block until ENTER is pressed, Ctrl+C aborts, or timeout elapses.

    Returns True on ENTER, False on Ctrl+C or timeout.
    """
    print(GATE_BANNER, flush=True)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("gate timeout")))
    signal.alarm(timeout_minutes * 60)
    try:
        input()  # wait for ENTER
        return True
    except (KeyboardInterrupt, TimeoutError):
        return False
    finally:
        signal.alarm(0)


def submit_with_human_gate(
    job_url: str,
    cv_pdf_path: Path,
    cover_md_path: Path,
    settings: Settings,
) -> str:
    """Open the browser, pre-fill, wait for human ENTER, submit.

    Returns one of: "submitted" | "aborted_by_user" | "failed".
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    user_data_dir = os.environ.get(
        settings.submit_user_data_dir_env, str(Path.cwd() / ".playwright-user-data")
    )
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    cover_text = cover_md_path.read_text(encoding="utf-8") if cover_md_path.exists() else ""

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=settings.submit_headless,
            accept_downloads=True,
        )
        page = ctx.new_page()
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)

            adapter = _pick_adapter(job_url)
            pre_submit_ready = adapter(page, cv_pdf_path, cover_text)
            if not pre_submit_ready:
                log.warning("Adapter could not fully pre-fill. Human will complete manually.")

            if not _wait_for_human(settings.submit_abort_after_minutes):
                log.info("Submission aborted by user.")
                return "aborted_by_user"

            # On ENTER: click the final submit button the adapter pointed to.
            clicked = _click_final_submit(page)
            if clicked:
                page.wait_for_timeout(3000)
                return "submitted"
            return "failed"
        except Exception as e:
            log.exception("submission error: %s", e)
            return "failed"
        finally:
            try:
                ctx.close()
            except Exception:
                pass


# ------------------------------------------------------------
# Site adapters — each returns True if pre-fill reached a Submit-ready state.
# ------------------------------------------------------------
def _pick_adapter(url: str) -> Callable:
    u = url.lower()
    if "linkedin.com" in u:
        return _adapter_linkedin
    if "greenhouse.io" in u or "boards.greenhouse.io" in u:
        return _adapter_greenhouse
    if "lever.co" in u or "jobs.lever.co" in u:
        return _adapter_lever
    if "workable.com" in u:
        return _adapter_workable
    if "myworkdayjobs" in u or "workday" in u:
        return _adapter_workday
    return _adapter_generic


def _adapter_linkedin(page, cv_pdf_path: Path, cover_text: str) -> bool:
    """Click Easy Apply, upload CV, paste cover. Stop before Submit."""
    try:
        page.wait_for_selector("button:has-text('Easy Apply'), button:has-text('Postuler')", timeout=8000)
        btn = page.locator("button:has-text('Easy Apply'), button:has-text('Postuler')").first
        btn.click()
        page.wait_for_timeout(1500)
        # File input for resume
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0 and cv_pdf_path.exists():
            inputs.first.set_input_files(str(cv_pdf_path))
        # Some flows have a Next button — click forward while we see one.
        for _ in range(6):
            if page.locator("button:has-text('Submit application'), button:has-text('Envoyer la candidature')").count() > 0:
                break
            nxt = page.locator("button:has-text('Next'), button:has-text('Suivant'), button:has-text('Continuer')")
            if nxt.count() == 0:
                break
            nxt.first.click()
            page.wait_for_timeout(1000)
        # Try to paste cover letter in any textarea if present
        if cover_text:
            ta = page.locator("textarea").first
            try:
                ta.fill(cover_text[:5000])
            except Exception:
                pass
        return True
    except Exception as e:
        log.warning("linkedin adapter partial: %s", e)
        return False


def _adapter_greenhouse(page, cv_pdf_path: Path, cover_text: str) -> bool:
    try:
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0 and cv_pdf_path.exists():
            inputs.first.set_input_files(str(cv_pdf_path))
        if cover_text:
            ta = page.locator("textarea").first
            try:
                ta.fill(cover_text[:5000])
            except Exception:
                pass
        return True
    except Exception as e:
        log.warning("greenhouse adapter partial: %s", e)
        return False


def _adapter_lever(page, cv_pdf_path: Path, cover_text: str) -> bool:
    try:
        # Lever often has a big "Apply for this job" link first
        if page.locator("a.postings-btn:has-text('Apply')").count() > 0:
            page.locator("a.postings-btn:has-text('Apply')").first.click()
            page.wait_for_timeout(1500)
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0 and cv_pdf_path.exists():
            inputs.first.set_input_files(str(cv_pdf_path))
        if cover_text:
            cov = page.locator("textarea[name='comments'], textarea[name='cover_letter']").first
            try:
                cov.fill(cover_text[:5000])
            except Exception:
                pass
        return True
    except Exception as e:
        log.warning("lever adapter partial: %s", e)
        return False


def _adapter_workable(page, cv_pdf_path: Path, cover_text: str) -> bool:
    try:
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0 and cv_pdf_path.exists():
            inputs.first.set_input_files(str(cv_pdf_path))
        return True
    except Exception:
        return False


def _adapter_workday(page, cv_pdf_path: Path, cover_text: str) -> bool:
    # Workday is extremely variable; we just open the page and let the human drive.
    return False


def _adapter_generic(page, cv_pdf_path: Path, cover_text: str) -> bool:
    try:
        inputs = page.locator("input[type='file']")
        if inputs.count() > 0 and cv_pdf_path.exists():
            inputs.first.set_input_files(str(cv_pdf_path))
        return True
    except Exception:
        return False


def _click_final_submit(page) -> bool:
    """After human ENTER, click the primary submit control. Conservative:
    only click buttons whose label clearly says submit/send/apply."""
    candidates = [
        "button:has-text('Submit application')",
        "button:has-text('Envoyer la candidature')",
        "button[type='submit']:has-text('Submit')",
        "button:has-text('Apply now')",
        "button:has-text('Send application')",
    ]
    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            try:
                loc.first.click()
                return True
            except Exception:
                continue
    log.warning("No final submit button detected. Human must click in the browser.")
    return False

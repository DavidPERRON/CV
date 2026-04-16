"""Command-line entry points. Thin wrappers around `pipeline.py`.

Usage after `pip install -e .`:
    cv-search
    cv-generate --fingerprint <fp>
    cv-submit   --fingerprint <fp> --cv-pdf path/to/cv.pdf
    cv-reject   --fingerprint <fp> --reason "not a fit"

Or call `python scripts/search_and_score.py` etc.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import (
    generate_draft,
    reject_pending,
    run_search,
    submit_pending,
)
from .settings import load_settings


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING - (10 * verbosity)
    logging.basicConfig(
        level=max(logging.DEBUG, level),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def search_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Search + score job postings against the master CV.")
    ap.add_argument("-v", action="count", default=1, help="increase verbosity")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Smoke test: cap to --max-jobs postings, write under runs/_dry-<stamp>/, "
        "skip state mutations. Use to validate the pipeline + LLM fallback without "
        "polluting the repo.",
    )
    ap.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Override the per-run posting cap (default 3 in --dry-run, "
        "config value otherwise).",
    )
    ap.add_argument(
        "--with-drafts",
        type=int,
        default=0,
        help="In --dry-run, also fully draft the top N scored postings "
        "(CV adapté + cover letter + positioning + competencies + gap analysis). "
        "Default 0.",
    )
    args = ap.parse_args(argv)
    _configure_logging(args.v)
    settings = load_settings()
    queue_path = run_search(
        settings,
        dry_run=args.dry_run,
        max_jobs=args.max_jobs,
        with_drafts=args.with_drafts,
    )
    print(f"OK queue written to {queue_path}")
    if args.dry_run:
        print(f"(dry-run — outputs under {queue_path.parent}/, state untouched)")
        summary = queue_path.parent / "summary.md"
        if summary.exists():
            print(f"Summary: {summary}")
    # Print a short summary of top 10 from the queue
    with queue_path.open("r", encoding="utf-8") as f:
        rows = [json.loads(ln) for ln in f if ln.strip()]
    for row in rows[:10]:
        print(f"  [{row['score']:3d}] {row['seniority']:9} {row['sector']:15} — {row['title']} @ {row['company']}")
        print(f"          {row['fingerprint']}  {row['url']}")
    return 0


def generate_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a tailored application draft for a scored job.")
    ap.add_argument("--fingerprint", "-f", required=True, help="fingerprint from the queue")
    ap.add_argument("--language", default=None, help="EN or FR (default: from config)")
    ap.add_argument("--extra", default="", help="extra instructions passed to the LLM")
    ap.add_argument("--allow-invention", action="store_true", help="disable the zero-invention guard (not recommended)")
    ap.add_argument("-v", action="count", default=1)
    args = ap.parse_args(argv)
    _configure_logging(args.v)
    settings = load_settings()
    try:
        draft = generate_draft(
            fingerprint=args.fingerprint,
            settings=settings,
            language=args.language,
            extra_instructions=args.extra,
            strict_no_invention=not args.allow_invention,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"OK draft ready for {draft.job.title} @ {draft.job.company}")
    return 0


def submit_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Open the application page in Playwright, pre-fill, wait for human ENTER, submit.",
    )
    ap.add_argument("--fingerprint", "-f", required=True)
    ap.add_argument("--cv-pdf", type=Path, default=None, help="path to the CV PDF to upload")
    ap.add_argument("-v", action="count", default=1)
    args = ap.parse_args(argv)
    _configure_logging(args.v)
    settings = load_settings()
    try:
        status = submit_pending(args.fingerprint, settings, cv_pdf_path=args.cv_pdf)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"final status: {status}")
    return 0 if status == "submitted" else 1


def reject_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reject a pending application (will be archived with reason).")
    ap.add_argument("--fingerprint", "-f", required=True)
    ap.add_argument("--reason", "-r", default="")
    args = ap.parse_args(argv)
    _configure_logging(1)
    settings = load_settings()
    reject_pending(args.fingerprint, args.reason, settings)
    print("rejected")
    return 0


if __name__ == "__main__":
    cmds = {"search": search_main, "generate": generate_main, "submit": submit_main, "reject": reject_main}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print("usage: python -m cv_agent.cli {search|generate|submit|reject} [...]", file=sys.stderr)
        sys.exit(64)
    sys.exit(cmds[sys.argv[1]](sys.argv[2:]))

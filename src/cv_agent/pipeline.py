"""Pipeline orchestration. Direct analogue of ai_press_review.pipeline.

Four public entry points:

- run_search(settings)                     -> writes runs/<date>/queue.jsonl
- generate_draft(fingerprint, settings)    -> writes runs/<date>/<slug>/* + pending_applications state
- submit_pending(fingerprint, settings)    -> Playwright semi-auto submit (stop before submit)
- reject_pending(fingerprint, reason)      -> moves the pending entry to applied with status=rejected
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .collectors.careers import collect_career_pages
from .collectors.linkedin_email import collect_linkedin_emails
from .collectors.rss_jobs import collect_rss
from .editorial.cv_generator import GenerationOptions, InventionError, generate_application
from .editorial.scorer import ScoringResult, score_posting
from .extractors.job_description import batch_extract
from .llm.client import LLMClient
from .models import ApplicationDraft, JobPosting
from .render.cv_html import render_cv_html
from .render.index_html import write_index
from .render.report_html import write_report
from .settings import DATA_DIR, RUNS_DIR, Settings
from .state import (
    add_pending,
    is_known,
    load_pending,
    mark_applied,
    remove_pending,
)
from .utils import ensure_dir, now_iso, slugify, today_iso, word_count

log = logging.getLogger(__name__)

MASTER_CV_CANDIDATES = [
    DATA_DIR / "master_cv.md",
    DATA_DIR / "master_cv.en.md",
    DATA_DIR / "master_cv.fr.md",
]


def _load_master_cv(language: str | None = None) -> str:
    lang_path = None
    if language:
        lang_path = DATA_DIR / f"master_cv.{language.lower()}.md"
    for p in [lang_path, DATA_DIR / "master_cv.md", *MASTER_CV_CANDIDATES]:
        if p and p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "No master CV found. Create data/master_cv.md (or master_cv.en.md / master_cv.fr.md)."
    )


def _run_dir(dry_run: bool = False) -> Path:
    if dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        return ensure_dir(RUNS_DIR / f"_dry-{stamp}")
    return ensure_dir(RUNS_DIR / today_iso())


def _job_dir(job: JobPosting, dry_run: bool = False) -> Path:
    slug = job.slug or slugify(f"{job.company}_{job.title}")
    return ensure_dir(_run_dir(dry_run=dry_run) / slug)


# ------------------------------------------------------------
# 1. Search + score
# ------------------------------------------------------------
def run_search(
    settings: Settings,
    dry_run: bool = False,
    max_jobs: int | None = None,
    with_drafts: int = 0,
) -> Path:
    """Collect, extract, score postings.

    dry_run=True:
      - cap to `max_jobs` postings (default 3) to spare API budget
      - write outputs under runs/_dry-<utc-stamp>/ instead of runs/<date>/
      - skip any state mutation (no fingerprints recorded as 'applied/known')
      - also writes a human-readable `summary.md` at the run-dir root
      - if `with_drafts > 0`, fully drafts the top-N scored postings
        (CV adapté + cover letter + positioning + competencies + gap analysis)
    """
    sources = settings.load_sources()
    log.info("Loading master CV...")
    master_cv = _load_master_cv()

    # Collect (track counts per source family)
    log.info("Collecting RSS feeds...")
    postings: list[JobPosting] = []
    source_counts: dict[str, int] = {}
    job_boards = sources.get("job_boards", {})
    rss_hits = collect_rss(job_boards.get("rss", []))
    source_counts["rss"] = len(rss_hits)
    postings += rss_hits
    log.info("Collecting LinkedIn email alerts...")
    email_hits = collect_linkedin_emails(job_boards.get("email", []), settings)
    source_counts["linkedin-email"] = len(email_hits)
    postings += email_hits
    log.info("Collecting career pages...")
    career_hits = collect_career_pages(sources, settings)
    source_counts["careers"] = len(career_hits)
    postings += career_hits

    total_collected = len(postings)

    # Dedup vs already-applied (skipped in dry_run so the test stays repeatable)
    before = len(postings)
    if not dry_run:
        postings = [p for p in postings if not is_known(p.fingerprint)]
        log.info("Dedup: %d -> %d after removing known fingerprints.", before, len(postings))
    else:
        log.info("Dry-run: skipping known-fingerprint dedup (kept %d).", before)

    # Exclude explicitly blocked companies
    excl = {c.strip().lower() for c in settings.excluded_companies if c.strip()}
    if excl:
        postings = [p for p in postings if p.company.strip().lower() not in excl]

    # Cap
    cap = (max_jobs if dry_run else settings.max_jobs_per_run)
    if dry_run and cap is None:
        cap = 3
    postings = postings[: cap]
    if dry_run:
        log.info("Dry-run: capped to %d postings.", len(postings))

    # Extract full JD in parallel
    log.info("Extracting full JDs for %d postings...", len(postings))
    urls = [p.url for p in postings]
    jds = batch_extract(urls, settings)
    for p in postings:
        text = jds.get(p.url, "") or p.description
        p.description = text

    # Drop thin descriptions — but never drop LinkedIn email postings: their JD
    # can't be scraped (login wall) so we score on title + company alone.
    before_thin = len(postings)
    postings = [
        p for p in postings
        if word_count(p.description) >= settings.min_jd_words
        or p.source.startswith("linkedin_email:")
    ]
    thin_dropped = before_thin - len(postings)
    log.info("After min_jd_words filter: %d postings (%d thin).", len(postings), thin_dropped)

    # Score
    llm = LLMClient(settings)
    scored: list[tuple[JobPosting, ScoringResult]] = []
    gate_dropped = 0
    for p in postings:
        res = score_posting(p, master_cv, settings, llm=llm)
        if not res.pass_seniority_gate:
            gate_dropped += 1
            log.info("drop (gate): %s @ %s [%s] %s", p.title, p.company, res.seniority, res.rationale[:80])
            continue
        p.score = res.fit_score
        p.seniority_signal = res.seniority
        if res.sector:
            p.sector = res.sector
        scored.append((p, res))

    # Sort by score desc
    scored.sort(key=lambda pr: pr[0].score, reverse=True)

    # Persist queue
    queue_path = _run_dir(dry_run=dry_run) / "queue.jsonl"
    with queue_path.open("w", encoding="utf-8") as f:
        for job, res in scored:
            f.write(json.dumps({
                "fingerprint": job.fingerprint,
                "score": job.score,
                "seniority": res.seniority,
                "sector": job.sector,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "rationale": res.rationale,
                "job": job.to_dict(),
            }, ensure_ascii=False) + "\n")
    log.info("Wrote %d scored postings to %s", len(scored), queue_path)

    # Render HTML report alongside queue.jsonl
    llm_label = f"{settings.llm_provider}/{settings.llm_model}"
    try:
        report_path = write_report(queue_path, llm_model=llm_label, dry_run=dry_run)
        log.info("HTML report written to %s", report_path)
    except Exception as e:
        log.warning("HTML report generation failed (non-fatal): %s", e)

    # Regenerate the global runs/index.html (skip for dry-runs — they land in _dry-* folders)
    if not dry_run:
        try:
            index_path = write_index(RUNS_DIR)
            log.info("Index written to %s", index_path)
        except Exception as e:
            log.warning("Index generation failed (non-fatal): %s", e)

    # Persist per-job stubs for those above mid_threshold (dry-run: keep all of them).
    threshold = 0 if dry_run else settings.mid_threshold
    for job, res in scored:
        if job.score < threshold:
            continue
        jdir = _job_dir(job, dry_run=dry_run)
        (jdir / "job.json").write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (jdir / "scoring.json").write_text(json.dumps({
            "seniority": res.seniority,
            "fit_score": res.fit_score,
            "sector": res.sector,
            "rationale": res.rationale,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (jdir / "status.txt").write_text("scored", encoding="utf-8")

    # Optional: draft full application for top-N in dry-run
    drafts_written: list[dict[str, Any]] = []
    if dry_run and with_drafts > 0 and scored:
        targets = scored[: with_drafts]
        log.info("Dry-run: drafting full application for top %d scored postings.", len(targets))
        for job, _res in targets:
            try:
                draft = generate_draft(
                    fingerprint=job.fingerprint,
                    settings=settings,
                    language=settings.default_language,
                    dry_run=True,
                )
                jdir = _job_dir(job, dry_run=True)
                drafts_written.append({
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                    "dir": str(jdir.relative_to(RUNS_DIR.parent)),
                    "status": "drafted",
                })
            except Exception as e:  # InventionError, LLM failure, render, ...
                log.warning("Draft failed for %s @ %s: %s", job.title, job.company, e)
                drafts_written.append({
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                    "dir": "",
                    "status": f"failed: {type(e).__name__}: {e}",
                })

    # Dry-run: write a human-readable summary.md at the run-dir root
    if dry_run:
        summary_path = _run_dir(dry_run=dry_run) / "summary.md"
        summary_path.write_text(
            _render_dry_run_summary(
                settings=settings,
                source_counts=source_counts,
                total_collected=total_collected,
                thin_dropped=thin_dropped,
                gate_dropped=gate_dropped,
                scored=scored,
                drafts=drafts_written,
                run_dir=_run_dir(dry_run=True),
            ),
            encoding="utf-8",
        )
        log.info("Dry-run summary written to %s", summary_path)

    return queue_path


def _render_dry_run_summary(
    settings: Settings,
    source_counts: dict[str, int],
    total_collected: int,
    thin_dropped: int,
    gate_dropped: int,
    scored: list[tuple[JobPosting, ScoringResult]],
    drafts: list[dict[str, Any]],
    run_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append(f"# Dry-run summary — {run_dir.name}")
    lines.append("")
    lines.append(
        f"**LLM chain** : `{settings.llm_provider}/{settings.llm_model}` "
        f"→ `{settings.llm_fallback_provider}/{settings.llm_fallback_model}`"
    )
    lines.append("")
    lines.append("## Sources scannées")
    lines.append("")
    for name, count in source_counts.items():
        lines.append(f"- **{name}** : {count} offres collectées")
    lines.append(f"- **total brut** : {total_collected}")
    lines.append("")
    lines.append("## Filtrage")
    lines.append("")
    lines.append(f"- `{thin_dropped}` offres rejetées (description < {settings.min_jd_words} mots)")
    lines.append(f"- `{gate_dropped}` offres rejetées (seniority gate)")
    lines.append(f"- `{len(scored)}` offres scorées et retenues")
    lines.append("")
    if scored:
        lines.append("## Offres scorées")
        lines.append("")
        lines.append("| Score | Titre | Entreprise | Lieu | Seniority | Secteur | Source | Postuler |")
        lines.append("|------:|-------|------------|------|-----------|---------|--------|----------|")
        for job, res in scored:
            src = (job.source or "").split(":")[0] or "?"
            lines.append(
                f"| {job.score:3d} | {job.title} | {job.company} | "
                f"{job.location or '—'} | {res.seniority} | {job.sector or '—'} | "
                f"{src} | [lien]({job.url}) |"
            )
        lines.append("")
        lines.append("### Rationale par offre")
        lines.append("")
        for job, res in scored:
            lines.append(f"- **{job.title} @ {job.company}** (score {job.score}) — {res.rationale}")
        lines.append("")
    else:
        lines.append("## Aucune offre scorée — vérifier les sources / les seuils.")
        lines.append("")
    if drafts:
        lines.append("## CV + lettres rédigés")
        lines.append("")
        for d in drafts:
            if d["status"] == "drafted":
                lines.append(f"- **{d['title']} @ {d['company']}**")
                lines.append(f"  - Dossier : `{d['dir']}/`")
                lines.append(f"  - Fichiers : `positioning.md`, `competencies.md`, "
                             f"`gap_analysis.md`, `cv_adapted.md`, `cv_adapted.html`, `cover.md`")
                lines.append(f"  - Page pour postuler : {d['url']}")
            else:
                lines.append(f"- **{d['title']} @ {d['company']}** — {d['status']}")
        lines.append("")
    else:
        lines.append("## CV rédigés")
        lines.append("")
        lines.append("_Aucun — relance avec `--with-drafts N` pour rédiger les N meilleures offres._")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------
# 2. Generate application draft
# ------------------------------------------------------------
def generate_draft(
    fingerprint: str,
    settings: Settings,
    language: str | None = None,
    extra_instructions: str = "",
    strict_no_invention: bool = True,
    dry_run: bool = False,
) -> ApplicationDraft:
    job = _find_job_by_fingerprint(fingerprint)
    master_cv = _load_master_cv(language)

    opts = GenerationOptions(
        language=(language or settings.default_language).upper(),
        extra_instructions=extra_instructions,
        strict_no_invention=strict_no_invention,
    )

    try:
        draft = generate_application(job, master_cv, settings, options=opts)
    except InventionError as e:
        log.error(
            "Invention guard triggered for %s (%s). Suspects: %s",
            job.fingerprint, job.title, e.suspects,
        )
        raise

    jdir = _job_dir(job, dry_run=dry_run)
    (jdir / "positioning.md").write_text(draft.positioning, encoding="utf-8")
    (jdir / "competencies.md").write_text(draft.competencies, encoding="utf-8")
    (jdir / "gap_analysis.md").write_text(draft.gap_analysis, encoding="utf-8")
    (jdir / "cv_adapted.md").write_text(draft.cv_adapted, encoding="utf-8")
    (jdir / "cover.md").write_text(draft.cover_letter, encoding="utf-8")

    # Render HTML (best-effort)
    try:
        name, contact = _extract_identity(master_cv)
        html_content = render_cv_html(
            draft.cv_adapted,
            name=name,
            role_target=f"{job.title} — {job.company}",
            contact=contact,
            language=draft.language,
        )
        (jdir / "cv_adapted.html").write_text(html_content, encoding="utf-8")
    except Exception as e:
        log.warning("HTML render failed: %s", e)

    status = "dry_run_draft" if dry_run else "pending_review"
    (jdir / "status.txt").write_text(status, encoding="utf-8")

    # In dry_run we do NOT touch the pending state — the draft is disposable.
    if not dry_run:
        add_pending(
            job.fingerprint,
            {
                "job": job.to_dict(),
                "language": draft.language,
                "dir": str(jdir),
                "generated_at": draft.generated_at,
                "status": "pending_review",
            },
            settings,
        )
    log.info("Draft ready: %s", jdir)
    return draft


def _extract_identity(master_cv: str) -> tuple[str, str]:
    """Best-effort: first markdown heading as name, next line as contact."""
    lines = [ln.strip() for ln in master_cv.splitlines() if ln.strip()]
    name = "Candidate"
    contact = ""
    for ln in lines:
        if ln.startswith("# "):
            name = ln.lstrip("# ").strip()
            break
    # First line that has "@" or "+" is contact-ish
    for ln in lines:
        if "@" in ln or ln.startswith("+") or "linkedin.com" in ln.lower():
            contact = ln
            break
    return name, contact


# ------------------------------------------------------------
# 3. Submit / reject
# ------------------------------------------------------------
def submit_pending(fingerprint: str, settings: Settings, cv_pdf_path: Path | None = None) -> str:
    pending = load_pending()
    entry = pending.get(fingerprint)
    if not entry:
        raise KeyError(f"No pending application with fingerprint {fingerprint}")
    from .submit.playwright_apply import submit_with_human_gate

    job_dict = entry["job"]
    jdir = Path(entry["dir"])
    status = submit_with_human_gate(
        job_url=job_dict["url"],
        cv_pdf_path=cv_pdf_path or (jdir / "cv_adapted.pdf"),
        cover_md_path=jdir / "cover.md",
        settings=settings,
    )
    (jdir / "status.txt").write_text(status, encoding="utf-8")
    # Move out of pending regardless of final status — next step is human retry if aborted
    remove_pending(fingerprint)
    mark_applied(fingerprint, {**entry, "status": status, "submitted_at": now_iso()}, settings)
    return status


def reject_pending(fingerprint: str, reason: str, settings: Settings) -> None:
    entry = remove_pending(fingerprint)
    if not entry:
        raise KeyError(f"No pending application with fingerprint {fingerprint}")
    jdir = Path(entry.get("dir", ""))
    if jdir.exists():
        (jdir / "status.txt").write_text("rejected", encoding="utf-8")
        (jdir / "rejection_reason.txt").write_text(reason, encoding="utf-8")
    mark_applied(
        fingerprint,
        {**entry, "status": "rejected", "rejected_at": now_iso(), "reason": reason},
        settings,
    )


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _find_job_by_fingerprint(fp: str) -> JobPosting:
    """Scan today's + recent runs/ for a job.json matching the fingerprint."""
    for date_dir in sorted(RUNS_DIR.glob("*"), reverse=True):
        for job_file in date_dir.rglob("job.json"):
            data = json.loads(job_file.read_text(encoding="utf-8"))
            if data.get("fingerprint") == fp:
                return JobPosting(**{k: v for k, v in data.items() if k in JobPosting.__dataclass_fields__})
    raise KeyError(f"No job.json matching fingerprint {fp} in runs/")

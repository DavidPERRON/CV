"""Generate a self-contained HTML report from a scored queue.

Called from pipeline.run_search() after queue.jsonl is written.
Also usable standalone: python -m cv_agent.render.report_html <queue.jsonl>
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).parent / "templates" / "report-template.html"


def _tier(score: int) -> str:
    if score >= 80:
        return "top"
    if score >= 60:
        return "good"
    if score >= 40:
        return "mid"
    return "low"


def _score_badge_class(score: int) -> str:
    return f"score-badge tier-{_tier(score)}"


def _render_job_card(job: dict[str, Any]) -> str:
    score = int(job.get("score", 0))
    title = html.escape(job.get("title", "—"))
    company = html.escape(job.get("company", "—"))
    location = html.escape(job.get("location", "") or "—")
    sector = html.escape(job.get("sector", "") or "—")
    seniority = html.escape(job.get("seniority", "") or "—")
    url = html.escape(job.get("url", "") or "#")
    fingerprint = html.escape(job.get("fingerprint", "") or "")
    rationale_raw = job.get("rationale", "") or ""

    # Bold the first sentence of the rationale for quick scanning
    sentences = rationale_raw.split(". ", 1)
    if len(sentences) == 2:
        rationale_html = f"<strong>{html.escape(sentences[0])}.</strong> {html.escape(sentences[1])}"
    else:
        rationale_html = html.escape(rationale_raw)

    tier = _tier(score)
    badge_cls = _score_badge_class(score)

    cmd = f"cv-generate --fingerprint {fingerprint}" if fingerprint else ""

    copy_btn = (
        f'<button class="btn-copy" onclick="copyFp(&quot;{fingerprint}&quot;, this)">⧉ Commande</button>'
        if fingerprint else ""
    )
    fp_block = (
        f'<div class="fingerprint-row">'
        f'<span class="fp-label">Fingerprint :</span>'
        f'<code class="fp-code">{fingerprint}</code>'
        f'</div>'
        f'<div class="cmd-block">{html.escape(cmd)}</div>'
        if fingerprint else ""
    )

    return (
        f'\n  <div class="job-card" data-tier="{tier}" onclick="toggleCard(this)">'
        f'\n    <div class="job-header">'
        f'\n      <div class="{badge_cls}">'
        f"\n        {score}"
        f'\n        <span class="score-label">/100</span>'
        f"\n      </div>"
        f'\n      <div class="job-main">'
        f'\n        <div class="job-title">{title}</div>'
        f'\n        <div class="job-company">{company}</div>'
        f'\n        <div class="job-tags">'
        f'\n          <span class="tag sector">{sector}</span>'
        f'\n          <span class="tag location">📍 {location}</span>'
        f'\n          <span class="tag seniority">{seniority}</span>'
        f"\n        </div>"
        f'\n        <div class="score-bar-wrap tier-{tier}">'
        f'\n          <div class="score-bar-fill" style="width:{score}%"></div>'
        f"\n        </div>"
        f"\n      </div>"
        f'\n      <div class="job-actions" onclick="event.stopPropagation()">'
        f'\n        <a class="btn-link" href="{url}" target="_blank" rel="noopener">↗ Voir l\'offre</a>'
        f"\n        {copy_btn}"
        f"\n      </div>"
        f"\n    </div>"
        f'\n    <div class="job-details">'
        f'\n      <div class="rationale">{rationale_html}</div>'
        f"\n      {fp_block}"
        f"\n    </div>"
        f"\n  </div>"
    )


def render_report_html(
    queue_path: Path,
    llm_model: str = "",
    dry_run: bool = False,
    generated_at: str = "",
) -> str:
    """Read queue.jsonl at queue_path, return a fully self-contained HTML string."""
    jobs: list[dict[str, Any]] = []
    if queue_path.exists():
        for line in queue_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    jobs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    jobs.sort(key=lambda j: j.get("score", 0), reverse=True)

    folder = queue_path.parent.name
    # Dry-run folders are named _dry-<utc-stamp>, e.g. _dry-2026-04-04T12-00-00Z
    if folder.startswith("_dry-"):
        folder = folder[5:]
    run_date = folder.split("T")[0]
    if not generated_at:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    count_top  = sum(1 for j in jobs if j.get("score", 0) >= 80)
    count_good = sum(1 for j in jobs if 60 <= j.get("score", 0) < 80)
    count_mid  = sum(1 for j in jobs if 40 <= j.get("score", 0) < 60)
    count_low  = sum(1 for j in jobs if j.get("score", 0) < 40)

    cards_html = "\n".join(_render_job_card(j) for j in jobs) if jobs else ""

    dry_pill = (
        '<div class="meta-pill" style="color:#f97316;border-color:rgba(249,115,22,0.4)">🧪 DRY RUN</div>'
        if dry_run else ""
    )

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{{TITLE}}", html.escape(f"CV Agent — {run_date}"))
        .replace("{{DATE}}", html.escape(run_date))
        .replace("{{LLM_MODEL}}", html.escape(llm_model or "—"))
        .replace("{{TOTAL}}", str(len(jobs)))
        .replace("{{COUNT_TOP}}", str(count_top))
        .replace("{{COUNT_GOOD}}", str(count_good))
        .replace("{{COUNT_MID}}", str(count_mid))
        .replace("{{COUNT_LOW}}", str(count_low))
        .replace("{{DRY_RUN_PILL}}", dry_pill)
        .replace("{{GENERATED_AT}}", html.escape(generated_at))
        .replace("{{JOB_CARDS}}", cards_html)
    )


def write_report(
    queue_path: Path,
    llm_model: str = "",
    dry_run: bool = False,
) -> Path:
    """Render and write report.html next to queue.jsonl. Returns the report path."""
    html_content = render_report_html(queue_path, llm_model=llm_model, dry_run=dry_run)
    report_path = queue_path.parent / "report.html"
    report_path.write_text(html_content, encoding="utf-8")
    return report_path


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs") / "queue.jsonl"
    out = write_report(path)
    print(f"Report written to {out}")

"""Generate runs/index.html — historical dashboard across all runs.

Called from pipeline.run_search() after report.html is written.
Also usable standalone via scripts/build_index.py.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).parent / "templates" / "index-template.html"


def _tier(score: int) -> str:
    if score >= 80:
        return "top"
    if score >= 60:
        return "good"
    if score >= 40:
        return "mid"
    return "low"


def _load_run(run_dir: Path) -> dict[str, Any] | None:
    """Load metadata for a single run directory. Returns None if not a valid run."""
    queue = run_dir / "queue.jsonl"
    if not queue.exists():
        return None
    jobs: list[dict] = []
    for line in queue.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                jobs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not jobs:
        return None

    scores = [j.get("score", 0) for j in jobs]
    best = max(scores)
    count_top  = sum(1 for s in scores if s >= 80)
    count_good = sum(1 for s in scores if 60 <= s < 80)
    count_mid  = sum(1 for s in scores if 40 <= s < 60)
    count_low  = sum(1 for s in scores if s < 40)

    # Derive a clean date from the folder name (skip _dry- folders)
    name = run_dir.name
    if name.startswith("_"):
        return None
    date = name.split("T")[0]

    return {
        "date": date,
        "dir": run_dir,
        "total": len(jobs),
        "best": best,
        "count_top": count_top,
        "count_good": count_good,
        "count_mid": count_mid,
        "count_low": count_low,
        "jobs": jobs,
        "has_report": (run_dir / "report.html").exists(),
    }


def _render_bar_segment(count: int, tier: str) -> str:
    if count == 0:
        return ""
    return f'<span class="bar-segment {tier}">{count}</span>'


def _render_run_row(run: dict[str, Any]) -> str:
    date = html.escape(run["date"])
    total = run["total"]
    best = run["best"]
    best_tier = _tier(best)

    bars = (
        _render_bar_segment(run["count_top"],  "top")
        + _render_bar_segment(run["count_good"], "good")
        + _render_bar_segment(run["count_mid"],  "mid")
        + _render_bar_segment(run["count_low"],  "low")
    )
    if not bars:
        bars = '<span class="bar-segment none">0</span>'

    report_link = ""
    if run["has_report"]:
        report_link = f'<span class="run-link">📊 Rapport</span>'

    return f"""<a class="run-row" href="{date}/report.html" {"" if run["has_report"] else 'style="pointer-events:none;opacity:.5"'}>
  <div class="run-date">{date}</div>
  <div class="run-bars">{bars}</div>
  <div class="run-best">Meilleur : <strong class="{best_tier}">{best}</strong>/100</div>
  <div class="run-best" style="min-width:60px;color:var(--c-muted)">{total} offres</div>
  {report_link}
</a>"""


def _render_all_time(runs: list[dict[str, Any]], top_n: int = 10) -> str:
    """Collect the top-N jobs across all runs and render a leaderboard section."""
    all_jobs: list[dict[str, Any]] = []
    for run in runs:
        for j in run["jobs"]:
            j = dict(j)
            j["_run_date"] = run["date"]
            all_jobs.append(j)

    all_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
    top_jobs = all_jobs[:top_n]

    if not top_jobs:
        return ""

    rows = []
    for j in top_jobs:
        score = j.get("score", 0)
        tier = _tier(score)
        title = html.escape(j.get("title", "—"))
        company = html.escape(j.get("company", "—"))
        url = j.get("url", "") or ""
        run_date = html.escape(j.get("_run_date", ""))
        link = f'<a class="job-mini-link" href="{html.escape(url)}" target="_blank" rel="noopener">↗ Voir l\'offre</a>' if url else ""
        rows.append(f"""<div class="job-mini">
  <span class="score-chip {tier}">{score}</span>
  <div class="job-mini-info">
    <div class="job-mini-title">{title}</div>
    <div class="job-mini-company">{company}</div>
  </div>
  <div class="job-mini-date">{run_date}</div>
  {link}
</div>""")

    rows_html = "\n".join(rows)
    return f"""<div class="all-time-section">
  <div class="section-title">Top {top_n} offres — tous runs confondus</div>
  {rows_html}
</div>"""


def render_index_html(runs_dir: Path, generated_at: str = "") -> str:
    """Scan runs_dir for valid run folders, build and return the index HTML."""
    if not generated_at:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    runs: list[dict[str, Any]] = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if d.is_dir():
            run = _load_run(d)
            if run:
                runs.append(run)

    total_runs = len(runs)
    total_jobs = sum(r["total"] for r in runs)
    total_top  = sum(r["count_top"] for r in runs)
    best_score = max((r["best"] for r in runs), default=0)

    run_rows_html = "\n".join(_render_run_row(r) for r in runs) if runs else (
        '<p style="color:var(--c-muted);padding:24px 0">Aucun run trouvé.</p>'
    )
    all_time_html = _render_all_time(runs)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{{GENERATED_AT}}", html.escape(generated_at))
        .replace("{{TOTAL_RUNS}}", str(total_runs))
        .replace("{{TOTAL_JOBS}}", str(total_jobs))
        .replace("{{TOTAL_TOP}}", str(total_top))
        .replace("{{BEST_SCORE}}", str(best_score))
        .replace("{{RUN_ROWS}}", run_rows_html)
        .replace("{{ALL_TIME_SECTION}}", all_time_html)
    )


def write_index(runs_dir: Path) -> Path:
    """Render and write runs/index.html. Returns the output path."""
    html_content = render_index_html(runs_dir)
    out = runs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    return out

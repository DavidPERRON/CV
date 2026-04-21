#!/usr/bin/env python3
"""Format the scored queue into a GitHub Actions step summary and an HTML email body.

Usage (called by daily-search.yml):
    python3 scripts/format_summary.py --date 2026-04-20 \
        --github-step-summary $GITHUB_STEP_SUMMARY \
        --email-body /tmp/email_body.html \
        --github-output $GITHUB_OUTPUT

All arguments are optional — the script degrades gracefully if a path is absent.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_queue(date: str, queue_path: Path | None = None) -> list[dict]:
    path = queue_path or (ROOT / "runs" / date / "queue.jsonl")
    if not path.exists():
        return []
    jobs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                jobs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return sorted(jobs, key=lambda j: j.get("score", 0), reverse=True)


def _tier_emoji(score: int) -> str:
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    if score >= 40:
        return "🟠"
    return "🔴"


# ── GitHub Actions step summary (Markdown) ───────────────────────────────────

def build_gha_summary(jobs: list[dict], date: str, exit_code: str) -> str:
    lines: list[str] = []
    lines.append(f"## CV Agent — {date}")
    lines.append("")
    lines.append(f"**Exit code :** `{exit_code or 'unknown'}`  |  "
                 f"**Offres scorées :** {len(jobs)}")
    lines.append("")

    if not jobs:
        lines.append("> Aucune offre scorée — vérifier sources / seuils.")
        return "\n".join(lines)

    top  = [j for j in jobs if j.get("score", 0) >= 80]
    good = [j for j in jobs if 60 <= j.get("score", 0) < 80]
    mid  = [j for j in jobs if 40 <= j.get("score", 0) < 60]
    low  = [j for j in jobs if j.get("score", 0) < 40]

    def _section(title: str, group: list[dict]) -> None:
        if not group:
            return
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Score | Entreprise | Poste | Lieu | Secteur | Lien |")
        lines.append("|------:|------------|-------|------|---------|------|")
        for j in group:
            score = j.get("score", 0)
            em = _tier_emoji(score)
            company = j.get("company", "—")
            title_j = j.get("title", "—")
            location = j.get("location", "—") or "—"
            sector = j.get("sector", "—") or "—"
            url = j.get("url", "")
            link = f"[↗]({url})" if url else "—"
            lines.append(f"| {em} **{score}** | {company} | {title_j} | {location} | {sector} | {link} |")
        lines.append("")
        lines.append("<details><summary>Rationale</summary>")
        lines.append("")
        for j in group:
            rationale = j.get("rationale", "")
            fp = j.get("fingerprint", "")
            lines.append(f"**{j.get('title','?')} @ {j.get('company','?')}** (score {j.get('score',0)})")
            lines.append(f"> {rationale}")
            if fp:
                lines.append(f"> `cv-generate --fingerprint {fp}`")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    _section("🟢 Top matches (score ≥ 80)", top)
    _section("🟡 Bonnes offres (60–79)", good)
    _section("🟠 Offres moyennes (40–59)", mid)
    _section("🔴 Faible match (< 40)", low)

    report_url = f"https://github.com/davidperron/cv/blob/main/runs/{date}/report.html"
    lines.append(f"📊 [Rapport HTML]({report_url}) · "
                 f"[Queue JSONL](https://github.com/davidperron/cv/blob/main/runs/{date}/queue.jsonl)")

    return "\n".join(lines)


# ── HTML email ────────────────────────────────────────────────────────────────

def build_html_email(jobs: list[dict], date: str) -> tuple[str, str]:
    """Return (subject, html_body)."""
    top  = [j for j in jobs if j.get("score", 0) >= 80]
    good = [j for j in jobs if 60 <= j.get("score", 0) < 80]
    count = len(jobs)

    subject = f"CV Agent — {count} offre(s) le {date}"

    def _tier_color(score: int) -> str:
        if score >= 80:
            return "#22c55e"
        if score >= 60:
            return "#eab308"
        if score >= 40:
            return "#f97316"
        return "#ef4444"

    def _job_row(j: dict) -> str:
        score = j.get("score", 0)
        color = _tier_color(score)
        company = html.escape(j.get("company", "—"))
        title_j = html.escape(j.get("title", "—"))
        location = html.escape(j.get("location", "") or "—")
        sector = html.escape(j.get("sector", "") or "—")
        url = j.get("url", "") or ""
        fp = j.get("fingerprint", "") or ""
        rationale = html.escape(j.get("rationale", "") or "")
        cmd = f"cv-generate --fingerprint {fp}" if fp else ""
        return f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2d3a;vertical-align:top">
            <span style="display:inline-block;background:rgba(0,0,0,0.2);color:{color};
                         font-weight:700;font-size:18px;padding:4px 10px;border-radius:6px;
                         border:1px solid {color}40">{score}</span>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2d3a;vertical-align:top">
            <div style="font-weight:600;color:#e2e8f0">{title_j}</div>
            <div style="color:#8892a4;font-size:12px;margin-top:2px">{company}</div>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2d3a;vertical-align:top;
                     color:#8892a4;font-size:12px">{location}<br>{sector}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2d3a;vertical-align:top;
                     font-size:12px;color:#8892a4">{rationale[:200]}{'…' if len(rationale) > 200 else ''}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2d3a;vertical-align:top">
            {"<a href='" + html.escape(url) + "' style='color:#a5b4fc;font-size:12px'>↗ Voir</a>" if url else ""}
            {"<br><code style='font-size:10px;color:#6366f1'>" + html.escape(cmd) + "</code>" if cmd else ""}
          </td>
        </tr>"""

    rows = "".join(_job_row(j) for j in jobs)

    if not jobs:
        rows = """
        <tr><td colspan="5" style="padding:32px;text-align:center;color:#8892a4">
          Aucune offre scorée aujourd'hui.
        </td></tr>"""

    report_url = f"https://github.com/davidperron/cv/blob/main/runs/{date}/report.html"

    body = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="background:#0f1117;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             margin:0;padding:24px">
  <div style="max-width:900px;margin:0 auto">

    <div style="background:#1a1d27;border:1px solid #2a2d3a;border-radius:12px;
                padding:24px 28px;margin-bottom:24px">
      <h1 style="font-size:20px;font-weight:700;color:#fff;margin:0 0 6px">
        CV Agent — Résultats du {html.escape(date)}
      </h1>
      <p style="color:#8892a4;margin:0;font-size:13px">
        {count} offre(s) analysée(s) ·
        <strong style="color:{'#22c55e' if top else '#eab308'}">{len(top)} top match(es)</strong> ·
        {len(good)} bonne(s) offre(s)
      </p>
    </div>

    <div style="background:#1a1d27;border:1px solid #2a2d3a;border-radius:12px;overflow:hidden">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#13151f">
            <th style="padding:10px 8px;text-align:left;font-size:11px;text-transform:uppercase;
                       letter-spacing:.06em;color:#8892a4;border-bottom:1px solid #2a2d3a">Score</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;text-transform:uppercase;
                       letter-spacing:.06em;color:#8892a4;border-bottom:1px solid #2a2d3a">Poste</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;text-transform:uppercase;
                       letter-spacing:.06em;color:#8892a4;border-bottom:1px solid #2a2d3a">Lieu · Secteur</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;text-transform:uppercase;
                       letter-spacing:.06em;color:#8892a4;border-bottom:1px solid #2a2d3a">Analyse</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;text-transform:uppercase;
                       letter-spacing:.06em;color:#8892a4;border-bottom:1px solid #2a2d3a">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <div style="margin-top:20px;text-align:center">
      <a href="{html.escape(report_url)}"
         style="display:inline-block;background:#6366f1;color:#fff;font-weight:600;
                padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px">
        📊 Ouvrir le rapport HTML complet
      </a>
    </div>

    <p style="text-align:center;color:#4a5568;font-size:11px;margin-top:20px">
      cv-agent · {html.escape(date)} ·
      <a href="https://github.com/davidperron/cv" style="color:#6366f1">github.com/davidperron/cv</a>
    </p>
  </div>
</body>
</html>"""

    return subject, body


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Format CV search results for GHA summary + email.")
    ap.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    ap.add_argument("--queue-path", default=None, help="Explicit path to queue.jsonl (overrides --date lookup)")
    ap.add_argument("--exit-code", default="0", help="Exit code from run_search step")
    ap.add_argument("--github-step-summary", default=None,
                    help="Path to $GITHUB_STEP_SUMMARY file")
    ap.add_argument("--email-body", default=None,
                    help="Output path for HTML email body")
    ap.add_argument("--github-output", default=None,
                    help="Path to $GITHUB_OUTPUT file (for subject + count outputs)")
    args = ap.parse_args(argv)

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    queue_path_override = Path(args.queue_path) if args.queue_path else None
    jobs = _load_queue(date, queue_path=queue_path_override)

    # 1. GHA step summary
    if args.github_step_summary:
        summary_md = build_gha_summary(jobs, date, args.exit_code)
        path = Path(args.github_step_summary)
        with path.open("a", encoding="utf-8") as f:
            f.write(summary_md + "\n")

    # 2. HTML email body
    subject, html_body = build_html_email(jobs, date)
    if args.email_body:
        Path(args.email_body).write_text(html_body, encoding="utf-8")

    # 3. GitHub outputs (subject + count)
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as f:
            f.write(f"count={len(jobs)}\n")
            f.write(f"subject={subject}\n")

    # Always print a compact summary to stdout for the run log
    print(f"format_summary: date={date} jobs={len(jobs)}", flush=True)
    for j in jobs[:5]:
        print(f"  [{j.get('score',0):3d}] {j.get('company','?')} — {j.get('title','?')}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())

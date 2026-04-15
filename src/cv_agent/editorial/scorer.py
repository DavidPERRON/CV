"""Scoring: two-stage gate.

Stage 1: a fast, deterministic junior-title blocklist — runs locally, no LLM.
Stage 2: LLM call (scoring_prompt.md) for seniority + fit score.

The two-stage design mirrors ai_press_review: cheap pre-filter before the LLM.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..llm.client import LLMClient, LLMError
from ..models import JobPosting
from ..settings import CONFIG_DIR, PROMPTS_DIR, Settings

log = logging.getLogger(__name__)

SCORING_PROMPT = (PROMPTS_DIR / "scoring_prompt.md").read_text(encoding="utf-8") if (PROMPTS_DIR / "scoring_prompt.md").exists() else ""


@dataclass
class ScoringResult:
    seniority: str           # junior | mid | senior | executive | unknown
    pass_seniority_gate: bool
    fit_score: int           # 0-100
    sector: str
    rationale: str


def _load_blocklist() -> list[str]:
    cfg_path = CONFIG_DIR / "jobs.yaml"
    if not cfg_path.exists():
        return []
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [t.lower() for t in data.get("search", {}).get("junior_title_blocklist", [])]


_BLOCKLIST_CACHE: list[str] | None = None


def junior_title_blocked(title: str) -> tuple[bool, str]:
    """Hard filter: if any blocklist token appears as a whole word in the title, reject.

    Returns (blocked, matched_token).
    """
    global _BLOCKLIST_CACHE
    if _BLOCKLIST_CACHE is None:
        _BLOCKLIST_CACHE = _load_blocklist()
    t = title.lower()
    for tok in _BLOCKLIST_CACHE:
        if re.search(rf"\b{re.escape(tok)}\b", t):
            return True, tok
    return False, ""


def score_posting(
    job: JobPosting,
    master_cv: str,
    settings: Settings,
    llm: LLMClient | None = None,
) -> ScoringResult:
    """Score a single posting. Runs the local blocklist first, then the LLM gate."""
    blocked, token = junior_title_blocked(job.title)
    if blocked:
        return ScoringResult(
            seniority="junior",
            pass_seniority_gate=False,
            fit_score=0,
            sector=job.sector,
            rationale=f"Blocked by junior-title token '{token}' in title.",
        )

    if llm is None:
        llm = LLMClient(settings)

    user_prompt = _build_user_prompt(job, master_cv, settings)
    try:
        payload = llm.call_json(system=SCORING_PROMPT, user=user_prompt)
    except LLMError as e:
        log.warning("Scoring LLM call failed (%s). Returning unknown/0.", e)
        return ScoringResult(
            seniority="unknown",
            pass_seniority_gate=False,
            fit_score=0,
            sector=job.sector,
            rationale=f"LLM error: {e}",
        )

    seniority = str(payload.get("seniority", "unknown")).lower().strip()
    pass_gate = bool(payload.get("pass_seniority_gate", False))
    # Defense: if LLM returns junior/mid but forgot to flip the gate, enforce it.
    if seniority in {"junior", "mid"}:
        pass_gate = False
    fit = int(payload.get("fit_score", 0) or 0)
    if not pass_gate:
        fit = 0

    return ScoringResult(
        seniority=seniority,
        pass_seniority_gate=pass_gate,
        fit_score=max(0, min(100, fit)),
        sector=str(payload.get("sector", job.sector) or job.sector),
        rationale=str(payload.get("rationale", "") or ""),
    )


def _build_user_prompt(job: JobPosting, master_cv: str, settings: Settings) -> str:
    prefs = {
        "preferred_roles": settings.preferred_roles,
        "preferred_sectors": settings.preferred_sectors,
        "preferred_geographies": settings.preferred_geographies,
        "target_companies": settings.target_companies,
        "excluded_companies": settings.excluded_companies,
    }
    return (
        "### JOB POSTING\n"
        f"- Title: {job.title}\n"
        f"- Company: {job.company}\n"
        f"- Location: {job.location or 'unknown'}\n"
        f"- Source: {job.source}\n"
        f"- URL: {job.url}\n\n"
        f"Description:\n{job.description}\n\n"
        "### MASTER CV (source of truth — do not invent beyond)\n"
        f"{master_cv}\n\n"
        "### CANDIDATE PREFERENCES\n"
        f"{prefs}\n"
    )

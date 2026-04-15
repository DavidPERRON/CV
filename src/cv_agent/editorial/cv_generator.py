"""CV generator. The LLM system prompt is LITERALLY `prompts/writing_prompt.md`.

Principle: zero invention. The user prompt only injects the raw JD, the master
CV (source of truth), the output language, and optional extra instructions.
The LLM is asked for a strict JSON object with the 5 mandatory blocks.

A local `validate_no_invention()` pass catches the most obvious fabricated
entities (companies, schools, languages) by cross-checking against the master CV.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..llm.client import LLMClient
from ..models import ApplicationDraft, JobPosting
from ..settings import PROMPTS_DIR, Settings

log = logging.getLogger(__name__)

WRITING_PROMPT_PATH = PROMPTS_DIR / "writing_prompt.md"


class InventionError(ValueError):
    def __init__(self, message: str, suspects: list[str]) -> None:
        super().__init__(message)
        self.suspects = suspects


@dataclass
class GenerationOptions:
    language: str = "EN"
    extra_instructions: str = ""
    strict_no_invention: bool = True


REQUIRED_BLOCKS = ("positioning", "competencies", "gap_analysis", "cv_adapted", "cover_letter")


def load_writing_prompt() -> str:
    if not WRITING_PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"writing_prompt.md not found at {WRITING_PROMPT_PATH}. "
            "This file is the system prompt contract — it must exist."
        )
    return WRITING_PROMPT_PATH.read_text(encoding="utf-8")


def generate_application(
    job: JobPosting,
    master_cv: str,
    settings: Settings,
    options: GenerationOptions | None = None,
    llm: LLMClient | None = None,
) -> ApplicationDraft:
    options = options or GenerationOptions(language=settings.default_language)
    llm = llm or LLMClient(settings)

    system = load_writing_prompt()
    user = _build_user_prompt(job, master_cv, options)

    payload = llm.call_json(system=system, user=user)
    missing = [b for b in REQUIRED_BLOCKS if not payload.get(b)]
    if missing:
        raise ValueError(
            f"LLM response is missing required blocks: {missing}. Keys returned: {list(payload.keys())}"
        )

    draft = ApplicationDraft(
        job=job,
        language=options.language,
        positioning=str(payload["positioning"]),
        competencies=str(payload["competencies"]),
        gap_analysis=str(payload["gap_analysis"]),
        cv_adapted=str(payload["cv_adapted"]),
        cover_letter=str(payload["cover_letter"]),
    )

    if options.strict_no_invention:
        suspects = detect_invented_entities(draft.cv_adapted, master_cv)
        if suspects:
            raise InventionError(
                f"{len(suspects)} entities in cv_adapted are not present in master CV.",
                suspects=suspects,
            )

    return draft


def _build_user_prompt(job: JobPosting, master_cv: str, options: GenerationOptions) -> str:
    extra = options.extra_instructions.strip() or "(none)"
    return (
        "### JOB DESCRIPTION\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'unknown'}\n"
        f"URL: {job.url}\n\n"
        f"{job.description}\n\n"
        "### MASTER CV (source of truth — ne rien inventer au-delà)\n"
        f"{master_cv}\n\n"
        f"### OUTPUT LANGUAGE\n{options.language}\n\n"
        f"### ADDITIONAL INSTRUCTIONS\n{extra}\n\n"
        "### OUTPUT CONTRACT\n"
        "Respond with a single valid JSON object with these exact keys, each containing markdown:\n"
        "  - positioning      (Part 1 of the method)\n"
        "  - competencies     (Part 2)\n"
        "  - gap_analysis     (Part 3)\n"
        "  - cv_adapted       (Part 4 — the full tailored CV)\n"
        "  - cover_letter     (a concise, senior cover letter tailored to this role)\n"
        "No additional keys. No prose around the JSON.\n"
    )


# ---------- zero-invention guard ----------

# Very light heuristic: we extract likely proper-noun spans (capitalized sequences
# of 1-4 words) from the generated cv_adapted and check they also appear in the
# master CV. We ignore common section words and month/geography tokens.
_IGNORE = {
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Q1", "Q2", "Q3", "Q4", "H1", "H2", "EMEA", "APAC", "AMER", "US", "USA",
    "UK", "EU", "France", "Europe", "Paris", "London", "Canada",
    "Executive", "Summary", "Professional", "Experience", "Education",
    "Core", "Competencies", "Areas", "Relevance", "Languages",
    "Present", "Current", "CV", "AI", "IA", "LLM", "KPI", "P&L",
    "English", "French", "Spanish", "German", "Italian",
}
# Token = capitalized word, letters + optional & or -. No dots, no digits.
_PROPER_RE = re.compile(r"\b([A-Z][a-zA-Z&\-]{1,25}(?:\s+[A-Z][a-zA-Z&\-]{1,25}){0,3})\b")


def _extract_entities(text: str) -> set[str]:
    # Replace punctuation/newlines with a sentinel so spans don't cross sentences.
    text = re.sub(r"[.,;:!?\n\r()\[\]]+", " | ", text)
    hits = set()
    for m in _PROPER_RE.finditer(text):
        span = m.group(1).strip()
        parts = span.split()
        # Drop if every token is a generic word we ignore (Executive Summary, ...).
        if all(p in _IGNORE for p in parts):
            continue
        # One-word spans: only flag all-caps acronyms (HEC, MIT, ENS, SNCF).
        # Pure sentence-initial capitals ("Based", "Head") are too noisy.
        if len(parts) == 1:
            w = parts[0]
            if not (w.isupper() and len(w) >= 2):
                continue
        if len(span) < 3:
            continue
        hits.add(span)
    return hits


def detect_invented_entities(generated_cv: str, master_cv: str) -> list[str]:
    """Return a list of proper-noun spans present in generated_cv but absent
    from master_cv (case-insensitive substring match). Best-effort heuristic;
    not a proof — human review is still required."""
    master_low = master_cv.lower()
    suspects: list[str] = []
    for ent in sorted(_extract_entities(generated_cv)):
        if ent.lower() in master_low:
            continue
        # Also accept if every token appears separately in master CV
        parts = ent.lower().split()
        if all(p in master_low for p in parts):
            continue
        suspects.append(ent)
    return suspects

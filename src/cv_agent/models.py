"""Dataclasses for the pipeline. Kept minimal and serializable."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class JobPosting:
    """A single job posting at any stage of the pipeline."""

    title: str
    company: str
    url: str
    source: str
    location: str = ""
    description: str = ""          # full JD text (filled after extraction)
    posted_at: str = ""            # ISO date if known
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))
    fingerprint: str = ""
    seniority_signal: str = ""     # "senior" | "mid" | "junior" | "unknown"
    score: int = 0                 # 0-100 fit vs master CV
    slug: str = ""
    sector: str = ""               # banking / fintech / ai_labs / ...

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicationDraft:
    """The generated, human-pending application for a job posting."""

    job: JobPosting
    language: str
    positioning: str = ""
    competencies: str = ""
    gap_analysis: str = ""
    cv_adapted: str = ""
    cover_letter: str = ""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))
    status: str = "pending_review"
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["job"] = self.job.to_dict()
        return d

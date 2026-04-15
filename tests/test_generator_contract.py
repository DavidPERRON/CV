"""Contract tests for the CV generator. We mock the LLM; we only assert the
wiring, the no-invention guard, and the disk side-effects."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cv_agent.editorial.cv_generator import (
    GenerationOptions,
    InventionError,
    detect_invented_entities,
    generate_application,
)
from cv_agent.models import JobPosting
from cv_agent.settings import Settings


MASTER_CV = """# John Senior
senior@example.com
- Head of Corporate Sales at BNP Paribas 2018-present
- MBA HEC Paris 2015
- Languages: English, French
"""


def _job():
    return JobPosting(
        title="Head of Transaction Banking Sales",
        company="Example Bank",
        url="https://example.com/jobs/1",
        source="test",
        description="Senior client-facing role owning revenue and transformation. "
                    "Requires C-level exposure, European coverage, and AI literacy.",
        fingerprint="abc",
    )


def test_no_invention_passes_on_clean_draft():
    job = _job()
    settings = Settings()
    llm = MagicMock()
    llm.call_json.return_value = {
        "positioning": "short note",
        "competencies": "- Strategic Sales\n- Coverage",
        "gap_analysis": "gaps",
        "cv_adapted": "# John Senior\nHead of Corporate Sales at BNP Paribas.\nMBA HEC Paris.",
        "cover_letter": "dear team...",
    }
    draft = generate_application(job, MASTER_CV, settings, llm=llm)
    assert draft.cv_adapted.startswith("# John Senior")


def test_no_invention_catches_fake_company():
    job = _job()
    settings = Settings()
    llm = MagicMock()
    llm.call_json.return_value = {
        "positioning": "x",
        "competencies": "x",
        "gap_analysis": "x",
        "cv_adapted": "# John Senior\nHead of Sales at Goldman Sachs.\nStanford MBA.",
        "cover_letter": "x",
    }
    with pytest.raises(InventionError) as exc:
        generate_application(job, MASTER_CV, settings, llm=llm)
    joined = " ".join(exc.value.suspects)
    assert "Goldman" in joined or "Stanford" in joined


def test_detect_invented_entities_ignores_generic_tokens():
    master = "Head of Sales at BNP Paribas, Paris, France."
    generated = "Head of Sales at BNP Paribas. Based in Paris, Europe."
    suspects = detect_invented_entities(generated, master)
    assert suspects == []


def test_missing_block_raises():
    job = _job()
    settings = Settings()
    llm = MagicMock()
    llm.call_json.return_value = {
        "positioning": "x",
        "competencies": "x",
        "gap_analysis": "x",
        # cv_adapted missing
        "cover_letter": "x",
    }
    with pytest.raises(ValueError, match="missing required blocks"):
        generate_application(job, MASTER_CV, settings, llm=llm)

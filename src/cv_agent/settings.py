"""Settings loader. Three-layer: defaults -> YAML -> env vars.

Mirrors ai_press_review.settings shape (see
https://github.com/davidPERRON/AI-Press-REVIEW-5/blob/main/src/ai_press_review/settings.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
PROMPTS_DIR = ROOT / "prompts"


@dataclass
class Settings:
    # scoring
    top_threshold: int = 80
    mid_threshold: int = 60
    min_jd_words: int = 300
    # search
    max_jobs_per_run: int = 30
    max_docs_generated: int = 10
    default_language: str = "EN"
    preferred_roles: list[str] = field(default_factory=list)
    preferred_sectors: list[str] = field(default_factory=list)
    preferred_geographies: list[str] = field(default_factory=list)
    target_companies: list[str] = field(default_factory=list)
    excluded_companies: list[str] = field(default_factory=list)
    # extraction
    extraction_timeout: int = 20
    user_agent: str = "cv-agent/0.1"
    # llm
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-6"
    llm_fallback_model: str = "claude-sonnet-4-6"
    llm_max_output_tokens: int = 8000
    llm_temperature: float = 0.2
    # state
    applied_jobs_cap: int = 1000
    applied_jobs_ttl_days: int = 180
    pending_applications_cap: int = 50
    # submit
    submit_browser: str = "chromium"
    submit_headless: bool = False
    submit_user_data_dir_env: str = "PLAYWRIGHT_USER_DATA_DIR"
    submit_abort_after_minutes: int = 20
    # raw sources file (loaded lazily)
    sources_file: Path = field(default_factory=lambda: CONFIG_DIR / "sources.yaml")

    # secrets (env only)
    anthropic_api_key: str | None = None
    linkedin_email: str | None = None
    gmail_app_password: str | None = None
    imap_host: str = "imap.gmail.com"
    imap_folder: str = "INBOX"

    def load_sources(self) -> dict[str, Any]:
        if not self.sources_file.exists():
            return {}
        with self.sources_file.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    """Build the Settings object from defaults + config/jobs.yaml + env."""
    load_dotenv(ROOT / ".env", override=False)

    cfg = _load_yaml(CONFIG_DIR / "jobs.yaml")
    s = Settings()

    scoring = cfg.get("scoring", {})
    s.top_threshold = int(scoring.get("top_threshold", s.top_threshold))
    s.mid_threshold = int(scoring.get("mid_threshold", s.mid_threshold))
    s.min_jd_words = int(scoring.get("min_jd_words", s.min_jd_words))

    search = cfg.get("search", {})
    s.max_jobs_per_run = int(search.get("max_jobs_per_run", s.max_jobs_per_run))
    s.max_docs_generated = int(search.get("max_docs_generated", s.max_docs_generated))
    s.default_language = str(search.get("default_language", s.default_language))
    s.preferred_roles = list(search.get("preferred_roles", []))
    s.preferred_sectors = list(search.get("preferred_sectors", []))
    s.preferred_geographies = list(search.get("preferred_geographies", []))
    s.target_companies = list(search.get("target_companies", []))
    s.excluded_companies = list(search.get("excluded_companies", []))

    extr = cfg.get("extraction", {})
    s.extraction_timeout = int(extr.get("timeout_seconds", s.extraction_timeout))
    s.user_agent = str(extr.get("user_agent", s.user_agent))

    llm = cfg.get("llm", {})
    s.llm_provider = str(llm.get("provider", s.llm_provider))
    s.llm_model = str(llm.get("model", s.llm_model))
    s.llm_fallback_model = str(llm.get("fallback_model", s.llm_fallback_model))
    s.llm_max_output_tokens = int(llm.get("max_output_tokens", s.llm_max_output_tokens))
    s.llm_temperature = float(llm.get("temperature", s.llm_temperature))

    state = cfg.get("state", {})
    s.applied_jobs_cap = int(state.get("applied_jobs_cap", s.applied_jobs_cap))
    s.applied_jobs_ttl_days = int(state.get("applied_jobs_ttl_days", s.applied_jobs_ttl_days))
    s.pending_applications_cap = int(state.get("pending_applications_cap", s.pending_applications_cap))

    submit = cfg.get("submit", {})
    s.submit_browser = str(submit.get("browser", s.submit_browser))
    s.submit_headless = bool(submit.get("headless", s.submit_headless))
    s.submit_user_data_dir_env = str(submit.get("user_data_dir_env", s.submit_user_data_dir_env))
    s.submit_abort_after_minutes = int(submit.get("abort_after_minutes", s.submit_abort_after_minutes))

    # Secrets from env only
    s.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    s.linkedin_email = os.getenv("LINKEDIN_EMAIL")
    s.gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
    s.imap_host = os.getenv("IMAP_HOST", s.imap_host)
    s.imap_folder = os.getenv("IMAP_FOLDER", s.imap_folder)

    return s

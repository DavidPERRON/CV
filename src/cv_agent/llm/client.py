"""Thin LLM client wrapping Anthropic. Provider-agnostic shape kept from
ai_press_review: a single `call_json()` that returns a parsed dict."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed

from ..settings import Settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self.settings.llm_provider != "anthropic":
            raise LLMError(f"Unsupported llm_provider: {self.settings.llm_provider}")
        api_key = self.settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY missing — set it in .env or the environment."
            )
        try:
            import anthropic  # imported lazily so the package imports without the dep
        except ImportError as e:
            raise LLMError("anthropic package not installed. Run: pip install anthropic") from e
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(3), reraise=True)
    def call_text(self, system: str, user: str, model: str | None = None) -> str:
        client = self._ensure_client()
        m = model or self.settings.llm_model
        log.info("LLM call model=%s user_len=%d", m, len(user))
        resp = client.messages.create(
            model=m,
            max_tokens=self.settings.llm_max_output_tokens,
            temperature=self.settings.llm_temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")

    def call_json(self, system: str, user: str, model: str | None = None) -> dict[str, Any]:
        """Call the LLM and require a JSON object back. Fallback model on parse error."""
        user_with_hint = (
            user
            + "\n\nRespond with a single valid JSON object. Do not wrap it in prose or code fences."
        )
        try:
            raw = self.call_text(system, user_with_hint, model=model)
            return _parse_json_object(raw)
        except (LLMError, json.JSONDecodeError) as primary_err:
            log.warning("Primary LLM call failed (%s). Retrying on fallback model.", primary_err)
            raw = self.call_text(system, user_with_hint, model=self.settings.llm_fallback_model)
            return _parse_json_object(raw)


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Tolerant JSON parser: strips ```json fences and leading prose."""
    text = raw.strip()
    if text.startswith("```"):
        # strip first fence line and the closing fence
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object in response", text, 0)
    return json.loads(text[start:end + 1])

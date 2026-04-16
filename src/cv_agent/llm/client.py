"""Multi-provider LLM client with a fallback chain.

Primary: Anthropic (configurable model, default claude-opus-4-6).
Fallback 1: OpenAI (configurable model, default gpt-4o), used automatically when
the Anthropic call raises (credit exhaustion, rate limit, transient error, or
JSON parse failure).

The fallback chain is provider-aware: on a credit/quota error from Anthropic,
we do NOT retry the same provider — we move directly to the next link.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from tenacity import retry, stop_after_attempt, wait_fixed

from ..settings import Settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ProviderLink:
    provider: str  # "anthropic" | "openai"
    model: str


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._anthropic = None
        self._openai = None

    # ---------- provider chain ----------

    def _chain(self) -> list[_ProviderLink]:
        """Build the ordered provider/model chain from settings.

        Default shape: [primary_provider:primary_model, openai:openai_fallback_model].
        If the primary is already OpenAI we still allow a secondary OpenAI model.
        """
        primary = _ProviderLink(self.settings.llm_provider, self.settings.llm_model)
        fallback = _ProviderLink(
            self.settings.llm_fallback_provider,
            self.settings.llm_fallback_model,
        )
        chain = [primary]
        if (fallback.provider, fallback.model) != (primary.provider, primary.model):
            chain.append(fallback)
        return chain

    # ---------- clients ----------

    def _get_anthropic(self) -> Any:
        if self._anthropic is not None:
            return self._anthropic
        api_key = self.settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY missing — set it in .env or the environment.")
        try:
            import anthropic  # imported lazily so the package imports without the dep
        except ImportError as e:
            raise LLMError("anthropic package not installed. Run: pip install anthropic") from e
        self._anthropic = anthropic.Anthropic(api_key=api_key)
        return self._anthropic

    def _get_openai(self) -> Any:
        if self._openai is not None:
            return self._openai
        api_key = self.settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OPENAI_API_KEY missing — required for the OpenAI fallback.")
        try:
            import openai  # imported lazily
        except ImportError as e:
            raise LLMError("openai package not installed. Run: pip install openai") from e
        self._openai = openai.OpenAI(api_key=api_key)
        return self._openai

    # ---------- per-provider call_text ----------

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(3), reraise=True)
    def _call_anthropic(self, system: str, user: str, model: str) -> str:
        client = self._get_anthropic()
        log.info("LLM call provider=anthropic model=%s user_len=%d", model, len(user))
        resp = client.messages.create(
            model=model,
            max_tokens=self.settings.llm_max_output_tokens,
            temperature=self.settings.llm_temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(3), reraise=True)
    def _call_openai(self, system: str, user: str, model: str) -> str:
        client = self._get_openai()
        log.info("LLM call provider=openai model=%s user_len=%d", model, len(user))
        resp = client.chat.completions.create(
            model=model,
            max_tokens=self.settings.llm_max_output_tokens,
            temperature=self.settings.llm_temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _dispatch(self, link: _ProviderLink, system: str, user: str) -> str:
        if link.provider == "anthropic":
            return self._call_anthropic(system, user, link.model)
        if link.provider == "openai":
            return self._call_openai(system, user, link.model)
        raise LLMError(f"Unsupported llm_provider: {link.provider}")

    # ---------- public API ----------

    def call_text(self, system: str, user: str, model: str | None = None) -> str:
        """Call the chain until one provider returns. If `model` is given it
        overrides only the primary link's model (back-compat with older callers)."""
        chain = self._chain()
        if model:
            chain = [_ProviderLink(chain[0].provider, model)] + chain[1:]
        return self._run_chain(chain, lambda link: self._dispatch(link, system, user))

    def call_json(self, system: str, user: str, model: str | None = None) -> dict[str, Any]:
        """Call the LLM and require a JSON object back. The fallback chain also
        catches JSON parse failures (a malformed response counts as a failure)."""
        user_with_hint = (
            user
            + "\n\nRespond with a single valid JSON object. Do not wrap it in prose or code fences."
        )
        chain = self._chain()
        if model:
            chain = [_ProviderLink(chain[0].provider, model)] + chain[1:]

        def _attempt(link: _ProviderLink) -> dict[str, Any]:
            raw = self._dispatch(link, system, user_with_hint)
            return _parse_json_object(raw)

        return self._run_chain(chain, _attempt)

    # ---------- chain runner ----------

    def _run_chain(self, chain: list[_ProviderLink], call: Callable[[_ProviderLink], Any]) -> Any:
        last_err: Exception | None = None
        for i, link in enumerate(chain):
            try:
                return call(link)
            except (LLMError, json.JSONDecodeError) as err:
                last_err = err
                if i + 1 < len(chain):
                    log.warning(
                        "LLM link %s/%s failed (%s). Falling back to %s/%s.",
                        link.provider, link.model, err,
                        chain[i + 1].provider, chain[i + 1].model,
                    )
                    continue
                raise
            except Exception as err:  # provider SDK errors (rate limit, credit, 5xx)
                last_err = err
                if _is_retryable_provider_error(err) and i + 1 < len(chain):
                    log.warning(
                        "LLM link %s/%s raised %s. Falling back to %s/%s.",
                        link.provider, link.model, type(err).__name__,
                        chain[i + 1].provider, chain[i + 1].model,
                    )
                    continue
                raise
        # Unreachable in practice — the loop either returns or raises.
        raise LLMError(f"All LLM providers failed: {last_err}")


# ---------- helpers ----------

# Error class names that mean "this provider is unusable, move on".
# We match by name to avoid hard-importing provider SDKs at module load.
_PROVIDER_FALLBACK_ERROR_NAMES = {
    # Anthropic
    "AuthenticationError",       # bad key
    "PermissionDeniedError",     # plan/feature gate
    "RateLimitError",            # 429
    "APIStatusError",            # generic 4xx/5xx
    "OverloadedError",           # 529
    "InternalServerError",       # 5xx
    "APIConnectionError",        # network
    "APITimeoutError",           # network
    # OpenAI (same names mostly)
    "BadRequestError",           # often credit/quota on OpenAI
}


def _is_retryable_provider_error(err: BaseException) -> bool:
    name = type(err).__name__
    if name in _PROVIDER_FALLBACK_ERROR_NAMES:
        return True
    msg = str(err).lower()
    # Heuristic: credit / quota / billing exhaustion
    needles = (
        "credit balance",
        "insufficient_quota",
        "quota",
        "billing",
        "exceeded",
        "rate limit",
        "overloaded",
    )
    return any(n in msg for n in needles)


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Tolerant JSON parser: strips ```json fences and leading prose."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object in response", text, 0)
    return json.loads(text[start:end + 1])

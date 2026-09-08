"""AI client for generating text using Claude API.

Two functions. `generate_with_ai` is the raw call: it raises `AIClientError`
and is what tests patch. `ai_call` is what services use: it never raises, and
returns an `AIResult` that says whether the text came from the model or from
an offline fallback. Fallback-ness is a property of the value, not of a flag
somewhere else — the flag was how 150 scheduled runs saved templates as drafts.
"""

import os
import time
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5"
AI_DISABLED = "AI is disabled in settings.json (ai_enabled: false); drafts are written by hand"


class AIClientError(RuntimeError):
    """Raised when AI text generation fails."""


@dataclass(frozen=True)
class AIResult:
    """What every model call returns.

    `text` is the model output, or the fallback text when `was_fallback` is
    True. `error` is set when there is no text at all; a fallback result keeps
    the underlying error in `error` *and* carries text, so callers can say why
    they are showing a template. Truthy only when there is text.
    """

    text: str = ""
    error: str | None = None
    was_fallback: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.was_fallback

    @property
    def source(self) -> str:
        """The provenance to stamp on anything persisted from this result."""
        return "template" if self.was_fallback else "ai"

    def __bool__(self) -> bool:
        return bool(self.text)


def fallback_enabled() -> bool:
    value = os.environ.get("LINKEDIN_AI_FALLBACK_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def ai_call(prompt: str, *, max_tokens: int = 500, fallback: str | None = None) -> AIResult:
    """Call the model and return an `AIResult`; never raises.

    With `fallback` given and `LINKEDIN_AI_FALLBACK_ENABLED` not off, a failed
    call returns the fallback text with `was_fallback=True` and the error kept.
    Without a fallback, a failed call returns an empty result carrying the error.
    """
    from linkedin.settings import ai_enabled

    if not ai_enabled():
        # A choice, not a failure: no retries, no network, no template either —
        # the person who turned AI off writes their own text.
        return AIResult(error=AI_DISABLED)
    try:
        return AIResult(text=generate_with_ai(prompt, max_tokens=max_tokens))
    except AIClientError as exc:
        if fallback is not None and fallback_enabled():
            return AIResult(text=fallback, error=str(exc), was_fallback=True)
        return AIResult(error=str(exc))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    non_retryable_markers = [
        "authentication",
        "api key",
        "anthropic_api_key",
        "unauthorized",
        "forbidden",
        "permission",
        "401",
        "403",
    ]
    return not any(marker in message for marker in non_retryable_markers)


def generate_with_ai(
    prompt: str,
    max_tokens: int = 500,
    timeout_seconds: int | None = None,
    retries: int | None = None,
    backoff_seconds: float | None = None,
) -> str:
    """Generate text using Claude API with timeout and retry/backoff."""
    timeout = timeout_seconds if timeout_seconds is not None else _int_env("LINKEDIN_AI_TIMEOUT_SECONDS", 45)
    retry_count = retries if retries is not None else _int_env("LINKEDIN_AI_MAX_RETRIES", 2)
    retry_count = max(0, retry_count)
    backoff = backoff_seconds if backoff_seconds is not None else _float_env("LINKEDIN_AI_RETRY_BACKOFF_SECONDS", 1.5)
    backoff = max(0.0, backoff)

    try:
        import anthropic
    except Exception as exc:
        raise AIClientError(f"AI generation failed: {exc}. Make sure ANTHROPIC_API_KEY is set.") from exc

    try:
        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
    except Exception as exc:
        raise AIClientError(f"AI generation failed: {exc}. Make sure ANTHROPIC_API_KEY is set.") from exc

    model = os.environ.get("LINKEDIN_AI_MODEL", "").strip() or DEFAULT_MODEL
    attempts = retry_count + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            content = getattr(message, "content", None)
            if not content:
                raise RuntimeError("AI response was empty.")
            text = getattr(content[0], "text", "")
            if not text:
                raise RuntimeError("AI response did not include text.")
            return text
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1 or not _is_retryable(exc):
                break
            sleep_for = backoff * (2**attempt)
            if sleep_for > 0:
                time.sleep(sleep_for)

    raise AIClientError(
        f"AI generation failed after {attempts} attempt(s): {last_error}. Make sure ANTHROPIC_API_KEY is set."
    ) from last_error


def probe_api_key(api_key: str | None = None) -> tuple[bool, str]:
    """Ask the API whether a key works, with the cheapest possible call.

    "Configured" is not "valid": the key in cron.env was present and invalid
    for five months, and every check that only looked for its presence said ok.
    """
    try:
        import anthropic
    except Exception as exc:
        return False, f"anthropic SDK not importable: {exc}"
    try:
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        client.models.list(limit=1)
        return True, "key accepted by the API"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"

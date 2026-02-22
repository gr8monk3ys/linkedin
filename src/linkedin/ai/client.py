"""AI client for generating text using Claude API."""

import os
import time


class AIClientError(RuntimeError):
    """Raised when AI text generation fails."""


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

    attempts = retry_count + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
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
            sleep_for = backoff * (2 ** attempt)
            if sleep_for > 0:
                time.sleep(sleep_for)

    raise AIClientError(
        f"AI generation failed after {attempts} attempt(s): {last_error}. "
        "Make sure ANTHROPIC_API_KEY is set."
    ) from last_error

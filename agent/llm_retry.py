"""Shared LLM retry utility with exponential back-off and model-pool rotation.

Used by scorer, tailorer, and letter writer so rate-limit logic lives in
one place.
"""
from __future__ import annotations

import random
import re
import time
from typing import Callable, TypeVar

from loguru import logger
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

T = TypeVar("T")

# Errors that are worth retrying (transient server-side / rate-limit issues)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    """Return True if the exception is a transient error worth retrying."""
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRYABLE_STATUS_CODES
    return False


def retry_after_seconds(exc: Exception, attempt: int, base: float) -> float:
    """Compute how long to wait before the next retry.

    Respects the ``Retry-After`` header when present; otherwise uses
    exponential back-off with jitter, capped at 60 s.
    """
    if isinstance(exc, APIStatusError) and exc.response is not None:
        raw = exc.response.headers.get("retry-after") or exc.response.headers.get("Retry-After")
        if raw:
            try:
                return min(float(raw), 60.0)
            except ValueError:
                pass
    delay = min(base * (2 ** attempt) + random.uniform(0, 1), 60.0)
    return delay


def call_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int,
    base_seconds: float,
    label: str,
) -> T | None:
    """Call *fn*, retrying on retryable errors with exponential back-off.

    Parameters
    ----------
    fn:
        Zero-argument callable that either returns a result or raises.
    max_retries:
        Maximum number of attempts (first call + retries).
    base_seconds:
        Base delay for exponential back-off.
    label:
        Human-readable label for log messages (e.g. model name + task).

    Returns
    -------
    The return value of *fn* on success, or ``None`` if all retries are
    exhausted.  Non-retryable exceptions are re-raised immediately.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc):
                logger.warning(f"[llm_retry] Non-retryable error for {label}: {exc}")
                raise
            last_exc = exc
            if attempt >= max_retries - 1:
                break
            delay = retry_after_seconds(exc, attempt, base_seconds)
            logger.warning(
                f"[llm_retry] {label} — attempt {attempt + 1}/{max_retries} "
                f"failed (retryable). Retrying in {delay:.1f}s… ({exc})"
            )
            time.sleep(delay)

    logger.error(f"[llm_retry] {label} — all {max_retries} attempts exhausted. Last error: {last_exc}")
    return None


def call_with_model_pool(
    fn: Callable[[str], T],
    models: list[str],
    *,
    max_retries_per_model: int,
    base_seconds: float,
    label: str,
) -> T | None:
    """Try *fn(model)* across an ordered list of models, each with its own
    retry budget, stopping at the first success.

    Parameters
    ----------
    fn:
        Single-argument callable that accepts a model string.
    models:
        Ordered list of model IDs to try (primary first, fallbacks after).
    max_retries_per_model:
        Retry budget per model.
    base_seconds:
        Base delay for exponential back-off.
    label:
        Human-readable label for log messages.
    """
    for model in models:
        result = call_with_backoff(
            lambda m=model: fn(m),
            max_retries=max_retries_per_model,
            base_seconds=base_seconds,
            label=f"{label} [{model}]",
        )
        if result is not None:
            return result
        logger.warning(f"[llm_retry] Model {model} exhausted for {label}. Trying next…")
    logger.error(f"[llm_retry] All models exhausted for {label}.")
    return None


def call_with_model_and_key_pool(
    fn: Callable[[str, str], T],
    models: list[str],
    api_keys: list[str],
    *,
    max_retries_per_combination: int,
    base_seconds: float,
    label: str,
) -> T | None:
    """Try *fn(api_key, model)* across an ordered list of models and keys.

    For each model, tries all keys. If a key hits rate limits and exhausts
    its retries, it moves to the next key. If all keys fail, it moves to
    the next model.
    """
    if not api_keys:
        logger.error(f"[llm_retry] No API keys provided for {label}")
        return None

    for model in models:
        for key in api_keys:
            # Mask key for logging
            masked_key = f"...{key[-4:]}" if len(key) > 4 else "***"
            
            result = call_with_backoff(
                lambda k=key, m=model: fn(k, m),
                max_retries=max_retries_per_combination,
                base_seconds=base_seconds,
                label=f"{label} [model={model}, key={masked_key}]",
            )
            if result is not None:
                return result
            logger.warning(f"[llm_retry] Key {masked_key} exhausted for model {model} ({label}). Trying next key…")
        logger.warning(f"[llm_retry] Model {model} exhausted (all keys failed) for {label}. Trying next model…")
    
    logger.error(f"[llm_retry] All models and keys exhausted for {label}.")
    return None


def strip_think_block(content: str) -> str:
    """Remove <think>…</think> reasoning blocks some models emit."""
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

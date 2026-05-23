"""
llm_client.py

Thin wrapper around the local LLM inference server.

Improvements over the original:
  - Per-call parameter control (max_tokens, temperature)
  - Retry logic with exponential backoff on transient errors
  - Structured logging (errors are visible, not silently swallowed)
  - Config-driven URL/timeout (no magic constants in business logic)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.exceptions import RequestException

from config import CONFIG

logger = logging.getLogger(__name__)


def send_prompt_to_llm(
    prompt: str,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    retries: Optional[int] = None,
) -> str:
    """
    Send a prompt to the local LLM server and return the text response.

    Args:
        prompt:      The full prompt string.
        max_tokens:  Max generation tokens. Defaults to config parse value.
        temperature: Sampling temperature. Defaults to config parse value.
        retries:     Retry attempts on transient failure. Defaults to config.

    Returns:
        Response string, or empty string on unrecoverable failure.
        Never raises — callers rely on graceful degradation.
    """
    cfg = CONFIG.llm
    _max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens_parse
    _temperature = temperature if temperature is not None else cfg.temperature_parse
    _retries = retries if retries is not None else cfg.retries

    payload = {
        "prompt": prompt,
        "max_tokens": _max_tokens,
        "temperature": _temperature,
    }

    for attempt in range(_retries + 1):
        try:
            response = requests.post(
                cfg.url,
                json=payload,
                timeout=cfg.timeout,
            )
            response.raise_for_status()
            content: str = response.json().get("content", "")
            logger.debug(
                "LLM OK (attempt %d/%d): '%s...'",
                attempt + 1, _retries + 1, content[:80],
            )
            return content

        except RequestException as exc:
            logger.warning(
                "LLM request failed (attempt %d/%d): %s",
                attempt + 1, _retries + 1, exc,
            )
            if attempt < _retries:
                backoff = 0.4 * (2 ** attempt)   # 0.4s, 0.8s, ...
                logger.debug("Retrying in %.1fs...", backoff)
                time.sleep(backoff)

        except (ValueError, KeyError) as exc:
            # Bad JSON or missing 'content' key — no point retrying
            logger.error("LLM response malformed: %s", exc)
            break

        except Exception as exc:
            logger.error("Unexpected LLM error: %s", exc)
            break

    return ""

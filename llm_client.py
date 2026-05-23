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
            response = requests.post(cfg.url, json=payload, timeout=cfg.timeout)
            response.raise_for_status()
            content: str = response.json().get("content", "")
            logger.debug("LLM OK (attempt %d): '%s...'", attempt + 1, content[:80])
            return content

        except RequestException as exc:
            logger.warning("LLM request failed (attempt %d/%d): %s", attempt + 1, _retries + 1, exc)
            if attempt < _retries:
                # Exponential backoff: 0.4s then 0.8s
                backoff = 0.4 * (2 ** attempt)
                logger.debug("Retrying in %.1fs...", backoff)
                time.sleep(backoff)

        except (ValueError, KeyError) as exc:
            # Malformed JSON or missing 'content' key — no point retrying
            logger.error("LLM response malformed: %s", exc)
            break

        except Exception as exc:
            logger.error("Unexpected LLM error: %s", exc)
            break

    return ""

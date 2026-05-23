"""
memory.py

Purchase history and user brand preference management.

Improvements over original:
  - In-memory cache: JSON file is loaded once per session, not on every call.
  - Fuzzy brand matching: "whole milk" matches history entry for "milk".
  - Typed API and explicit error handling.
  - invalidate_cache() for testing and manual resets.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

FILE = "purchase_history.json"
_cache: Optional[List[dict]] = None   # module-level cache, lives for process lifetime


# ──────────────────────────────────────────────────────────────
#  History I/O
# ──────────────────────────────────────────────────────────────

def load_history() -> List[dict]:
    """
    Load purchase history from disk.
    Cached after first read — subsequent calls return the cached list.
    """
    global _cache
    if _cache is not None:
        return _cache

    if not os.path.exists(FILE):
        _cache = []
        return _cache

    try:
        with open(FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
            logger.debug("Loaded %d history entries from %s", len(_cache), FILE)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load purchase history: %s", exc)
        _cache = []

    return _cache


def save_history(data: List[dict]) -> None:
    """Persist history to disk and update cache."""
    global _cache
    try:
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        _cache = data
        logger.debug("Saved %d history entries to %s", len(data), FILE)
    except OSError as exc:
        logger.error("Failed to save purchase history: %s", exc)


def clear_history() -> None:
    """Delete the history file and clear cache."""
    global _cache
    _cache = None
    if os.path.exists(FILE):
        try:
            os.remove(FILE)
        except OSError as exc:
            logger.error("Failed to clear purchase history: %s", exc)


def invalidate_cache() -> None:
    """Force a fresh disk read on the next load_history() call."""
    global _cache
    _cache = None


# ──────────────────────────────────────────────────────────────
#  Brand Preference Lookup
# ──────────────────────────────────────────────────────────────

def get_preferred_brand(item_name: str) -> Optional[str]:
    """
    Return the user's preferred brand for this item, or None.

    Matching strategy (in order):
      1. Exact match: "milk" == "milk"
      2. Substring match: "whole milk" contains "milk" → matches "milk" entry
         Also handles the reverse: "milk" is contained in "toned milk"

    This fuzzy approach avoids missed preferences when the user asks for
    "1 litre whole milk" but history only has "milk" stored.
    """
    item_lower = item_name.lower().strip()
    history = load_history()

    # Pass 1: exact match (highest confidence)
    for entry in history:
        stored = entry.get("item", "").lower()
        if stored == item_lower:
            brand = entry.get("preferred_brand")
            logger.debug("Brand exact match: '%s' -> '%s'", item_lower, brand)
            return brand

    # Pass 2: substring match (fuzzy)
    for entry in history:
        stored = entry.get("item", "").lower()
        if stored and (stored in item_lower or item_lower in stored):
            brand = entry.get("preferred_brand")
            logger.debug(
                "Brand fuzzy match: '%s' ~ '%s' -> '%s'",
                item_lower, stored, brand,
            )
            return brand

    return None

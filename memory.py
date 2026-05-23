import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

FILE = "purchase_history.json"
_cache: Optional[List[dict]] = None

# Brand preferences are OFF by default and only turn on when the user
# explicitly uploads a history file via the UI. This prevents stale data
# on disk from silently biasing searches in a fresh session.
_preferences_enabled: bool = False


def enable_preferences() -> None:
    global _preferences_enabled
    _preferences_enabled = True
    logger.info("Brand preferences ENABLED (history uploaded).")


def disable_preferences() -> None:
    global _preferences_enabled
    _preferences_enabled = False
    logger.info("Brand preferences DISABLED.")


def is_preferences_enabled() -> bool:
    return _preferences_enabled


def load_history() -> List[dict]:
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
    global _cache
    try:
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        _cache = data
    except OSError as exc:
        logger.error("Failed to save purchase history: %s", exc)


def clear_history() -> None:
    global _cache, _preferences_enabled
    _cache = None
    _preferences_enabled = False
    if os.path.exists(FILE):
        try:
            os.remove(FILE)
        except OSError as exc:
            logger.error("Failed to clear purchase history: %s", exc)


def invalidate_cache() -> None:
    global _cache
    _cache = None


def get_preferred_brand(item_name: str) -> Optional[str]:
    # Return None immediately if the user hasn't uploaded history this session
    if not _preferences_enabled:
        return None

    item_lower = item_name.lower().strip()
    item_words = set(item_lower.split())
    history = load_history()

    # Exact match first
    for entry in history:
        stored = entry.get("item", "").lower()
        if stored == item_lower:
            brand = entry.get("preferred_brand")
            logger.debug("Brand exact match: '%s' -> '%s'", item_lower, brand)
            return brand

    # Fuzzy word-set match — only allow matches where the two items are
    # close in specificity (at most 1 word apart) to avoid "milk bread"
    # cross-matching with the "milk" entry and creating broken search queries
    for entry in history:
        stored = entry.get("item", "").lower()
        if not stored:
            continue
        stored_words = set(stored.split())
        if abs(len(item_words) - len(stored_words)) > 1:
            continue
        if stored_words <= item_words or item_words <= stored_words:
            brand = entry.get("preferred_brand")
            logger.debug("Brand fuzzy match: '%s' ~ '%s' -> '%s'", item_lower, stored, brand)
            return brand

    return None

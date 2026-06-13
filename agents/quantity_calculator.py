import logging
import math
import re

logger = logging.getLogger(__name__)

MAX_UNITS = 10

_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(ml|l\b|ltr|litres?|liters?|g\b|gm|gms?|gram|grams?|kg|kgs?"
    r"|pcs?|pc|pieces?|pack|nos|unit|units)",
    re.IGNORECASE,
)

_UNIT_MAP = {
    "ml":      ("ml",   1.0),
    "l":       ("ml",   1000.0),
    "ltr":     ("ml",   1000.0),
    "litre":   ("ml",   1000.0),
    "litres":  ("ml",   1000.0),
    "liter":   ("ml",   1000.0),
    "liters":  ("ml",   1000.0),
    "g":       ("g",    1.0),
    "gm":      ("g",    1.0),
    "gms":     ("g",    1.0),
    "gram":    ("g",    1.0),
    "grams":   ("g",    1.0),
    "kg":      ("g",    1000.0),
    "kgs":     ("g",    1000.0),
    "pcs":     ("ct",   1.0),
    "pc":      ("ct",   1.0),
    "piece":   ("ct",   1.0),
    "pieces":  ("ct",   1.0),
    "pack":    ("ct",   1.0),
    "packet":  ("ct",   1.0),
    "packets": ("ct",   1.0),
    "nos":     ("ct",   1.0),
    "unit":    ("ct",   1.0),
    "units":   ("ct",   1.0),
}

_COUNT_UNITS = {
    "pcs", "pc", "piece", "pieces",
    "pack", "packet", "packets",
    "unit", "units", "nos",
}


def _parse_size(product_name: str, preferred_base_unit: str = None):
    """
    Find size measurements in a product name and return the most relevant one.

    Collects ALL regex matches first, then selects:
      1. The first match whose base unit equals preferred_base_unit (if given)
      2. Otherwise the first match overall

    This fixes the "1 pack (450 ml)" problem — the old code used re.search()
    which returned "1 pack" (count unit) before ever reaching "450 ml" (volume).
    When the user requested litres, preferred_base_unit="ml" so we now skip
    "1 pack" and correctly pick "450 ml".
    """
    all_matches = []
    for m in _SIZE_RE.finditer(product_name):
        value   = float(m.group(1))
        key     = m.group(2).lower()
        mapping = _UNIT_MAP.get(key)
        if mapping:
            base_unit, multiplier = mapping
            all_matches.append((value * multiplier, base_unit))

    if not all_matches:
        return None, None

    if preferred_base_unit:
        for size_base, size_unit in all_matches:
            if size_unit == preferred_base_unit:
                return size_base, size_unit

    return all_matches[0]


def calculate_units_needed(requested_amount, requested_unit: str, product_name: str) -> int:
    """
    How many packs to add to reach the user's requested quantity.

    Examples after fix:
      2 litre + "1 pack (450 ml)"  -> prefers 450ml -> ceil(2000/450) = 5
      2 litre + "500 ml pack"      -> 500ml          -> ceil(2000/500) = 4
      1 kg    + "500g pack"        -> 500g           -> ceil(1000/500) = 2
      6 pcs   + "6-pack"           -> 6ct            -> ceil(6/6)      = 1
    """
    try:
        amount = float(requested_amount) if requested_amount else 1.0
    except (TypeError, ValueError):
        amount = 1.0

    unit_lower = (requested_unit or "unit").lower().strip()

    if unit_lower in _COUNT_UNITS:
        size_base, size_unit = _parse_size(product_name, preferred_base_unit="ct")
        if size_base and size_base > 1 and size_unit == "ct":
            result = max(1, min(math.ceil(amount / size_base), MAX_UNITS))
            logger.info("Qty: %d items / %d per pack = %d x '%s'",
                        int(amount), int(size_base), result, product_name[:50])
            return result
        return max(1, min(int(amount), MAX_UNITS))

    req_mapping = _UNIT_MAP.get(unit_lower)
    if req_mapping is None:
        logger.debug("Unknown unit '%s'; using raw amount as count", unit_lower)
        return max(1, min(int(amount), MAX_UNITS))

    req_base_unit, req_multiplier = req_mapping
    requested_in_base = amount * req_multiplier

    # Pass preferred unit so parser skips count-based matches (e.g. "1 pack")
    # and finds the volume/weight match (e.g. "450 ml") instead
    size_base, size_unit = _parse_size(product_name, preferred_base_unit=req_base_unit)

    if size_base is None:
        logger.debug("No size in '%s'; defaulting to 1", product_name[:50])
        return 1

    if size_base > 0 and size_unit == req_base_unit:
        result = max(1, min(math.ceil(requested_in_base / size_base), MAX_UNITS))
        logger.info("Qty: %.0f%s / %.0f%s per pack = %d x '%s'",
                    requested_in_base, req_base_unit,
                    size_base, size_unit, result, product_name[:50])
        return result

    logger.debug("Unit mismatch: want %s, product has %s for '%s'; defaulting to 1",
                 req_base_unit, size_unit, product_name[:50])
    return 1

import logging
import math
import re

logger = logging.getLogger(__name__)

MAX_UNITS = 10

# Matches a size+unit anywhere in a product name string.
# Includes both "litre/litres" (British) and "liter/liters" (American)
# because different scrapers/platforms use different spellings.
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
    "liter":   ("ml",   1000.0),   # American spelling — was missing
    "liters":  ("ml",   1000.0),   # American spelling — was missing
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


def _parse_size(product_name: str):
    matches = list(_SIZE_RE.finditer(product_name))

    if not matches:
        return None, None

    volume_matches = []
    count_matches = []

    for m in matches:
        unit_key = m.group(2).lower()

        if unit_key in {
            "ml", "l", "ltr", "litre", "litres",
            "liter", "liters",
            "g", "gm", "gms", "gram", "grams",
            "kg", "kgs"
        }:
            volume_matches.append(m)
        else:
            count_matches.append(m)

    chosen = volume_matches[-1] if volume_matches else matches[-1]

    value = float(chosen.group(1))
    unit_key = chosen.group(2).lower()

    base_unit, multiplier = _UNIT_MAP[unit_key]

    return value * multiplier, base_unit


def calculate_units_needed(requested_amount, requested_unit: str, product_name: str) -> int:
    """
    How many packs of this product are needed to fulfil the user's request?

    Examples:
      2 litre  + 500ml pack  -> ceil(2000/500) = 4
      2 litre  + 1L pack     -> ceil(2000/1000) = 2
      2 liter  + 500ml pack  -> same (American spelling now handled)
      1 kg     + 500g pack   -> ceil(1000/500) = 2
      6 pcs    + 6-pack      -> ceil(6/6) = 1
      3 unit   + no size     -> 3  (count unit, direct)
      2 litre  + no size     -> 1  (can't divide, safe default)
    """
    try:
        amount = float(requested_amount) if requested_amount else 1.0
    except (TypeError, ValueError):
        amount = 1.0

    unit_lower = (requested_unit or "unit").lower().strip()

    if unit_lower in _COUNT_UNITS:
        # User wants N individual items — divide by pack size if it's a multipack
        size_base, size_unit = _parse_size(product_name)
        if size_base and size_base > 1 and size_unit == "ct":
            result = max(1, min(math.ceil(amount / size_base), MAX_UNITS))
            logger.info(
                "Qty calc: %d items / %d per pack = %d pack(s) of '%s'",
                int(amount), int(size_base), result, product_name[:50],
            )
            return result
        return max(1, min(int(amount), MAX_UNITS))

    req_mapping = _UNIT_MAP.get(unit_lower)
    if req_mapping is None:
        logger.debug("Unknown unit '%s'; using raw amount as count", unit_lower)
        return max(1, min(int(amount), MAX_UNITS))

    req_base_unit, req_multiplier = req_mapping
    requested_in_base = amount * req_multiplier

    size_base, size_unit = _parse_size(product_name)

    if size_base is None:
        logger.debug("No size found in '%s'; defaulting to 1 pack", product_name[:50])
        return 1

    if size_base > 0 and size_unit == req_base_unit:
        result = max(1, min(math.ceil(requested_in_base / size_base), MAX_UNITS))
        logger.info(
            "Qty calc: %.0f%s / %.0f%s per pack = %d pack(s) of '%s'",
            requested_in_base, req_base_unit,
            size_base, size_unit,
            result, product_name[:50],
        )
        return result

    # Units don't match (e.g. user requested ml, product measured in g)
    logger.debug(
        "Unit mismatch: requested %s but product in %s for '%s'; defaulting to 1",
        req_base_unit, size_unit, product_name[:50],
    )
    return 1

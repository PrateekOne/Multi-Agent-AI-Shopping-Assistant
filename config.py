"""
config.py

Central configuration for the AI Shopping Agent.

Scoring weights, blocklists, quality brand tiers, LLM parameters,
and browser settings are all defined here so they can be tuned in
one place without touching business logic.

To override browser session path at runtime:
    export BROWSER_SESSION_PATH=/your/path
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List


# ──────────────────────────────────────────────────────────────
#  Scoring Weights
# ──────────────────────────────────────────────────────────────

@dataclass
class ScoringWeights:
    """
    Configurable weights for the product ranking engine.
    All weights are applied as a linear combination; they do NOT need
    to sum to 1.0 (each dimension is independently normalized to [0,1]
    before multiplication), but keeping them close to 1.0 total makes
    the 'total' score intuitively readable.

    Tuning guide:
      - Raise `relevance` if the agent picks wrong product categories.
      - Raise `value` if the agent consistently picks overpriced options.
      - Raise `brand` if brand fidelity matters more than cost.
    """
    relevance: float = 0.40   # Semantic match between user query and product
    value: float = 0.30       # Price-per-unit efficiency (normalized)
    brand: float = 0.15       # Known brand quality tier + preference match
    availability: float = 0.15  # Reserved for future stock/rating signals


# ──────────────────────────────────────────────────────────────
#  Variant Blocklists
# ──────────────────────────────────────────────────────────────

# Maps a category keyword (if found in query) → product name substrings to block.
# Add new categories freely. Matching is case-insensitive substring.
VARIANT_BLOCKLIST: Dict[str, List[str]] = {
    "milk": [
        "curd", "greek", "yogurt", "yoghurt", "butter", "ghee",
        "cream", "cheese", "paneer", "lassi", "chaach", "chaas",
        "protein", "shake", "flavoured", "flavored", "condensed",
        "evaporated", "powder",
    ],
    "water": ["sparkling", "flavored", "flavoured", "vitamin", "electrolyte"],
    "bread": ["crumbs", "rusks", "croutons", "breadstick"],
    "juice": ["jam", "jelly", "squash", "syrup", "cordial"],
    "rice": ["flour", "beaten", "puffed", "poha", "flattened", "flakes"],
    "sugar": ["artificial", "stevia", "sweetener", "jaggery powder"],
    "oil": ["essential oil", "hair oil", "baby oil"],
}


# ──────────────────────────────────────────────────────────────
#  Quality Brand Tiers
# ──────────────────────────────────────────────────────────────

# Tier 1: Flagship Indian & international FMCG brands — consistent quality.
QUALITY_BRANDS_TIER1: List[str] = [
    "amul", "britannia", "nestlé", "nestle", "mother dairy",
    "aashirvaad", "fortune", "saffola", "dabur", "tata",
    "farm fresh", "country delight", "epigamia",
    "mahananda", "heritage", "vijaya",
]

# Tier 2: Well-known but slightly more regional or snack-focused brands.
QUALITY_BRANDS_TIER2: List[str] = [
    "patanjali", "haldiram", "mtr", "maggi", "parle", "lays",
    "bingo", "pepsico", "kitkat", "cadbury", "coca cola",
    "pepsi", "mondelez", "himalaya", "organic india",
    "maaza", "real", "tropicana", "paperboat",
    "weikfield", "ching's", "priya", "catch",
]


# ──────────────────────────────────────────────────────────────
#  LLM Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    url: str = "http://localhost:8080"

    # Timeouts and retries
    timeout: int = 25
    retries: int = 2

    # Token budgets — keep selection tasks cheap
    max_tokens_select: int = 120   # For product disambiguation (JSON index only)
    max_tokens_parse: int = 500    # For item extraction from user input

    # Temperature — deterministic for selection, slight variance for parsing
    temperature_select: float = 0.0
    temperature_parse: float = 0.3


# ──────────────────────────────────────────────────────────────
#  App-wide Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    scoring: ScoringWeights = field(default_factory=ScoringWeights)

    # Browser session: override via env var for portability across machines
    browser_session_path: str = field(
        default_factory=lambda: os.environ.get(
            "BROWSER_SESSION_PATH",
            os.path.join(
                os.path.expanduser("~"),
                ".shopping_agent",
                "browser_session",
            ),
        )
    )

    # Ranking pipeline controls
    max_candidates: int = 10          # Max raw products passed to ranker
    top_k_for_llm: int = 5            # Top K candidates sent to LLM fallback

    # If top-2 score gap ≥ this, skip LLM call and return immediately
    confidence_gap_threshold: float = 0.12

    # Jaccard similarity above which two products are considered duplicates
    dedup_similarity_threshold: float = 0.80


# Singleton instance — import this everywhere
CONFIG = AppConfig()

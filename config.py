from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ScoringWeights:
    # Raise relevance if the agent keeps picking the wrong product category.
    # Raise value if it keeps picking overpriced options.
    # Raise brand if brand fidelity matters more than cost for your use case.
    relevance: float = 0.40
    value: float = 0.30
    brand: float = 0.15
    availability: float = 0.15   # reserved for future rating/stock signals


# Maps a category keyword in the query to product name substrings that should
# be blocked — prevents "milk" search from returning yogurt or protein shakes
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

# Tier 1: flagship FMCG brands with consistent nationwide quality
QUALITY_BRANDS_TIER1: List[str] = [
    "amul", "britannia", "nestlé", "nestle", "mother dairy",
    "aashirvaad", "fortune", "saffola", "dabur", "tata",
    "farm fresh", "country delight", "epigamia",
    "mahananda", "heritage", "vijaya",
]

# Tier 2: well-known regional or snack-focused brands
QUALITY_BRANDS_TIER2: List[str] = [
    "patanjali", "haldiram", "mtr", "maggi", "parle", "lays",
    "bingo", "pepsico", "kitkat", "cadbury", "coca cola",
    "pepsi", "mondelez", "himalaya", "organic india",
    "maaza", "real", "tropicana", "paperboat",
    "weikfield", "chings", "priya", "catch",
    "kurkure", "uncle chipps", "sunfeast", "oreo", "bourbon",
    "good day", "marie", "hide and seek", "monaco",
]


@dataclass
class LLMConfig:
    url: str = "http://localhost:8080"
    timeout: int = 25
    retries: int = 2
    max_tokens_select: int = 120   # keep low — selection only needs a JSON index
    max_tokens_parse: int = 500
    temperature_select: float = 0.0   # deterministic for product selection
    temperature_parse: float = 0.3


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    scoring: ScoringWeights = field(default_factory=ScoringWeights)

    # Browser session path — override with BROWSER_SESSION_PATH env var
    # so the project works on any machine without editing this file
    browser_session_path: str = field(
        default_factory=lambda: os.environ.get(
            "BROWSER_SESSION_PATH",
            os.path.join(os.path.expanduser("~"), ".shopping_agent", "browser_session"),
        )
    )

    max_candidates: int = 10         # how many raw scraper results enter the ranker
    top_k_for_llm: int = 5           # how many top candidates get sent to the LLM

    # If the gap between the top two scores exceeds this, skip the LLM call
    confidence_gap_threshold: float = 0.12

    # Products with Jaccard token similarity above this are treated as duplicates
    dedup_similarity_threshold: float = 0.80

    # Products scoring below this relevance value are excluded from ranking.
    # This stops a Britannia biscuit from winning a "lays chips" search because
    # it happened to score well on brand/value while matching zero query words.
    min_relevance_threshold: float = 0.05


CONFIG = AppConfig()

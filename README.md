# AI Shopping Assistant

An agentic desktop app that automates grocery shopping across **Blinkit** and **Zepto** simultaneously, compares prices in real time, and adds the best-value items to your cart — all from a single natural language input.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt5](https://img.shields.io/badge/UI-PyQt5-green)
![Playwright](https://img.shields.io/badge/Automation-Playwright-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What it does

1. You type something like `"2 litres of milk, 6 eggs and lays chips"`
2. The agent parses your list, identifies items and quantities (works even when the LLM is offline)
3. Colloquial names are resolved before searching — `"red pringles"` becomes `"Pringles Original"`, `"blue lays"` becomes `"Lays Magic Masala"`
4. Both Blinkit and Zepto are opened in a real browser, searched, and ranked by relevance, value, and brand quality
5. Quantities are calculated by unit conversion — `"2 litres"` with a `500ml` pack adds 4 units automatically
6. A side-by-side price table shows which platform is cheaper and by how much

---

## Features

- **Natural language input** — type your list however you want, with or without quantities
- **Colloquial name resolution** — colour-coded or informal product names are resolved to proper searchable names before hitting the search bar (local lookup table for zero LLM cost; falls back to LLM for unknown cases)
- **Smart quantity calculation** — converts user-requested units to pack counts by reading the actual pack size from each product. `"2 litres of milk"` with a `450ml` pack correctly adds 5 units, not 2
- **Intelligent product selection** — ranks candidates by relevance to your query, price-per-unit value, and brand quality tier; never just picks the first result
- **Relevance gate** — products with zero relevance to the query are excluded so unrelated items can never win on price or brand alone
- **LLM-optional** — a regex-based fallback parser handles quantity extraction even when the local LLM server is offline, so the app keeps working
- **Brand preference memory** — upload a purchase history JSON to bias selection toward preferred brands; preferences are **session-scoped** and only activate after an explicit upload
- **Cart clearing** — previous run's cart is emptied before each new run on both platforms
- **Side-by-side price comparison** — Blinkit vs Zepto totals with savings highlighted in the UI
- **Re-run without restarting** — click Clear and run a completely new search in the same session
- **Persistent browser session** — stays logged in across runs

---

## Project structure

```
AgenticProject/
├── main.py                        # Entry point — sets up logging before imports
├── ui.py                          # PyQt5 desktop UI (dark theme, colour-coded log)
├── config.py                      # Scoring weights, brand tiers, blocklists, LLM config
├── llm_client.py                  # Local LLM HTTP wrapper with retry + backoff
├── memory.py                      # Purchase history with session-gated brand preferences
├── purchase_history.json          # Sample history file (optional)
│
├── agents/
│   ├── planner_agent.py           # Parses natural language → structured item list (LLM + regex fallback)
│   ├── query_normalizer.py        # Resolves colloquial names before search (local table + LLM)
│   ├── quantity_calculator.py     # Converts requested units to pack count using product size
│   ├── product_ranker.py          # Multi-factor scoring engine — relevance, value, brand
│   ├── selector_agent.py          # Orchestrates ranker + optional LLM disambiguation
│   ├── comparison_agent.py        # Compares Blinkit and Zepto cart totals
│   └── recipe_agent.py            # (Optional) Extracts ingredients from a recipe name
│
├── automation/
│   ├── blinkit_bot.py             # Playwright bot for Blinkit
│   └── zepto_bot.py               # Playwright bot for Zepto
│
└── utils/
    ├── playwright_manager.py      # Singleton browser context — closes pages between runs
    ├── logging_config.py          # Structured logging (console + file)
    ├── progress.py                # Progress signal helper for UI thread
    └── storage.py                 # File loader utility
```

---

## Requirements

- Python 3.10+
- A local LLM server on `http://localhost:8080` — e.g. [LM Studio](https://lmstudio.ai), [Ollama](https://ollama.com), or [llama.cpp](https://github.com/ggerganov/llama.cpp). The app works without it but product parsing and disambiguation quality improves with it
- Chrome or Chromium installed
- Active Blinkit and Zepto accounts (the browser session persists your login)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/AgenticProject.git
cd AgenticProject
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install PyQt5 playwright requests
playwright install chromium
```

### 4. Start your local LLM server (optional but recommended)

Point any OpenAI-compatible server at port `8080`. Example with LM Studio:
- Load a model (Mistral 7B Instruct or similar works well)
- Start the local server on port `8080`

To use a different port, edit `config.py`:

```python
@dataclass
class LLMConfig:
    url: str = "http://localhost:8080"
```

If the LLM is unreachable the app continues using the regex fallback parser — quantities like `"2 litres of milk"` are still parsed correctly.

### 5. Run the app

```bash
python main.py
```

On first run the browser opens and asks you to log in to Blinkit and Zepto. The session is saved so you won't need to log in again.

---

## Usage

### Basic search

```
milk, eggs, brown bread and lays chips
```

### With quantities

```
2 litres of milk, 6 eggs, 1 loaf of bread
```

The agent converts units automatically. `"2 litres of milk"` with a `500ml` pack on the shelf adds 4 packs. With a `450ml` pack it adds 5. With a `1L` pack it adds 2.

### Colloquial and colour-coded names

```
red pringles, blue lays, coke zero, amul gold
```

These are resolved to proper searchable names before the browser search runs:

| You type | Agent searches |
|---|---|
| red pringles | Pringles Original |
| green pringles | Pringles Sour Cream Onion |
| blue lays | Lays Magic Masala |
| yellow lays | Lays Classic Salted |
| coke zero | Coca Cola Zero Sugar |
| amul gold | Amul Gold Full Cream Milk |
| amul blue | Amul Taaza Toned Milk |
| maggi masala | Maggi 2-Minute Noodles Masala |

To add your own mappings, edit `COLLOQUIAL_MAP` in `agents/query_normalizer.py`.

### With brand preferences

1. Create a `purchase_history.json` (see format below)
2. Click **⬆ Upload History** before starting
3. The green **✓ History Loaded** badge confirms preferences are active
4. The agent will bias selection toward your preferred brands for this session

### Searching again

Click **✕ Clear**, type new items, click **▶ Start Shopping**. No restart needed.

---

## Purchase history format

```json
[
    {
        "item": "milk",
        "preferred_brand": "Amul Taaza Toned Milk"
    },
    {
        "item": "bread",
        "preferred_brand": "Britannia"
    }
]
```

Brand preferences are **session-scoped** — they only activate after you explicitly upload the file. Running without an upload means completely neutral product selection. Closing and reopening the app always starts with preferences off.

---

## How product selection works

Every search result is scored on three dimensions and the highest total wins:

| Dimension | Weight | What it measures |
|---|---|---|
| Relevance | 40% | Token overlap between your query and the product name. Products with zero relevance are excluded entirely — they can never win on price or brand alone |
| Value | 30% | Price-per-unit efficiency. Compares products in the same base unit (ml, g, count) so a 1L pack at ₹40 correctly beats a 500ml pack at ₹25 |
| Brand | 15% | Tier-1 FMCG (Amul, Britannia, Nestlé…) score higher than Tier-2, which score higher than unknown brands. Your preferred brand scores highest of all |
| Reserved | 15% | Placeholder for future signals: stock availability, ratings |

If the top two candidates are within `0.12` of each other in total score, the LLM is called to break the tie using the full product context (name, price, size, brand). If the gap is clear the LLM call is skipped entirely to save tokens and time.

Near-duplicate listings (same product scraped twice at slightly different prices) are removed before ranking using Jaccard token similarity.

Weights and thresholds can be adjusted in `config.py` under `ScoringWeights`.

---

## How quantity calculation works

1. The planner extracts the requested amount and unit from your input — `"2 litres of milk"` → `{amount: 2, unit: "ltr"}`
2. The bot selects the best matching product — e.g. `"Amul Taaza Toned Milk 500 ml"`
3. The quantity calculator converts both to the same base unit and divides: `ceil(2000ml / 500ml) = 4 packs`
4. For products like `"1 pack (450 ml)"`, the calculator scans all size measurements in the name and picks the one matching your requested unit type — so `450ml` is used, not `1 pack`

Supported units: `ml`, `l`, `ltr`, `litre`, `liter`, `g`, `gm`, `kg`, `pcs`, `pack`, `unit` and their plurals. Maximum 10 units per item to prevent runaway clicks.

---

## Configuration

All tunable settings live in `config.py`:

```python
# Scoring weights
ScoringWeights(relevance=0.40, value=0.30, brand=0.15)

# Skip LLM if score gap is this large or bigger
confidence_gap_threshold: float = 0.12

# Products scoring below this are excluded from ranking entirely
min_relevance_threshold: float = 0.05

# Jaccard similarity above which two products are treated as duplicates
dedup_similarity_threshold: float = 0.80

# Cap on packs added per item
MAX_UNITS = 10  # in quantity_calculator.py
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BROWSER_SESSION_PATH` | `~/.shopping_agent/browser_session` | Where Playwright saves the browser session |

---

## Known limitations

- **Zepto card selector** — `a.B4vNQ` is a generated CSS class that changes when Zepto redeploys. If search stops returning products, open DevTools on Zepto, inspect a product card, and update `_CARD` in `zepto_bot.py`
- **Blinkit/Zepto selector drift** — both sites update their HTML structure occasionally. The selectors most likely to break are documented as module-level constants at the top of each bot file so they are easy to find and update
- **Cart clearing** — uses `aria-label` selectors on stepper buttons. If clearing silently does nothing (cart stays full between runs), the selectors may need updating — the run continues regardless so comparison results are not blocked
- **Quantity accuracy** — if a product name contains no size information (e.g. just `"Amul Milk"` with no `"500ml"`), the quantity calculator cannot divide and defaults to 1 pack
- **LLM dependency** — disambiguation between close-scoring products is better with a local LLM running. Without it the top-ranked candidate is used directly, which is correct most of the time but occasionally picks the wrong variant

---

## Roadmap

- [ ] Swiggy Instamart — third platform for a three-way price comparison
- [ ] Async bots — run Blinkit and Zepto in parallel to cut total search time roughly in half
- [ ] Results export — save comparison table as PDF or CSV
- [ ] Voice input — speak your shopping list via microphone
- [ ] Past searches panel — SQLite log of previous runs with totals
- [ ] Headless mode toggle — run browsers invisibly for faster execution

---

## License

MIT

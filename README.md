# AI Shopping Assistant

An agentic desktop app that automates grocery shopping across **Blinkit** and **Zepto** simultaneously, compares prices in real time, and adds the best-value items to your cart — all from a single natural language input.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt5](https://img.shields.io/badge/UI-PyQt5-green)
![Playwright](https://img.shields.io/badge/Automation-Playwright-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What it does

1. You type something like `"2 litres of milk, eggs and lays chips"`
2. The agent parses your list using an LLM, identifies items and quantities
3. It opens Blinkit and Zepto in a real browser, searches each item, and intelligently picks the best product using a multi-factor ranking system
4. Both carts are cleared from any previous run, then filled with the correct quantities
5. A price comparison table shows you which platform is cheaper and by how much

---

## Features

- **Natural language input** — type your list however you want, quantities included
- **Intelligent product selection** — ranks candidates by relevance, price-per-unit value, and brand quality; doesn't just pick the first result
- **Quantity support** — "2 litres of milk" adds 2 units to both carts
- **Cart clearing** — previous run's cart is emptied automatically before each new run
- **Side-by-side price comparison** — Blinkit vs Zepto with savings highlighted
- **Brand preference memory** — upload a purchase history JSON to bias selection toward your preferred brands (opt-in per session)
- **Re-run without restarting** — clear and search again as many times as you want in the same session
- **Persistent browser session** — stays logged in across runs so you don't need to re-authenticate

---

## Project structure

```
AgenticProject/
├── main.py                        # Entry point
├── ui.py                          # PyQt5 desktop UI
├── config.py                      # All settings and scoring weights
├── llm_client.py                  # Local LLM HTTP wrapper with retry
├── memory.py                      # Purchase history and brand preference store
├── purchase_history.json          # Sample history file (optional)
│
├── agents/
│   ├── planner_agent.py           # Parses natural language into structured item list
│   ├── product_ranker.py          # Multi-factor scoring engine (no LLM)
│   ├── selector_agent.py          # Orchestrates ranker + LLM disambiguation
│   ├── comparison_agent.py        # Compares Blinkit and Zepto cart totals
│   └── recipe_agent.py            # (Optional) Extracts ingredients from a recipe
│
├── automation/
│   ├── blinkit_bot.py             # Playwright bot for Blinkit
│   └── zepto_bot.py               # Playwright bot for Zepto
│
└── utils/
    ├── playwright_manager.py      # Singleton browser context manager
    ├── logging_config.py          # Structured logging setup
    ├── progress.py                # Progress signal helper
    └── storage.py                 # File loader utility
```

---

## Requirements

- Python 3.10+
- A local LLM server running on `http://localhost:8080` (e.g. [LM Studio](https://lmstudio.ai), [Ollama](https://ollama.com), or [llama.cpp](https://github.com/ggerganov/llama.cpp))
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

### 4. Start your local LLM server

Point any OpenAI-compatible server at port `8080`. Example with LM Studio:
- Load a model (recommended: Mistral 7B Instruct or similar)
- Start the local server on port `8080`

To use a different port or URL, edit `config.py`:

```python
@dataclass
class LLMConfig:
    url: str = "http://localhost:8080"
```

### 5. Run the app

```bash
python main.py
```

On first run, the browser will open and ask you to log in to Blinkit and Zepto. After that the session is saved and you won't need to log in again.

---

## Usage

### Basic search
Type your items in plain English and click **▶ Start Shopping**:
```
milk, eggs, brown bread and lays chips
```

### With quantities
```
2 litres of milk, 6 eggs, 1 loaf of bread
```

### With brand preferences
1. Create a `purchase_history.json` (see format below)
2. Click **⬆ Upload History** before starting
3. The green **✓ History Loaded** badge confirms preferences are active
4. The agent will bias selection toward your preferred brands

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

Brand preferences are **session-scoped** — they are only active after you explicitly upload the file. Closing and reopening the app resets to neutral selection.

---

## How product selection works

The ranker scores every search result on three dimensions and picks the highest total:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Relevance | 40% | Token overlap between your query and the product name |
| Value | 30% | Price-per-unit efficiency (handles 500ml vs 1L correctly) |
| Brand | 15% | Tier-1 FMCG brands > Tier-2 brands > unknown |
| (Reserved) | 15% | Future: ratings, stock availability |

If the top two candidates are very close in score, the LLM is called to break the tie using full product context (name, price, size, brand). Otherwise the LLM call is skipped entirely to save tokens.

Weights can be adjusted in `config.py` under `ScoringWeights`.

---

## Configuration

All tunable settings live in `config.py`. Key options:

```python
# Scoring weights
ScoringWeights(relevance=0.40, value=0.30, brand=0.15)

# Skip LLM if score gap is this large or bigger
confidence_gap_threshold: float = 0.12

# Products scoring below this relevance are excluded from ranking
min_relevance_threshold: float = 0.05

# Browser session location (override via environment variable)
# export BROWSER_SESSION_PATH=/your/path
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_SESSION_PATH` | `~/.shopping_agent/browser_session` | Where Playwright saves the browser session |

---

## Known limitations

- Blinkit and Zepto occasionally update their HTML structure, which can break the CSS selectors in the bots. If a search returns no products, the selectors in `blinkit_bot.py` or `zepto_bot.py` may need updating.
- Cart clearing uses aria-label selectors that may need adjustment if the site updates. If clearing fails, the run still continues — the old cart items are just left in place.
- Quantity support clicks the stepper button N-1 times after the initial ADD. Very high quantities (10+) may be slow.

---

## Roadmap

- [ ] Swiggy Instamart support (third platform for comparison)
- [ ] Async bots — run Blinkit and Zepto in parallel to cut total time in half
- [ ] Results export to PDF or CSV
- [ ] Voice input via microphone
- [ ] Past searches history panel (SQLite)
- [ ] Headless mode toggle in the UI

---

## License

MIT

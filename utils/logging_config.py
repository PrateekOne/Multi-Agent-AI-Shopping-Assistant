"""
utils/logging_config.py

Centralized logging setup for the AI Shopping Agent.

Call `setup_logging()` once from main.py before anything else runs.
All modules use `logging.getLogger(__name__)` — no configuration needed per-module.

Log format:
  2025-05-19 10:32:01 | INFO     | agents.selector_agent | Fast path: gap=0.18 -> 'Amul Taaza'
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_file: str | None = "shopping_agent.log",
) -> None:
    """
    Configure root logger with console + optional file output.

    Args:
        level:    Logging level for the console handler. File always logs DEBUG.
        log_file: Path to log file. Pass None to disable file logging.
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # capture everything; handlers filter

    # Console handler (INFO by default)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (DEBUG — full trace for debugging)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialized | console=%s | file=%s",
        logging.getLevelName(level),
        log_file or "disabled",
    )

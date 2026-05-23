"""
utils/playwright_manager.py

Singleton Playwright persistent browser context.

Session path is resolved from (in priority order):
  1. BROWSER_SESSION_PATH environment variable
  2. AppConfig default: ~/.shopping_agent/browser_session

This removes the hardcoded developer machine path and makes the agent
portable across machines and operating systems.
"""

from __future__ import annotations

import logging
import os

from playwright.sync_api import BrowserContext, sync_playwright

from config import CONFIG

logger = logging.getLogger(__name__)

_playwright_instance = None
_browser_context: BrowserContext | None = None


def get_browser() -> BrowserContext:
    """
    Return the singleton Playwright browser context.
    Launches a new one if not already running.
    Raises on launch failure (caller should handle gracefully).
    """
    global _playwright_instance, _browser_context

    if _browser_context is not None:
        return _browser_context

    session_path = CONFIG.browser_session_path
    os.makedirs(session_path, exist_ok=True)

    logger.info("Starting Playwright browser | session=%s", session_path)

    _playwright_instance = sync_playwright().start()

    _browser_context = _playwright_instance.chromium.launch_persistent_context(
        user_data_dir=session_path,
        headless=False,
        args=["--start-maximized"],
    )

    logger.info("Browser started successfully.")
    return _browser_context


def close_browser() -> None:
    """Cleanly shut down the browser context and Playwright instance."""
    global _playwright_instance, _browser_context

    if _browser_context:
        try:
            _browser_context.close()
        except Exception as exc:
            logger.warning("Error closing browser context: %s", exc)
        _browser_context = None

    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception as exc:
            logger.warning("Error stopping playwright: %s", exc)
        _playwright_instance = None

    logger.info("Browser closed.")

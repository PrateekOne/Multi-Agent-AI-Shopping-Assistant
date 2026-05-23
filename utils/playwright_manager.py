import logging
import os

from playwright.sync_api import BrowserContext, sync_playwright

from config import CONFIG

logger = logging.getLogger(__name__)

_playwright_instance = None
_browser_context: BrowserContext | None = None


def get_browser() -> BrowserContext:
    global _playwright_instance, _browser_context

    if _browser_context is not None:
        return _browser_context

    session_path = CONFIG.browser_session_path
    os.makedirs(session_path, exist_ok=True)

    logger.info("Starting browser | session=%s", session_path)
    _playwright_instance = sync_playwright().start()
    _browser_context = _playwright_instance.chromium.launch_persistent_context(
        user_data_dir=session_path,
        headless=False,
        args=["--start-maximized"],
    )
    logger.info("Browser started.")
    return _browser_context


def close_all_pages() -> None:
    # Close every open tab before starting a new run so pages from the
    # previous run don't accumulate and cause stale-state errors
    if _browser_context is None:
        return
    for page in list(_browser_context.pages):
        try:
            page.close()
        except Exception as exc:
            logger.debug("Could not close page: %s", exc)
    logger.debug("All browser pages closed.")


def close_browser() -> None:
    global _playwright_instance, _browser_context
    if _browser_context:
        try:
            _browser_context.close()
        except Exception as exc:
            logger.warning("Error closing browser: %s", exc)
        _browser_context = None
    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception as exc:
            logger.warning("Error stopping playwright: %s", exc)
        _playwright_instance = None
    logger.info("Browser closed.")

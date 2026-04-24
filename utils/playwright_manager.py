from playwright.sync_api import sync_playwright
import os

playwright_instance = None
browser_context = None


SESSION_PATH = r"C:\Users\ganni\Downloads\Agentic AI\browser_session"


def get_browser():
    global playwright_instance, browser_context

    if browser_context is None:
        playwright_instance = sync_playwright().start()

        # Ensure directory exists
        os.makedirs(SESSION_PATH, exist_ok=True)

        browser_context = playwright_instance.chromium.launch_persistent_context(
            user_data_dir=SESSION_PATH,
            headless=False,
            args=[
                "--start-maximized"
            ]
        )

    return browser_context


def close_browser():
    global playwright_instance, browser_context

    if browser_context:
        browser_context.close()
        browser_context = None

    if playwright_instance:
        playwright_instance.stop()
        playwright_instance = None
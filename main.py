"""
main.py — AI Shopping Assistant entry point.

Sets up logging before importing anything else so all modules
get structured log output from the first import.
"""

import sys

from utils.logging_config import setup_logging
setup_logging()   # must be first — before any agent/bot imports

from PyQt5.QtWidgets import QApplication
from ui import App

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())

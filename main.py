import sys

# Set up logging before importing anything else so every module
# gets structured output from the very first import
from utils.logging_config import setup_logging
setup_logging()

from PyQt5.QtWidgets import QApplication
from ui import App

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())

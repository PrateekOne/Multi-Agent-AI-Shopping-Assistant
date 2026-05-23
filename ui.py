"""
ui.py — AI Shopping Assistant UI

PyQt5 application with threaded worker.

Bug fix from original:
  - Zepto now searches using ORIGINAL item names (not Blinkit product names).
    Previously, `zepto_items` was built from `blinkit_cart` (scraped product
    names like "Amul Taaza Toned Milk 500ml"), causing Zepto to search wrong
    queries and producing broken/mismatched price comparisons.
    Now both platforms independently search using the user's intent.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agents.comparison_agent import compare_prices
from agents.planner_agent import extract_items
from automation.blinkit_bot import BlinkitBot
from automation.zepto_bot import ZeptoBot
from memory import save_history
from utils.progress import ProgressTracker
from utils.storage import load_file

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Background Worker
# ──────────────────────────────────────────────────────────────

class Worker(QThread):
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, prompt: str, file_data):
        super().__init__()
        self.prompt = prompt
        self.file_data = file_data

    def run(self):
        tracker = ProgressTracker(self.progress_signal.emit)

        try:
            # ── Parse input ──────────────────────────────────────────────────
            tracker.update(5, "Parsing input...")
            parsed = extract_items(self.prompt)

            items = []
            for name in parsed["priority_items"]:
                q = parsed["item_quantities"].get(
                    name, {"amount": 1, "unit": "unit"}
                )
                items.append({
                    "name": name,
                    "amount": q["amount"],
                    "unit": q["unit"],
                })

            logger.info("Parsed %d items: %s", len(items), [i["name"] for i in items])

            if self.file_data:
                save_history(self.file_data)

            # ── Blinkit ──────────────────────────────────────────────────────
            tracker.update(10, "Running Blinkit...")
            blinkit = BlinkitBot()
            blinkit_cart = blinkit.run(items, tracker)

            # ── Zepto (BUG FIX: use original items, not Blinkit cart names) ──
            tracker.update(10, "Running Zepto...")
            zepto = ZeptoBot()
            zepto_cart = zepto.run(items, tracker)   # <-- was: zepto_items from blinkit_cart

            # ── Compare ──────────────────────────────────────────────────────
            tracker.update(10, "Comparing prices...")
            result = compare_prices(blinkit_cart, zepto_cart)

            self.result_signal.emit(result)

        except Exception as exc:
            logger.error("Worker failed: %s", exc, exc_info=True)
            self.error_signal.emit(str(exc))


# ──────────────────────────────────────────────────────────────
#  Main Application Window
# ──────────────────────────────────────────────────────────────

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.file_data = None
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("AI Shopping Assistant")
        self.setGeometry(200, 200, 900, 600)

        main_layout = QVBoxLayout()

        # ── Input area ───────────────────────────────────────────────────────
        top_layout = QVBoxLayout()

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText(
            "Enter items (e.g. milk and eggs / chicken biryani)"
        )
        self.input_box.setFixedHeight(80)

        btn_layout = QHBoxLayout()

        self.upload_btn = QPushButton("Upload History")
        self.upload_btn.clicked.connect(self.upload_file)

        self.start_btn = QPushButton("Start Shopping")
        self.start_btn.clicked.connect(self.start_process)

        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.start_btn)

        top_layout.addWidget(self.input_box)
        top_layout.addLayout(btn_layout)

        # ── Split: logs (left 70%) + price table (right 30%) ─────────────────
        bottom_layout = QHBoxLayout()

        left_layout = QVBoxLayout()
        self.progress = QProgressBar()
        left_layout.addWidget(self.progress)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        left_layout.addWidget(self.logs)

        left_container = QWidget()
        left_container.setLayout(left_layout)

        right_layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Item", "Blinkit Rs", "Zepto Rs"])
        self.table.horizontalHeader().setStretchLastSection(True)

        right_layout.addWidget(QLabel("Price Comparison"))
        right_layout.addWidget(self.table)

        right_container = QWidget()
        right_container.setLayout(right_layout)

        bottom_layout.addWidget(left_container, 7)
        bottom_layout.addWidget(right_container, 3)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

    # ── Slots ────────────────────────────────────────────────────────────────

    def upload_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Upload History")
        if file:
            self.file_data = load_file(file)
            self.logs.append("History loaded.")

    def update_progress(self, val: int, msg: str):
        self.progress.setValue(val)
        if msg:
            self.logs.append(msg)

    def show_result(self, result: dict):
        items = result.get("items", [])
        self.table.setRowCount(len(items))

        for i, item in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(str(item.get("blinkit", "-"))))
            self.table.setItem(i, 2, QTableWidgetItem(str(item.get("zepto", "-"))))

        summary = (
            f"\nBlinkit total: Rs{result.get('blinkit_total', 0)}\n"
            f"Zepto total:   Rs{result.get('zepto_total', 0)}\n"
            f"Savings:       Rs{result.get('savings', 0)} ({result.get('cheaper', '?')} is cheaper)\n"
        )
        self.logs.append(summary)

        QMessageBox.information(
            self,
            "Savings Summary",
            f"You save Rs{result.get('savings', 0)} using {result.get('cheaper', '?')}",
        )

    def show_error(self, msg: str):
        self.logs.append(f"\n[ERROR] {msg}")
        QMessageBox.critical(self, "Error", msg)

    def start_process(self):
        prompt = self.input_box.toPlainText().strip()
        if not prompt:
            self.logs.append("Please enter items.")
            return

        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.logs.clear()

        self.worker = Worker(prompt, self.file_data)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.show_result)
        self.worker.result_signal.connect(lambda _: self.start_btn.setEnabled(True))
        self.worker.error_signal.connect(self.show_error)
        self.worker.error_signal.connect(lambda _: self.start_btn.setEnabled(True))
        self.worker.start()
